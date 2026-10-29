"""Real Native handoff through two videos, bundle and cleanup, with no providers."""
import json

from PIL import Image
import pytest

from test_stickman_pipeline import setup_episode
from test_stickman_word_pipeline import supplied
from kitok.youtube_stickman_es import completion, jobs, pipeline
from kitok.youtube_stickman_es.delivery import sha256
from kitok.youtube_stickman_es.files import episode_lock


def ready(setup_episode):
    root, episode, settings = supplied(setup_episode)
    config = json.loads((episode / 'configuracion.json').read_text())
    config['description'] = 'Descripción editorial aprobada de una prueba técnica.'
    (episode / 'configuracion.json').write_text(json.dumps(config))
    Image.new('RGB', (1280, 720), '#596575').save(episode / 'miniaturas/miniatura_final.png')
    pipeline.execute(root, episode, 'prepare', settings=settings, reuse_images=True)
    return root, episode, settings


def test_real_queue_closes_both_qa_bundle_and_cleanup_then_reuses_without_encode(setup_episode, monkeypatch):
    root, episode, settings = ready(setup_episode)
    from kitok.youtube_stickman_es import audio, subtitle_delivery
    monkeypatch.setattr(pipeline, 'prepare_narration', lambda *a, **kw: pytest.fail('No ASR or voice preparation after handoff'))
    monkeypatch.setattr(subtitle_delivery, 'prepare_narration', lambda *a, **kw: pytest.fail('Use accepted frozen narration'))
    monkeypatch.setattr(audio, 'FishVoiceClient', lambda *a, **k: pytest.fail('No paid providers'))
    before = completion.handoff_inputs(episode)
    row = jobs.enqueue(root, episode, start=False)
    jobs.worker(root, settings=settings)
    state = jobs.status(root)[0]
    assert state['status'] == 'technical_complete', state.get('error')
    assert state['result']['cleanup_files'] > 0
    assert len(list((episode / 'entrega').iterdir())) == 6
    receipt = json.loads((episode / '.stickman/completion-cleanup.json').read_text())
    assert receipt['status'] == 'complete' and receipt['protected_hashes_verified']
    assert completion.handoff_inputs(episode) == before
    assert completion.verify_videos(episode)
    assert not list((episode / '.editorial-work').glob('*/s*.mp4'))
    videos = {name: sha256(episode / name) for name in ('video_final.mp4', 'video_subtitulado.mp4')}
    monkeypatch.setattr(pipeline, 'render_editorial_plan', lambda *a, **kw: pytest.fail('No recode'))
    monkeypatch.setattr(subtitle_delivery, 'choose_encoder', lambda *a, **kw: pytest.fail('Reuse caption encode'))
    result = pipeline.execute(root, episode, 'complete', settings=settings, handoff=before)
    assert result['status'] == 'technical_complete' and result['cleanup_files'] == 0
    assert all(sha256(episode / name) == digest for name, digest in videos.items())
    assert row['id'] in (root / 'local/stickman_jobs/ESTADO.md').read_text()


def test_changed_handoff_blocks_before_render_and_preserves_materials(setup_episode, monkeypatch):
    root, episode, settings = ready(setup_episode)
    expected = completion.handoff_inputs(episode)
    Image.new('RGB', (1280, 720), 'red').save(episode / 'miniaturas/miniatura_final.png')
    monkeypatch.setattr(pipeline, '_render', lambda *a, **kw: pytest.fail('No render of changed inputs'))
    with pytest.raises(ValueError, match='Handoff inputs changed'):
        pipeline.execute(root, episode, 'complete', settings=settings, handoff=expected)
    assert not (episode / 'video_final.mp4').exists()


def test_missing_editorial_inputs_and_active_episode_are_rejected(setup_episode):
    root, episode, settings = supplied(setup_episode)
    pipeline.execute(root, episode, 'prepare', settings=settings, reuse_images=True)
    with pytest.raises(ValueError, match='description and chapter'):
        jobs.enqueue(root, episode, start=False)
    with episode_lock(episode), pytest.raises(ValueError, match='already being processed'):
        jobs.enqueue(root, episode, start=False)


def test_normal_qa_and_base_identity_are_required_before_any_cleanup(tmp_path):
    episode = tmp_path
    for name in ('video_final.mp4', 'video_subtitulado.mp4'):
        (episode / name).write_bytes(name.encode())
    (episode / '.stickman').mkdir()
    for suffix, video in (('', 'video_final.mp4'), ('_subtitulado', 'video_subtitulado.mp4')):
        (episode / ('qa'+suffix+'.json')).write_text(json.dumps({
            'technical_status': 'passed', 'video_sha256': sha256(episode / video), 'copied_audio_identical': True}))
    (episode / 'video_final.editorial.json').write_text(json.dumps({'output_sha256': sha256(episode / 'video_final.mp4')}))
    record = {'status': 'complete', 'identity': {'base_video_sha256': 'wrong'},
              'output_sha256': sha256(episode / 'video_subtitulado.mp4'),
              'qa_sha256': sha256(episode / 'qa_subtitulado.json')}
    (episode / '.stickman/subtitles.json').write_text(json.dumps(record))
    with pytest.raises(ValueError, match='Both video receipts'):
        completion.verify_videos(episode)
    record['identity']['base_video_sha256'] = sha256(episode / 'video_final.mp4')
    (episode / '.stickman/subtitles.json').write_text(json.dumps(record))
    assert completion.verify_videos(episode)
    (episode / 'video_final.mp4').write_bytes(b'tampered original')
    with pytest.raises(ValueError, match='Both videos require'):
        completion.verify_videos(episode)

