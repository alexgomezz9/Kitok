"""Conservative MotionDirector and Native bridge. Sparse effects, deterministic execution.

Only explicit narration facts are surfaced. Ambiguous prose remains stock. Word
anchors are searched in the supplied alignment; estimates are labelled as such.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import math
import re

from ..config import PROJECT_ROOT
from .motion_components import MotionDesign
from .storyboard import EditorialPlan, EditorialScene, EditorialAsset, file_hash, frame_time, phrase_time


@dataclass(frozen=True)
class MotionDecision:
    start: float
    end: float
    design: MotionDesign
    reason: str
    timing: str
    full_screen: bool = False

    def to_dict(self):
        return {'start': self.start, 'end': self.end, 'design': self.design.model_dump(),
                'reason': self.reason, 'timing': self.timing, 'full_screen': self.full_screen}


_AMOUNT = re.compile(r'(?:[$€£]\s*\d[\d,.]*(?:\s+(?:million|billion|thousand))?|\b\d[\d,.]*\s*(?:%|million|billion|thousand|dollars?|euros?|millones?|mil)\b)', re.I)
_WORD_AMOUNT = re.compile(r'\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)(?:[- ](?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|hundred|thousand|million|billion|and)){0,5}\s+(?:dollars?|euros?|pounds?)\b', re.I)
_PERCENT = re.compile(r'\b\d+(?:[.,]\d+)?\s*%')
_CONCEPT = re.compile(r'\b(?:private cards|hidden cards|software code|source code|financial transfers|access control|private information|unfair advantage|información privada|acceso no autorizado|código fuente)\b', re.I)
_DATE = re.compile(r'\b(?:(?:January|February|March|April|May|June|July|August|September|October|November|December|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?)?(?:19|20)\d{2}\b',re.I)
_NAME = re.compile(r'\b(?:named|called|llamado|llamada)\s+([A-ZÀ-Ý][a-zà-ÿ]+(?:\s+[A-ZÀ-Ý][a-zà-ÿ]+){0,2})\b')


def provider_sections(sections, word_alignment, duration):
    """Match expanded transcript tokens; Fish may split hyphens and emit zero-length tokens.

    Zero-length anchors are accepted, but no new word precision is invented. A
    mismatch rejects the whole timing projection and keeps declared estimates.
    """
    if not word_alignment or not isinstance(word_alignment.get('words'), list):
        return None
    expanded = []
    previous = 0.
    try:
        for word in word_alignment['words']:
            start,end=float(word['start']),float(word['end'])
            if not math.isfinite(start+end) or start < previous-.02 or end < start or start<0 or end>duration+.05:
                return None
            previous=start
            expanded.extend((token,start,end) for token in re.findall(r'\w+',str(word['word']).casefold()))
        expected=[token for section in sections for token in re.findall(r'\w+',section.section.casefold())]
        if expected != [token for token,_,_ in expanded]:
            return None
        projected=[]
        cursor=0
        from ..longform.models import VisualSection
        for section in sections:
            count=len(re.findall(r'\w+',section.section))
            if not count:
                return None
            projected.append(VisualSection(section.section,tuple(getattr(section,'keywords',())),expanded[cursor][1],expanded[cursor+count-1][2]))
            cursor+=count
        return projected
    except (ValueError,TypeError,KeyError):
        return None


def _context_excerpt(sentence,phrase,limit=100):
    if len(sentence)<=limit:
        return sentence
    before,after=sentence.split(phrase,1)
    prefix,suffix=before.split()[-5:],after.split()[:8]
    def value():
        body=' '.join([*prefix,phrase,*suffix])
        return ('… ' if len(before.split())>len(prefix) else '')+body+(' …' if len(after.split())>len(suffix) else '')
    while len(value())>limit and (prefix or suffix):
        if prefix:
            prefix.pop(0)
        else:
            suffix.pop()
    return value()


def direct_motion(editing, duration: float, *, preset='investigation', word_alignment: dict | None = None) -> list[MotionDecision]:
    """Select only supported semantic intentions; density/recent history constrain variety."""
    if preset not in {'investigation', 'archive', 'signal'}:
        raise ValueError('Unknown documentary preset')
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Motion needs a measured positive duration')
    if not editing:
        return []
    decisions = []
    occupied = 0.
    projected = provider_sections(editing.sections,word_alignment,duration)
    usable_alignment = word_alignment if projected is not None else None
    # Input sections are persisted transcript decisions; never call a model here.
    for section in projected or editing.sections:
        sentence = section.section.strip()
        if section.audio_start is None or section.audio_end is None:
            continue
        left, right = float(section.audio_start), float(section.audio_end)
        if not all(math.isfinite(t) for t in (left,right)) or not 0 <= left < right <= duration+.05:
            raise ValueError('Invalid motion section timing')
        text, effect, reason, full = '', '', '', False
        question = re.search(r'[^.!?]*\?', sentence)
        amount = _AMOUNT.search(sentence) or _WORD_AMOUNT.search(sentence) or _PERCENT.search(sentence)
        date = _DATE.search(sentence)
        name = _NAME.search(sentence)
        concept = _CONCEPT.search(sentence)
        if question and 12 <= len(question.group().strip()) <= 180:
            text, effect, reason, full = question.group().strip(), 'question', 'Pregunta explícita de la narración', True
        elif amount:
            text, effect, reason = amount.group(), 'amount', 'Cantidad expresada literalmente, sin convertir unidades ni inferir cifras'
        elif date:
            text, effect, reason = date.group(), 'date', 'Fecha explícita de contexto'
        elif name:
            text, effect, reason = name[1], 'identity', 'Presentación explícita mediante named/called/llamado'
        elif concept and len(sentence)<=180:
            text, effect, reason = sentence, 'keyword', 'Concepto técnico explícito, mostrado dentro de su frase'
        if not effect:
            continue
        anchor, timing = left+.12, 'estimated-sentence'
        if usable_alignment and usable_alignment.get('words'):
            try:
                # Select the matching occurrence inside this section, not a repeated
                # phrase from an earlier scene or an unrelated cached transcript.
                occurrence = 0
                while True:
                    begin, finish = phrase_time(usable_alignment['words'],text,occurrence=occurrence)
                    if left-.25 <= begin <= right and finish <= right+.25:
                        anchor, timing = begin, 'provider-phrase-anchor'
                        break
                    occurrence += 1
            except ValueError:
                pass
        if timing == 'estimated-sentence':
            prefix = sentence[:sentence.find(text)]
            anchor = left + (right-left)*len(prefix.split())/max(1,len(sentence.split()))
        # Never slide an anchored highlight away from the spoken phrase to fit a budget.
        start = max(0, anchor)
        hold = min(8.,right-start+.12) if full else min(4.0,max(2.2,len(text)/22))
        end = min(duration, right+.12, start+hold)
        if end-start < 1.5:
            continue
        label = ''
        if effect == 'amount':
            # A compact exact context excerpt gives the amount a meaning.
            label = _context_excerpt(sentence,text)
        emphasis_delay = .35
        if effect=='keyword' and usable_alignment:
            try:
                occurrence=0
                while True:
                    at,_=phrase_time(usable_alignment['words'],concept.group(),occurrence=occurrence)
                    if start<=at<=right:
                        emphasis_delay=at-start
                        break
                    occurrence+=1
            except ValueError:
                pass
        if effect=='keyword':
            end=min(duration,right+.8,start+max(hold,emphasis_delay+1.4))
        design = MotionDesign(effect=effect,text=text,label=label,preset=preset,delay=0,
                              detail='', emphasis_delay=emphasis_delay, emphasis=concept.group() if effect=='keyword' else '')
        decisions.append(MotionDecision(start,end,design,reason,timing,full))
    # Narrative questions and literal quantities get first claim on the budget;
    # a long optional keyword must not crowd out the revelation later in a clip.
    priorities={'question':3,'amount':3,'date':2,'identity':2,'keyword':1}
    selected=[]
    occupied=0.
    for decision in sorted(decisions,key=lambda d:(-priorities.get(d.design.effect,0),d.start)):
        available=duration*.38-occupied
        if decision.end-decision.start>available:
            if not decision.full_screen or available<1.5:
                continue
            decision=replace(decision,end=decision.start+available)
        if any(not (decision.start>=other.end+3 or decision.end+3<=other.start) for other in selected):
            continue
        recent=[d.design.effect for d in sorted(selected,key=lambda d:d.start)
                if 0 <= decision.start-d.end < 45][-2:]
        effect=decision.design.effect
        if effect in recent and effect=='question':
            effect='quote'
            if effect in recent:
                continue
            decision=replace(decision,design=decision.design.model_copy(update={'effect':effect}))
        elif effect in recent:
            continue
        selected.append(decision)
        occupied+=decision.end-decision.start
    return sorted(selected,key=lambda d:d.start)


def _plate_interval(a,b,decision,boundaries,duration):
    candidate=set(boundaries)
    prior=max((t for t in candidate if t<=a),default=a)
    after=min((t for t in candidate if t>=b),default=b)
    original_a,original_b=a,b
    if a-prior<.4:
        a=prior
    if after-b<.4:
        b=after
    design=decision.design.model_copy(update={'delay':max(0,original_a-a),'hold':original_b-original_a})
    decision=replace(decision,design=design,full_screen=True)
    candidate={t for t in candidate if not a<t<b}
    return a,b,decision,candidate


def motion_plan(clips, narration: Path, duration: float, *, root: Path, episode_id: str,
                editing=None, style='investigation', audio_is_final_mix=False,
                width=1920, height=1080, fps=30, word_alignment=None) -> EditorialPlan:
    root = Path(root).resolve()
    narration = Path(narration).resolve()
    if not narration.is_relative_to(root):
        raise ValueError('Motion narration must remain in the workspace')
    duration = frame_time(duration,fps)
    if duration < .4:
        raise ValueError('Motion needs at least 0.4s')
    decisions = [] if style == 'basic' else direct_motion(editing,duration,preset=style,word_alignment=word_alignment)
    assets = {}
    for index,clip in enumerate(clips):
        source = clip.source.resolve()
        if not source.is_relative_to(root):
            raise ValueError('Motion stock must remain in the workspace')
        assets[f'clip_{index}'] = EditorialAsset(path=str(source.relative_to(root)),description=clip.slot.query or 'Existing stock',
                                              source_url=f'https://www.pexels.com/video/{clip.asset_id}/' if clip.asset_id > 0 else None,
                                              usage='illustration',sha256=file_hash(source))
    boundaries = {0.,duration}
    for clip in clips:
        boundaries.update((frame_time(clip.slot.start,fps),frame_time(min(duration,clip.slot.end),fps)))
    admitted = []
    for decision in decisions:
        a,b = frame_time(decision.start,fps),frame_time(decision.end,fps)
        if b-a < .4:
            continue
        # A highlight owns one continuous animation. Full-screen plates may
        # replace several source shots; overlays stop at the next stock boundary.
        candidate = set(boundaries)
        if decision.full_screen:
            a,b,decision,candidate=_plate_interval(a,b,decision,boundaries,duration)
        else:
            decision=replace(decision,design=decision.design.model_copy(update={'hold':b-a}))
        # Keep shot fragments renderable; fewer effects are better than damaged timing.
        proposed = sorted(candidate|{a,b})
        if any(right-left < .4-1e-6 for left,right in zip(proposed,proposed[1:])):
            if decision.full_screen:
                continue
            # Preserve an important anchored datum using a plate when a tiny
            # stock fragment would otherwise make the overlay unrenderable.
            a,b,decision,candidate=_plate_interval(a,b,decision,boundaries,duration)
            proposed=sorted(candidate|{a,b})
            if any(right-left < .4-1e-6 for left,right in zip(proposed,proposed[1:])):
                continue
        boundaries = candidate | {a,b}
        admitted.append((a,b,decision))
    points = sorted(t for t in boundaries if 0 <= t <= duration)
    scenes = []
    for index,(start,end) in enumerate(zip(points,points[1:])):
        if end-start < .4-1e-6:
            raise ValueError('Stock timeline contains sub-0.4s shots')
        middle = (start+end)/2
        choice = next(((i,c) for i,c in enumerate(clips) if c.slot.start-1/fps <= middle < c.slot.end+1/fps), None)
        if choice is None:
            raise ValueError('Stock timeline does not cover motion plan')
        i,clip = choice
        active_range = next(((a,b,d) for a,b,d in admitted if a-1e-6<=start and end<=b+1e-6), None)
        active = active_range[2] if active_range else None
        design = active.design.model_copy(update={'elapsed':start-active_range[0]},deep=True) if active else None
        scenes.append(EditorialScene(id=f'shot_{index:04}',start=start,end=end,
                     intention=active.reason if active else 'Narración ambiental: mantener stock sin rótulos',
                     spoken_claim=design.text if design else 'Stock ilustrativo',
                     graphic='motion' if active and active.full_screen else None,
                     asset=None if active and active.full_screen else f'clip_{i}',
                     source_start=0 if active and active.full_screen else max(0,clip.source_start+start-clip.slot.start),
                     motion_design=design,
                     transition='dissolve' if style!='basic' and index>0 and index%5==0 else 'cut'))
    return EditorialPlan(episode_id=episode_id,title='Documental enriquecido' if style!='basic' else 'Montaje básico',
                         audio_source=str(narration.relative_to(root)),audio_is_final_mix=audio_is_final_mix,
                         duration=duration,width=width,height=height,fps=fps,assets=assets,scenes=scenes,
                         alignment={'audio_sha256':file_hash(narration),'method':getattr(editing,'alignment',{}),
                                    'motion_decisions':[d.to_dict() for _,_,d in admitted],
                                    'density_limit':.38,'minimum_gap_seconds':3,'recent_history':2,'recent_window_seconds':45,
                                    'note':'Only explicit supported narration intentions. Estimates remain labelled. No general semantic understanding.'})


def render_motion_longform(clips, narration, duration, output, workspace, *, settings, editing=None,
                           style='investigation', audio_is_final_mix=False, width=1920,height=1080,fps=30,
                           word_alignment=None):
    from .production import render_editorial_plan
    root = (settings.data_root or PROJECT_ROOT).resolve()
    episode_id = re.sub(r'[^A-Za-z0-9_-]','_',Path(output).stem)[:100]
    plan = motion_plan(clips,Path(narration),duration,root=root,episode_id=episode_id,
                       editing=editing,style=style,audio_is_final_mix=audio_is_final_mix,
                       width=width,height=height,fps=fps,word_alignment=word_alignment)
    plan_path = Path(workspace)/'motion-plan.json'
    plan.write(plan_path)
    return render_editorial_plan(plan,root=root,output=Path(output),settings=settings)


def automatic_sfx(editing, duration, *, word_alignment=None):
    """At most one quiet cue every 15s, 4/minute; only question/revelation emphasis.

    An effect is optional punctuation, never a sound on each cut. No generated
    media or provider request happens while deriving these editorial events.
    """
    decisions=direct_motion(editing,duration,word_alignment=word_alignment)
    events=[]
    budget=min(24,max(1,math.floor(duration/15)))
    for decision in decisions:
        if decision.design.effect not in {'question','amount','keyword'}:
            continue
        if events and decision.start-events[-1]['time']<15:
            continue
        if decision.start+.4>duration or len(events)>=budget:
            continue
        events.append({'time':round(decision.start,4),'kind':'low_pulse' if decision.design.effect=='question' else 'soft_tick'})
    return events
