"""Compile explicit editorial intent into a local plan, without writing or providers.

This is a deterministic compiler, not a semantic script-writing agent. Missing
resources block the plan instead of substituting unrelated people or footage.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from PIL import Image
from pydantic import Field, field_validator, model_validator

from ..media.ffprobe import probe_media, stream_durations
from ..media_library import local_records, select_asset, validate_record_license
from .cinema import CinemaData
from .storyboard import EditorialAsset, EditorialPlan, EditorialScene, PlanModel, file_hash, project_file


Intent = Literal['establish', 'identify', 'escalate', 'loss', 'compare', 'investigate',
                 'question', 'conceal', 'reveal', 'refund', 'profile']
MODES = {'establish': 'opponent', 'identify': 'opponent', 'escalate': 'aggression',
         'loss': 'loss', 'question': 'question', 'conceal': 'private', 'reveal': 'exposed'}
SHOTS = {'establish': 'wide', 'identify': 'opponent', 'escalate': 'chips',
         'loss': 'overhead', 'question': 'cards', 'conceal': 'cards', 'reveal': 'cards'}
IMAGES = {'.jpg', '.jpeg', '.png', '.webp'}
VIDEOS = {'.mp4', '.mov', '.webm', '.mkv'}


class DirectorBeat(PlanModel):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,70}$')
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    intent: Intent
    claim: str = Field(min_length=1, max_length=1500)
    evidence_url: str = Field(min_length=1, max_length=2000)
    direction: str = Field(default='', max_length=600)
    headline: str | None = Field(default=None, max_length=95)
    kicker: str | None = Field(default=None, max_length=80)
    headline_style: Literal['caption', 'impact'] = 'caption'
    composer: Literal['auto', 'photo', 'stock', 'table', 'records'] = 'auto'
    entity: str | None = Field(default=None, min_length=1, max_length=150)
    role: str | None = Field(default=None, min_length=1, max_length=100)
    reuse_asset: bool = False
    source_start: float = Field(default=0, ge=0, allow_inf_nan=False)
    shot: Literal['wide', 'opponent', 'cards', 'chips', 'overhead'] | None = None
    label: str = Field(default='', max_length=70)
    amount: str = Field(default='', max_length=30)
    detail: str = Field(default='', max_length=100)
    reveal_at: float = Field(default=1.5, ge=0, le=30, allow_inf_nan=False)
    focus_x: float = Field(default=.5, ge=0, le=1, allow_inf_nan=False)
    focus_y: float = Field(default=.45, ge=0, le=1, allow_inf_nan=False)

    @field_validator('evidence_url')
    @classmethod
    def public_source(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Evidence needs an HTTP(S) source URL without credentials')
        return value

    @model_validator(mode='after')
    def complete_beat(self):
        if self.end - self.start < .4 - 1e-6:
            raise ValueError('A beat needs at least 0.4 seconds')
        if bool(self.entity) != bool(self.role):
            raise ValueError('Asset selection needs both exact entity and role')
        if self.composer in {'photo', 'stock'} and not self.entity:
            raise ValueError('Photo/stock beats require exact entity and role')
        if self.composer in {'photo', 'table', 'records'} and self.source_start:
            raise ValueError('Only stock footage can use source_start')
        return self


class DirectorBrief(PlanModel):
    version: Literal[1] = 1
    episode_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    channel_id: str = Field(default='default', pattern=r'^[A-Za-z0-9_-]{1,60}$')
    title: str = Field(min_length=1, max_length=150)
    family: Literal['generic', 'ultimatebet'] = 'generic'
    cast: dict[str, str] = Field(default_factory=dict)
    audio_source: str = Field(min_length=1, max_length=2000)
    audio_approved: Literal[True]
    audio_offset: float = Field(default=0, ge=0, allow_inf_nan=False)
    duration: float = Field(gt=.4, le=7200, allow_inf_nan=False)
    width: int = Field(default=1920, ge=320, le=1920)
    height: int = Field(default=1080, ge=180, le=1080)
    fps: int = Field(default=30, ge=24, le=60)
    beats: list[DirectorBeat] = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def timeline(self):
        if self.width % 2 or self.height % 2:
            raise ValueError('Geometry must use even dimensions')
        if len({beat.id for beat in self.beats}) != len(self.beats):
            raise ValueError('Beat IDs must be unique')
        cursor = 0.
        for beat in self.beats:
            if abs(beat.start - cursor) > 1e-6:
                raise ValueError(f'Timeline gap/overlap before {beat.id}')
            if any(abs(t * self.fps - round(t * self.fps)) > 1e-4 for t in (beat.start, beat.end)):
                raise ValueError('Beat boundaries must use the global FPS frame grid')
            cursor = beat.end
        if abs(cursor - self.duration) > 1e-6:
            raise ValueError('Beats must cover the declared audio duration exactly')
        return self


def _composer(beat: DirectorBeat) -> str:
    if beat.composer != 'auto':
        return beat.composer
    if beat.entity:
        return 'media'
    if beat.intent == 'compare':
        return 'records'
    if beat.intent in MODES:
        return 'table'
    return 'missing'


def _verified_candidates(records, beat, *, root, composer, used, ffprobe_binary):
    candidates, rejected = [], []
    for record in records:
        # Reuse the library's entity, role and accepted-license contract first.
        try:
            if not isinstance(record, dict):
                raise ValueError('Library receipt must be an object')
            for field in ('entities', 'roles'):
                if not isinstance(record.get(field), list) or not all(isinstance(v, str) for v in record[field]):
                    raise ValueError('Library entity and role annotations must be lists of text')
            if select_asset([record], entity=beat.entity, role=beat.role)['status'] != 'selected':
                continue
            validate_record_license(record)
            if record['license'] == 'Pexels':
                if composer == 'photo' or beat.intent in {'identify', 'profile'}:
                    raise ValueError('Illustrative Pexels stock cannot identify a person or replace a verified photograph')
                if urlsplit(beat.evidence_url).hostname in {'www.pexels.com', 'pexels.com'}:
                    raise ValueError('A Pexels stock page cannot substantiate a historical spoken claim')
            digest = record.get('sha256', '')
            if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('Missing or invalid SHA256')
            if digest in used and not beat.reuse_asset:
                rejected.append('Exact asset already used; explicit reuse_asset is required')
                continue
            path = project_file(root, record['path'])
            if file_hash(path) != digest:
                raise ValueError('Asset bytes differ from the licensed library receipt')
            suffix = path.suffix.lower()
            if record['license'] == 'Pexels' and suffix not in VIDEOS:
                raise ValueError('Pexels registration currently supports illustrative video only')
            if suffix in IMAGES and composer in {'media', 'photo'}:
                if beat.source_start or beat.end - beat.start > 30:
                    raise ValueError('Photo compositions require zero source offset and at most 30 seconds')
                with Image.open(path) as image:
                    if image.width * image.height > 30_000_000:
                        raise ValueError('Image exceeds the supported pixel limit')
                    image.load()
                    width, height = image.size
                media_type = 'photo'
            elif suffix in VIDEOS and composer in {'media', 'stock'}:
                info = probe_media(path, ffprobe_binary)
                video_duration, _ = stream_durations(path, ffprobe_binary)
                if not info.video_codec or not info.width or not info.height:
                    raise ValueError('Stock asset has no usable video stream')
                if video_duration is None:
                    raise ValueError('Stock asset has no measured video-stream duration')
                if video_duration + 1e-6 < beat.source_start + beat.end - beat.start:
                    raise ValueError('Stock asset is shorter than the requested beat')
                width, height = info.width, info.height
                media_type = 'stock'
            else:
                raise ValueError('Asset media type does not match the requested composer')
            source = record.get('source_url', '')
            parsed = urlsplit(source)
            if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('Library asset lacks a source URL without credentials')
            attribution = record.get('attribution') or record.get('credit')
            if not isinstance(attribution, str) or not attribution.strip() or len(attribution) > 300:
                raise ValueError('Library asset needs an attribution fitting the plan credit')
            candidates.append({**record, 'path': str(path.relative_to(root)),
                               'width': width, 'height': height, '_composer': media_type})
        except (ValueError, OSError, RuntimeError, KeyError, TypeError, Image.DecompressionBombError) as error:
            rejected.append(str(error))
    # select_asset ties preserve input order, so canonicalize before selection.
    candidates.sort(key=lambda row: (-row['width'] * row['height'], row['sha256'],
                                     str(row.get('id', '')), row['path']))
    return candidates, sorted(set(rejected))


def compile_brief(brief: DirectorBrief | dict, records: list[dict], *, root: Path,
                  ffprobe_binary: str = 'ffprobe') -> dict:
    """Prepare only: no writes, network, narration, generation, or publication."""
    brief = DirectorBrief.model_validate(brief)
    root = root.resolve()
    audio = project_file(root, brief.audio_source)
    info = probe_media(audio, ffprobe_binary)
    _, audio_duration = stream_durations(audio, ffprobe_binary)
    if not info.audio_codec or audio_duration is None:
        raise ValueError('Approved audio needs a measurable audio stream')
    if audio_duration + 1e-6 < brief.audio_offset + brief.duration:
        raise ValueError('Approved audio is shorter than the declared timeline')
    assets, scenes, decisions, missing, used = {}, [], [], [], set()
    for beat in brief.beats:
        composer = _composer(beat)
        common = dict(id=beat.id, start=beat.start, end=beat.end,
                      intention=beat.direction or beat.intent, spoken_claim=beat.claim,
                      evidence_url=beat.evidence_url, headline=beat.headline,
                      kicker=beat.kicker, headline_style=beat.headline_style)
        if composer in {'table', 'records'}:
            if brief.family != 'ultimatebet' or brief.cast != {'player': 'David Paredes', 'opponent': 'NioNio'}:
                missing.append({'beat': beat.id, 'reason': 'Poker reconstructions currently require ultimatebet and the exact supported cast'})
                continue
            if beat.entity or beat.source_start or beat.end - beat.start > 30:
                missing.append({'beat': beat.id, 'reason': 'Reconstruction needs no asset/offset and a beat of at most 30 seconds'})
                continue
            if composer == 'table' and beat.intent not in MODES:
                missing.append({'beat': beat.id, 'reason': 'No supported 3D mode for this explicit intent'})
                continue
            if composer == 'records' and beat.intent != 'compare':
                missing.append({'beat': beat.id, 'reason': 'The current records reconstruction only supports comparison'})
                continue
            mode = MODES[beat.intent] if composer == 'table' else 'records'
            data = CinemaData(mode=mode, engine='three' if composer == 'table' else 'pillow',
                              shot=beat.shot or SHOTS.get(beat.intent, 'wide'), label=beat.label,
                              amount=beat.amount, detail=beat.detail, reveal_at=beat.reveal_at)
            if mode == 'exposed' and beat.reveal_at >= beat.end - beat.start:
                missing.append({'beat': beat.id, 'reason': 'The card reveal must occur within its beat'})
                continue
            scenes.append(EditorialScene(**common, composition=composer, composition_data=data.model_dump()))
            decisions.append({'beat': beat.id, 'composer': composer, 'engine': data.engine,
                              'shot': data.shot, 'reason': f'Explicit {beat.intent} intent; supported reconstruction cast'})
            continue
        if composer == 'missing' or not beat.entity:
            missing.append({'beat': beat.id, 'reason': 'Choose a composer or annotate an exact local asset entity and role'})
            continue
        candidates, rejected = _verified_candidates(records, beat, root=root, composer=composer,
                                                    used=used, ffprobe_binary=ffprobe_binary)
        selected = select_asset(candidates, entity=beat.entity, role=beat.role, used=used)
        if selected['status'] != 'selected':
            missing.append({'beat': beat.id, 'entity': beat.entity, 'role': beat.role,
                            'reason': selected['reason'], 'rejected': rejected})
            continue
        record = selected['asset']
        composer = record['_composer']
        if composer == 'photo' and (beat.source_start or beat.end - beat.start > 30):
            missing.append({'beat': beat.id, 'reason': 'Photo compositions require zero source offset and at most 30 seconds'})
            continue
        asset_id = 'asset_' + record['sha256']
        credit = record.get('attribution') or record['credit']
        assets[asset_id] = EditorialAsset(path=record['path'], sha256=record['sha256'], description=str(record.get('title') or beat.entity)[:600],
                                         source_url=record['source_url'], credit=credit,
                                         usage=('illustration' if record['license'] == 'Pexels' else
                                                'document' if record.get('usage') == 'document' else 'provided'))
        if composer == 'photo':
            data = CinemaData(mode='profile', engine='pillow', label=beat.label, detail=beat.detail,
                              credit=credit[:260], focus_x=beat.focus_x, focus_y=beat.focus_y)
            scenes.append(EditorialScene(**common, asset=asset_id, composition='photo', composition_data=data.model_dump()))
        else:
            scenes.append(EditorialScene(**common, asset=asset_id, source_start=beat.source_start,
                                         motion='pan' if beat.intent == 'investigate' else 'push'))
        decisions.append({'beat': beat.id, 'composer': composer, 'asset': asset_id,
                          'sha256': record['sha256'], 'entity': beat.entity, 'role': beat.role,
                          'license': record['license'], 'source_url': record['source_url'],
                          'license_url': record.get('license_url'),
                          'share_alike': record.get('share_alike'),
                          'content_id': record.get('content_id', 'unknown'),
                          'usage': record.get('usage'), 'restrictions': record.get('restrictions', ''),
                          'credit': credit, 'explicit_reuse': record['sha256'] in used,
                          'reason': selected['reason']})
        used.add(record['sha256'])
    plan = None if missing else EditorialPlan(
        episode_id=brief.episode_id, channel_id=brief.channel_id, title=brief.title,
        audio_source=str(audio.relative_to(root)), audio_offset=brief.audio_offset,
        audio_is_final_mix=True, duration=brief.duration, width=brief.width,
        height=brief.height, fps=brief.fps, assets=assets, scenes=scenes,
        alignment={'method': 'explicit-director-brief', 'precision': 'operator-authored',
                   'audio_sha256': file_hash(audio),
                   'director': {'version': 1, 'family': brief.family, 'decisions': decisions}},
    )
    return {'status': 'blocked' if missing else 'ready', 'plan': plan.model_dump(mode='json') if plan else None,
            'decisions': decisions, 'missing': missing, 'provider_requests': 0}


def load_records(root: Path) -> list[dict]:
    """Read local receipts without constructing a network-enabled library client."""
    return local_records(root)
