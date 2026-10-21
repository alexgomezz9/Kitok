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


_NUMBER = r'\d+(?:[.,]\d+)*'
_SIGN = r'[+\-−]?\s*'
_MAGNITUDE = r'(?:trillion|billion|million|thousand|billones?|millones?|mil|bn|[kmbt])'
_UNIT = r'(?:dollars?|euros?|pounds?|por\s+ciento|%)'
_RANGE = rf'(?:\s*[–—-]\s*{_SIGN}[$€£]?\s*{_NUMBER})?'
_APPROX = r'(?:(?:about|roughly|approximately|more than|less than|at least|at most|up to|around)\s+)?'
_AMOUNT = re.compile(
    rf'(?<![\w.]){_APPROX}(?:{_SIGN}[$€£]\s*{_SIGN}{_NUMBER}{_RANGE}(?:\s*{_MAGNITUDE})?(?:\s*{_UNIT})?'
    rf'|{_SIGN}{_NUMBER}{_RANGE}\s*(?:{_MAGNITUDE}(?:\s*{_UNIT})?|{_UNIT}))(?!\w)', re.I)
_NUMBER_WORD = r'(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|trillion|half|quarter|a)'
_WORD_AMOUNT = re.compile(
    rf'(?<![\w-]){_APPROX}(?:(?:minus|negative)\s+|[+−-]\s*)?{_NUMBER_WORD}(?:[\s-]+(?:and|point|{_NUMBER_WORD})){{0,22}}[\s-]+(?:dollars?|euros?|pounds?)(?!\w)', re.I)
_CONCEPT = re.compile(r'\b(?:private cards|hidden cards|software code|source code|financial transfers|access control|private information|unfair advantage|información privada|acceso no autorizado|código fuente)\b', re.I)
_MONTH = r'(?:January|February|March|April|May|June|July|August|September|October|November|December|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)'
_DATE = re.compile(rf'\b(?:(?P<month>{_MONTH}\s+(?:de\s+)?(?:19|20)\d{{2}})|(?:in|during|since|until|by|before|after|from|en|desde|hasta|durante|año|year)\s+(?P<year>(?:19|20)\d{{2}}))\b',re.I)
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
            previous=end
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


