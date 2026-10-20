from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from kitok.api.schemas import LongformRequest
from kitok.config import Settings
from kitok.editing.manifest import build_edit_manifest
from kitok.locks import generation_lock, GenerationBusy
from kitok.longform_studio import LongformStudio
from kitok.media.ffmpeg import EncoderSettings, RenderSpec
from kitok.native_recovery import CachedStock, digest, identity, inspect_narration
from kitok.rendering.native import NativeLongformRenderer
from kitok.stock.cache import SearchCache, AssetCache
from kitok.stock.models import StockAsset, StockVariant, SelectedStock


@pytest.fixture
def failed_job(tmp_path, monkeypatch, request):
    settings = Settings(_env_file=None, data_root=tmp_path, native_cache_dir=tmp_path / 'cache' / 'pexels')
    app = SimpleNamespace(s=settings, _mutex=threading.Lock(), _executor=ThreadPoolExecutor(max_workers=1))
    studio = LongformStudio(app)
    row = studio.create(LongformRequest(subject='Recovery test', script='The narrator describes this important city.',
                                       keywords=getattr(request, 'param', ['city']), music_enabled=False, music_mode='off'))
    cid = row['id']
    record = studio._read(cid)
    record.update(status='failed', error='Original paid operation failed after narration', stage='Original stage')
    studio._write(record)
    from kitok.longform.cli import load_longform_config
    definition = load_longform_config(studio.folder / f'{cid}.json', project_root=tmp_path)
    narration = studio.output_path(cid).parent / '.native-work' / cid / 'narration.mp3'
    narration.parent.mkdir(parents=True)
    narration.write_bytes(b'confirmed-paid-audio')
    words = {'words': [{'word': word, 'start': i * 2., 'end': i * 2. + 1}
                       for i, word in enumerate(definition.item.script.split())]}
    narration.with_suffix('.alignment.json').write_text(json.dumps(words))
    build_edit_manifest(definition.item.script, 12., ['city'], audio_sha256=digest(narration),
                        word_alignment=words).write(studio.output_path(cid).with_suffix('.edit.json'))
    body = {'text': definition.item.script, 'reference_id': definition.voice_name.split(':')[1],
            'format': 'mp3', 'temperature': .8, 'top_p': .7, 'prosody': {'speed': definition.voice_rate}}
    request_hash = identity({'version': 2, 'model': settings.fish_model, 'body': body})
    cache = settings.audio_cache_dir / request_hash[:2] / request_hash
    cache.mkdir(parents=True)
    (cache / 'audio.mp3').write_bytes(narration.read_bytes())
    (cache / 'operation.json').write_text(json.dumps({'status': 'succeeded', 'request_hash': request_hash,
                                                    'model': settings.fish_model, 'audio_sha256': digest(narration)}))
    info = SimpleNamespace(duration=12., audio_codec='mp3')
    monkeypatch.setattr('kitok.native_recovery.probe_media', lambda *a: info)
    monkeypatch.setattr('kitok.rendering.native.probe_media', lambda *a: info)
    try:
        yield studio, definition, narration, info
    finally:
        app._executor.shutdown(wait=True)