@pytest.fixture
def rendered(tmp_path, monkeypatch):
    episode = tmp_path / 'episode'
    episode.mkdir()
    for name, content in (
        ('video_final.mp4', 'normal'), ('video_subtitulado.mp4', 'captioned'),
        ('source.png', 'paid source'), ('miniaturas/miniatura_final.png', 'thumbnail'),
        ('metadata_youtube.json', '{"title":"Approved"}'),
        ('descripcion_youtube.txt', 'Approved description'), ('CREDITS.md', 'Real music credit')):
        path = episode / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    (episode / '.stickman').mkdir()
    for suffix, name in (('', 'video_final.mp4'), ('_subtitulado', 'video_subtitulado.mp4')):
        (episode / ('qa'+suffix+'.json')).write_text(json.dumps({
            'technical_status': 'passed', 'video_sha256': sha256(episode / name),
            'copied_audio_identical': True}))
    (episode / 'video_final.editorial.json').write_text(json.dumps({'output_sha256': sha256(episode / 'video_final.mp4')}))
    (episode / '.stickman/subtitles.json').write_text(json.dumps({
        'status': 'complete', 'identity': {'base_video_sha256': sha256(episode / 'video_final.mp4')},
        'output_sha256': sha256(episode / 'video_subtitulado.mp4'),
        'qa_sha256': sha256(episode / 'qa_subtitulado.json')}))
    expected = {'source.png': sha256(episode / 'source.png')}
    monkeypatch.setattr(completion, 'handoff_inputs', lambda p: {'source.png': sha256(p / 'source.png')})
    workspace = episode / '.editorial-work/job'
    workspace.mkdir(parents=True)
    for i in range(2):
        (workspace / f's000{i}_000000000.mp4').write_bytes(b'regenerable')
    return tmp_path, episode, expected, workspace


def test_partial_cleanup_is_audited_before_delete_and_retry_keeps_delivery(rendered, monkeypatch):
    root, episode, expected, work = rendered
    original = completion._organize_locked
    def interrupted(*args, **kw):
        if kw['apply']:
            planned = json.loads((episode / '.stickman/completion-cleanup.json').read_text())
            assert planned['status'] == 'planned' and len(planned['attempts'][-1]['removed']) == 2
            (work / 's0000_000000000.mp4').unlink()
            raise RuntimeError('interrupted during cleanup')
        return original(*args, **kw)
    monkeypatch.setattr(completion, '_organize_locked', interrupted)
    with episode_lock(episode), pytest.raises(RuntimeError, match='interrupted during cleanup'):
        completion.complete_locked(root, episode, expected=expected)
    delivery_before = {p.name: sha256(p) for p in (episode / 'entrega').iterdir()}
    assert (work / 's0001_000000000.mp4').exists()
    monkeypatch.setattr(completion, '_organize_locked', original)
    with episode_lock(episode):
        result = completion.complete_locked(root, episode, expected=expected)
    assert result['status'] == 'technical_complete' and result['cleanup_files'] == 1
    assert {p.name: sha256(p) for p in (episode / 'entrega').iterdir()} == delivery_before
    assert len(json.loads((episode / '.stickman/completion-cleanup.json').read_text())['attempts']) == 2


def test_bundle_failure_never_cleans(rendered, monkeypatch):
    root, episode, expected, work = rendered
    def reject(*a, **kw):
        raise ValueError('Existing entrega differs')
    monkeypatch.setattr(completion, '_compact_delivery_locked', reject)
    monkeypatch.setattr(completion, '_organize_locked', lambda *a, **kw: pytest.fail('No cleanup on failed bundle'))
    with episode_lock(episode), pytest.raises(ValueError, match='Existing entrega differs'):
        completion.complete_locked(root, episode, expected=expected)
    assert len(list(work.glob('*.mp4'))) == 2


def test_complete_propagates_gpu_policy_to_base_and_captions(setup_episode, monkeypatch):
    root, episode, settings = ready(setup_episode)
    from kitok.youtube_stickman_es import subtitle_delivery
    expected = completion.handoff_inputs(episode)
    observed = []
    monkeypatch.setattr(pipeline, '_render', lambda *a, **kw: observed.append(kw['encoder_name']))
    monkeypatch.setattr(subtitle_delivery, 'caption_video', lambda *a, **kw: observed.append(kw['encoder_name']))
    monkeypatch.setattr(completion, 'complete_locked', lambda *a, **kw: {'status': 'technical_complete'})
    pipeline.execute(root, episode, 'complete', settings=settings, handoff=expected, require_gpu=True)
    assert observed == ['h264_nvenc', 'h264_nvenc']