def display_headline(text, effect):
    """Short display copy with its original source retained in MotionDesign.text.

    A short question requires explicit editorial copy, never a regex truncation.
    Monetary amounts spelled as whole numbers below 100 can use digits; qualifiers
    and scale stay literal. Pounds remain literal because they can mean weight.
    Other formats are deliberately left intact, including ranges and fractions.
    """
    if effect=='amount':
        ones='zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
        tens={'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}
        match=re.fullmatch(r'(?P<q>more than |less than |at least |at most |about |roughly |approximately |up to |around )?(?P<n>[a-z]+(?:[ -][a-z]+)?) (?P<scale>thousand|million|billion|trillion) (?P<unit>dollars?|euros?)',text,re.I)
        if match:
            parts=match['n'].lower().replace('-',' ').split()
            number=None
            if len(parts)==1 and parts[0] in ones:number=ones.index(parts[0])
            elif parts[0] in tens and (len(parts)==1 or parts[1] in ones[1:10]):
                number=tens[parts[0]]+(ones.index(parts[1]) if len(parts)==2 else 0)
            if number is not None:
                currency='$' if match['unit'].lower().startswith('dollar') else '€'
                return f"{match['q'] or ''}{currency}{number} {match['scale']}"
    return ''


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
        amount = _AMOUNT.search(sentence) or _WORD_AMOUNT.search(sentence)
        date = _DATE.search(sentence)
        if date and re.match(r'\s+(?:rows|records|files|lines|filas|registros|archivos|líneas)\b',sentence[date.end():],re.I):
            date = None
        name = _NAME.search(sentence)
        concept = _CONCEPT.search(sentence)
        if question and 12 <= len(question.group().strip()) <= 180:
            text, effect, reason, full = question.group().strip(), 'question', 'Pregunta explícita de la narración', True
        elif amount:
            text, effect, reason = amount.group(), 'amount', 'Cantidad expresada literalmente, sin convertir unidades ni inferir cifras'
        elif date:
            text, effect, reason = date.group('month') or date.group('year'), 'date', 'Fecha explícita de contexto'
        elif name:
            text, effect, reason = name[1], 'identity', 'Presentación explícita mediante named/called/llamado'
        elif concept and len(sentence)<=180:
            text, effect, reason = sentence, 'keyword', 'Concepto técnico explícito, mostrado dentro de su frase'
        if not effect:
            continue
        if effect=='amount' and (len(text)>100 or re.search(r'[\w+−$€£–—-]$',sentence[:sentence.find(text)].rstrip())):
            # An unrecognised prefix may be part of a larger quantity. Keep
            # stock rather than highlight a smaller, factually different suffix.
            prefix=sentence[:sentence.find(text)].rstrip().split()
            if len(text)>100 or (prefix and re.fullmatch(r'(?:minus|negative|several|many|dozen|dozens|[\d.,]+|[+−$€£–—-])',prefix[-1],re.I)):
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
        design = MotionDesign(effect=effect,text=text,display_text=display_headline(text,effect),label=label,preset=preset,delay=0,
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
                width=1920, height=1080, fps=30, word_alignment=None, visual_plan=None, visual_root=None, script=None) -> EditorialPlan:
    root = Path(root).resolve()
    narration = Path(narration).resolve()
    if not narration.is_relative_to(root):
        raise ValueError('Motion narration must remain in the workspace')
    duration = frame_time(duration,fps)
    if duration < .4:
        raise ValueError('Motion needs at least 0.4s')
    decisions = [] if style == 'basic' else direct_motion(editing,duration,preset=style,word_alignment=word_alignment)
    from .visual_cues import validate_visual_plan, visual_file, cue_start
    script = script if script is not None else ' '.join(section.section for section in getattr(editing, 'sections', []))
    supplied_plan = visual_plan is not None
    visual_plan = validate_visual_plan(visual_plan, script, root, visual_root)
    usable_alignment = word_alignment if editing and provider_sections(editing.sections, word_alignment, duration) is not None else None
    visual_ranges = []
    for cue in visual_plan.visual_cues:
        start, timing = cue_start(cue, script, duration, alignment=usable_alignment)
        if cue.duration is not None and start+cue.duration > duration+1/fps:
            raise ValueError('Explicit visual duration extends beyond the narration')
        if start >= duration:
            raise ValueError('Visual cue starts after the narration ends')
        a = frame_time(start, fps)
        b = frame_time(min(duration, start + (cue.duration or 4.)), fps)
        if b-a < .4-1e-6:
            raise ValueError('Visual cue leaves less than 0.4s before narration ends')
        visual_ranges.append((a, b, cue, timing))
    visual_ranges.sort(key=lambda value: value[0])
    visual_ranges = [(a, min(b, visual_ranges[i+1][0]) if cue.duration is None and i+1<len(visual_ranges) else b, cue, timing)
                     for i,(a,b,cue,timing) in enumerate(visual_ranges)]
    if any(b-a < .4-1e-6 for a,b,*_ in visual_ranges):
        raise ValueError('Visual cues need at least 0.4s between their anchors')
    for previous, following in zip(visual_ranges, visual_ranges[1:]):
        if previous[1] > following[0]+1e-6:
            raise ValueError('Visual cues overlap; adjust anchor, start or duration')
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
    # Photographs own continuous intervals. Remove hidden stock boundaries and
    # absorb tiny stock fragments at their edges without moving spoken anchors.
    prepared_visuals = []
    visual_timing = {}
    for index,(a,b,cue,timing) in enumerate(visual_ranges):
        requested_start,requested_end=a,b
        owned = cue.asset is not None or cue.background == 'black'
        prior = max((t for t in boundaries if t <= a), default=0.)
        after = min((t for t in boundaries if t >= b), default=duration)
        # An overlay keeps every stock cut. If either cue edge falls just
        # across a cut, attach it to the complete neighboring stock scene and
        # retain its spoken anchor through MotionDesign.delay/elapsed.
        next_start_cut=min((t for t in boundaries if t>=a),default=duration)
        previous_end_cut=max((t for t in boundaries if t<=b),default=0.)
        if a-prior < .4-1e-6 or (not owned and 1e-6<next_start_cut-a<.4-1e-6):
            a=prior
        if not owned and 1e-6<b-previous_end_cut<.4-1e-6:
            b=after
        if after-b < .4-1e-6:
            b=after
        if prepared_visuals and a < prepared_visuals[-1][1]-1e-6:
            raise ValueError('Visual cues leave an unrenderable fragment; separate their anchors')
        boundaries = ({t for t in boundaries if not a<t<b} if owned else boundaries) | {a,b}
        key=f'visual_{index}'
        if cue.asset:
            source=visual_file(root, visual_root, cue.asset)
            assets[key]=EditorialAsset(path=str(source.relative_to(root)),description=cue.description,
                                      source_url=cue.source_url,credit=cue.credit,usage=cue.usage,sha256=file_hash(source))
        visual_timing[key]={'requested_anchor_seconds':cue_start(cue,script,duration,alignment=usable_alignment)[0],
                            'requested_duration':cue.duration,'requested_start':requested_start,'requested_end':requested_end,
                            'boundary_adjustment':a!=requested_start or b!=requested_end}

        prepared_visuals.append((a,b,cue,timing,key))
    admitted = []
    for decision in decisions:
        a,b = frame_time(decision.start,fps),frame_time(decision.end,fps)
        if b-a < .4:
            continue
        # Explicit photographs take precedence over automatic plates/overlays.
        if any(a<right and b>left for left,right,*_ in prepared_visuals):
            continue
        # A highlight owns one continuous animation. Full-screen plates may
        # replace several source shots; overlays stop at the next stock boundary.
        candidate = set(boundaries)
        if decision.full_screen:
            a,b,decision,candidate=_plate_interval(a,b,decision,boundaries,duration)
        else:
            decision=replace(decision,design=decision.design.model_copy(update={'hold':b-a}))
        if any(a<right and b>left for left,right,*_ in prepared_visuals):
            continue
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
        if any(a<right and b>left for left,right,*_ in prepared_visuals):
            continue
        boundaries = candidate | {a,b}
        admitted.append((a,b,decision))
    points = sorted(t for t in boundaries if 0 <= t <= duration)
    scenes = []
    for index,(start,end) in enumerate(zip(points,points[1:])):
        if end-start < .4-1e-6:
            raise ValueError('Stock timeline contains sub-0.4s shots')
        visual = next((v for v in prepared_visuals if v[0]-1e-6<=start and end<=v[1]+1e-6), None)
        if visual:
            a,b,cue,timing,key=visual
            data={**cue.motion_data,'effect':cue.effect,'text':cue.text,'elapsed':start-a}
            source_delay=float(data.get('delay',0))
            data['delay']=source_delay+visual_timing[key]['requested_start']-a
            available=visual_timing[key]['requested_end']-visual_timing[key]['requested_start']-source_delay
            if available < .4-1e-6:
                raise ValueError('Visual effect delay leaves no readable interval after cue timing is resolved')
            if data.get('hold') is None:
                data['hold']=min(30,available)
            design=MotionDesign.model_validate(data) if cue.effect else None
            black = not cue.asset and cue.background == 'black'
            stock = next(((i,c) for i,c in enumerate(clips) if c.slot.start-1/fps <= (start+end)/2 < c.slot.end+1/fps),None)
            if not cue.asset and not black and stock is None:
                raise ValueError('Stock timeline does not cover visual effect')
            photo_cameras=('slow_push_in','slow_pull_out','pan_left','pan_right','diagonal_drift')
            camera=cue.camera or (photo_cameras[int(key.split('_')[-1])%len(photo_cameras)] if cue.asset else ('static','slow_push_in','static','pan_right','slow_pull_out','pan_left')[stock[0]%6] if stock and not black else None)
            entry=abs(start-a)<1e-6
            scenes.append(EditorialScene(id=f'shot_{index:04}',start=start,end=end,
                          intention='Recurso visual indicado por el editor',spoken_claim=cue.text or cue.description,
                          asset=key if cue.asset else None if black else f'clip_{stock[0]}',
                          graphic='motion' if black else None,graphic_data={'background':'black'} if black else {},
                          source_start=0 if cue.asset or black else max(0,stock[1].source_start+start-stock[1].slot.start),
                          motion_design=design,camera=camera,image_fit=cue.image_fit,
                          transition=(cue.transition or ('dissolve' if cue.asset or black else 'cut')) if index and entry else 'cut'))
            continue
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
                     camera=('static','slow_push_in','static','pan_right','slow_pull_out','pan_left')[i%6] if supplied_plan else None,
                     transition=('dissolve' if any(abs(start-b)<1e-6 and (cue.asset or cue.background=='black') and cue.transition!='cut' for _,b,cue,_,_ in prepared_visuals) else
                                 'dissolve' if active and active.full_screen and index>0 and abs(start-active_range[0])<1e-6 else 'cut')))
    return EditorialPlan(episode_id=episode_id,title='Documental enriquecido' if style!='basic' else 'Montaje básico',
                         audio_source=str(narration.relative_to(root)),audio_is_final_mix=audio_is_final_mix,
                         duration=duration,width=width,height=height,fps=fps,assets=assets,scenes=scenes,
                         fade_in=visual_plan.fade_in if supplied_plan else 0,fade_out=visual_plan.fade_out if supplied_plan else 0,
                         alignment={'audio_sha256':file_hash(narration),'method':getattr(editing,'alignment',{}),
                                    'motion_decisions':[d.to_dict() for _,_,d in admitted],
                                    'visual_cues':[{'cue_id':key,'asset':key if cue.asset else None,'background':cue.background,'start':a,'end':b,'timing':timing, **visual_timing[key], 'anchor':cue.anchor.model_dump() if cue.anchor else None} for a,b,cue,timing,key in prepared_visuals],
                                    'density_limit':.38,'minimum_gap_seconds':3,'recent_history':2,'recent_window_seconds':45,
                                    'note':'Only explicit supported narration intentions. Estimates remain labelled. No general semantic understanding.'})


def render_motion_longform(clips, narration, duration, output, workspace, *, settings, editing=None,
                           style='investigation', audio_is_final_mix=False, width=1920,height=1080,fps=30,
                           word_alignment=None, workspace_id=None, on_stage=None, visual_plan=None, visual_root=None, script=None):
    from .production import render_editorial_plan
    root = (settings.data_root or PROJECT_ROOT).resolve()
    episode_id = re.sub(r'[^A-Za-z0-9_-]','_',workspace_id or Path(output).stem)[:100]
    plan = motion_plan(clips,Path(narration),duration,root=root,episode_id=episode_id,
                       editing=editing,style=style,audio_is_final_mix=audio_is_final_mix,
                       width=width,height=height,fps=fps,word_alignment=word_alignment,
                       visual_plan=visual_plan,visual_root=visual_root,script=script)
    plan_path = Path(workspace)/'motion-plan.json'
    plan.write(plan_path)
    return render_editorial_plan(plan,root=root,output=Path(output),settings=settings,on_stage=on_stage)


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