def test_audit_is_read_only_and_validates_actual_paid_identity(failed_job):
    studio, definition, narration, _ = failed_job
    before = {p: digest(p) for p in studio.root.rglob('*') if p.is_file()}
    audit = studio.recovery_audit(definition.item.id)
    assert audit['narration_sha256'] == digest(narration)
    assert audit['duration'] == 12 and audit['network_allowed'] is False
    assert before == {p: digest(p) for p in studio.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('corruption', ['audio', 'alignment', 'edit', 'script', 'voice', 'receipt', 'output', 'symlink', 'status'])
def test_audit_fails_closed_without_new_speech(failed_job, corruption):
    studio, definition, narration, _ = failed_job
    cid = definition.item.id
    if corruption == 'audio':
        narration.write_bytes(b'changed')
    elif corruption == 'alignment':
        narration.with_suffix('.alignment.json').write_text('{"words": [{"word":"foreign", "start":0,"end":1}]}')
    elif corruption == 'edit':
        studio.output_path(cid).with_suffix('.edit.json').unlink()
    elif corruption == 'script':
        (studio.folder / f'{cid}.txt').write_text('A different narration has been substituted.')
    elif corruption == 'voice':
        record = studio._read(cid)
        record['request']['narrator_voice'] = 'fish_audio:other:Other voice'
        studio._write(record)
    elif corruption == 'receipt':
        next(studio.s.audio_cache_dir.rglob('operation.json')).write_text('{"status":"unknown"}')
    elif corruption == 'output':
        studio.output_path(cid).write_bytes(b'preserve me')
    elif corruption == 'symlink':
        narration.rename(narration.with_suffix('.original'))
        narration.symlink_to(narration.with_suffix('.original'))
    elif corruption == 'status':
        record = studio._read(cid); record['status'] = 'draft'; studio._write(record)
    with pytest.raises(ValueError):
        studio.recovery_audit(cid)


def test_confirmation_rejects_changed_inputs_and_same_id_parallelism(failed_job):
    studio, definition, narration, _ = failed_job
    cid = definition.item.id
    audit = studio.recovery_audit(cid)
    with pytest.raises(ValueError, match='confirmación'):
        studio.recover(cid, '0' * 64, audit['audit_fingerprint'])
    with generation_lock(studio.s, f'longform-{cid}'):
        with pytest.raises(GenerationBusy):
            studio.recover(cid, audit['narration_sha256'], audit['audit_fingerprint'])
    narration.with_suffix('.alignment.json').write_text(narration.with_suffix('.alignment.json').read_text() + '\n')
    with pytest.raises(ValueError, match='confirmación'):
        studio.recover(cid, audit['narration_sha256'], audit['audit_fingerprint'])
    assert studio._read(cid)['status'] == 'failed'


def test_explicit_recovery_preserves_failure_and_holds_lock_through_worker(failed_job, monkeypatch):
    studio, definition, narration, _ = failed_job
    cid = definition.item.id
    audit = studio.recovery_audit(cid)
    entered, release = threading.Event(), threading.Event()
    def render(record, definition, stage, *, confirmed_narration):
        assert confirmed_narration.sha256 == audit['narration_sha256']
        entered.set()
        assert release.wait(5)
        studio.output_path(cid).write_bytes(b'rendered')
    monkeypatch.setattr(studio, '_render', render)
    studio.recover(cid, audit['narration_sha256'], audit['audit_fingerprint'])
    assert entered.wait(5)
    with pytest.raises(GenerationBusy):
        with generation_lock(studio.s, f'longform-{cid}'):
            pass
    release.set(); studio.application._executor.shutdown(wait=True)
    record = studio._read(cid)
    assert record['status'] == 'succeeded'
    assert record['recovery_attempts'][0]['previous_error'] == 'Original paid operation failed after narration'
    assert record['recovery_attempts'][0]['status'] == 'succeeded'
    assert digest(narration) == audit['narration_sha256']


@pytest.mark.parametrize('failed_job', [['city'], ['city', 'unused original keyword']], indirect=True)
def test_offline_renderer_never_constructs_fish_and_preserves_workspace(failed_job, monkeypatch):
    studio, definition, narration, info = failed_job
    confirmed = studio._recovery_inputs(definition.item.id)[2]
    root = studio.s.native_cache_dir
    asset = StockAsset(1, 'city', 30., (StockVariant('https://unreachable.invalid/a.mp4', 1920, 1080, 30),))
    SearchCache(root).store('city', 'landscape', 80, 1, [asset])
    selection = SelectedStock(asset, asset.variants[0])
    cache = AssetCache(root); part = cache.part_path(1); part.write_bytes(b'cached-stock'); cache.commit(selection, part)
    monkeypatch.setattr('kitok.native_recovery.valid_video', lambda *a: True)
    previous = narration.parent / 'failed-mix.wav.part'; previous.write_bytes(b'preserve')
    def forbidden(*a, **kw):
        pytest.fail('Fish must never be constructed during confirmed recovery')
    class ForbiddenSecret:
        def get_secret_value(self):
            pytest.fail('Recovery must not access provider credentials')
    settings = studio.s.model_copy(update={'fish_api_key': ForbiddenSecret(), 'pexels_api_key': ForbiddenSecret()})
    class Engine:
        spec = RenderSpec()
        encoder = EncoderSettings('libx264', 'veryfast')
        def render(self, clips, audio, duration, output, workspace, **kw):
            assert audio == narration and workspace.parent == narration.parent
            assert workspace != narration.parent
            output.write_bytes(b'assembled-video')
            return info
    monkeypatch.setattr('kitok.rendering.native.write_render_manifest', lambda *a, **kw: None)
    stock = CachedStock(root)
    preflight_calls = []
    original_preflight = stock.preflight_searches
    def preflight(queries, **kwargs):
        preflight_calls.append(list(queries))
        original_preflight(queries, **kwargs)
    monkeypatch.setattr(stock, 'preflight_searches', preflight)
    result = NativeLongformRenderer(settings, stock, Engine(), output_path=studio.output_path(definition.item.id),
                                    fish_factory=forbidden, confirmed_narration=confirmed).render(definition)
    assert result.output.is_file()
    assert preflight_calls == [['city']]
    assert result.timings.fish == 0
    assert previous.read_bytes() == b'preserve'
    assert digest(narration) == confirmed.sha256


def test_motion_recovery_uses_new_editorial_workspace_with_same_output(failed_job, monkeypatch):
    from kitok.editing.motion import render_motion_longform
    from kitok.longform.models import TimelineClip, TimelineSlot
    studio, definition, narration, _ = failed_job
    stock = studio.root / 'cached.mp4'; stock.write_bytes(b'local video')
    clips = [TimelineClip(TimelineSlot(index=0, start=0., duration=12., query='city'), 1, stock, 0.)]
    seen = []
    monkeypatch.setattr('kitok.editing.production.render_editorial_plan', lambda plan, **kwargs: seen.append((plan, kwargs)))
    render_motion_longform(clips, narration, 12., studio.output_path(definition.item.id), narration.parent,
                           settings=studio.s, style='basic', workspace_id=f'{definition.item.id}-recovery-unique')
    plan, kwargs = seen[0]
    assert plan.episode_id == f'{definition.item.id}-recovery-unique'
    assert kwargs['output'] == studio.output_path(definition.item.id)


def test_cache_only_miss_preserves_part_and_never_opens_http(tmp_path):
    stock = CachedStock(tmp_path)
    part = tmp_path / 'videos' / '1.mp4.part'; part.parent.mkdir(); part.write_bytes(b'existing download')
    with pytest.raises(ValueError, match='missing'):
        stock.search_videos('missing', orientation='landscape')
    assert part.read_bytes() == b'existing download'


@pytest.mark.parametrize('editing_enabled', [True, False])
def test_offline_renderer_still_rejects_missing_used_search_without_fish(failed_job, editing_enabled):
    studio, definition, narration, _ = failed_job
    confirmed = studio._recovery_inputs(definition.item.id)[2]
    before = digest(narration)
    definition = SimpleNamespace(**vars(definition), editing_enabled=editing_enabled)
    part = narration.parent / 'previous-download.part'
    part.write_bytes(b'preserve previous attempt')
    def forbidden(*args, **kwargs):
        pytest.fail('Offline recovery must not synthesize or render after a required cache miss')
    engine = SimpleNamespace(spec=RenderSpec(), encoder=EncoderSettings('libx264', 'veryfast'), render=forbidden)
    renderer = NativeLongformRenderer(studio.s, CachedStock(studio.s.native_cache_dir), engine,
                                      output_path=studio.output_path(definition.item.id),
                                      fish_factory=forbidden, confirmed_narration=confirmed)
    with pytest.raises(ValueError, match='missing'):
        renderer.render(definition)
    assert digest(narration) == before
    assert part.read_bytes() == b'preserve previous attempt'
    assert not studio.output_path(definition.item.id).exists()
    assert studio._read(definition.item.id)['status'] == 'failed'
