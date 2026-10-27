import fcntl
import json
import os
from pathlib import Path

import pytest

from kitok.youtube_stickman_es.delivery import compact_delivery, clean_visual_cache, inventory, sha256
from kitok.youtube_stickman_es.files import episode_lock


@pytest.fixture
def episode(tmp_path):
    folder = tmp_path / 'episode'
    folder.mkdir()
    for relative, data in [('video_subtitulado.mp4', b'approved final video'),
                           ('miniaturas/miniatura_final.png', b'approved thumbnail'),
                           ('descripcion_youtube_final.txt', b'description'),
                           ('creditos_finales.txt', b'license'), ('voz.mp3', b'paid original'),
                           ('imagenes/escena_001.png', b'original scene')]:
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    qa = folder / 'qa_subtitulado.json'
    qa.write_text(json.dumps({'technical_status': 'passed', 'video_sha256': sha256(folder / 'video_subtitulado.mp4'),
                              'duration': 497.7, 'decoded_frames': 14932}))
    (folder / '.stickman').mkdir()
    (folder / '.stickman/subtitles.json').write_text(json.dumps({'status': 'complete',
           'output_sha256': sha256(folder / 'video_subtitulado.mp4'), 'qa_sha256': sha256(qa)}))
    return tmp_path, folder


def test_bundle_six_files_reuses_video_storage_and_is_idempotent(episode):
    root, folder = episode
    before = inventory(folder)
    result = compact_delivery(root, folder)
    assert result['files'] == 6
    assert compact_delivery(root, folder) == result
    delivery = folder / 'entrega'
    assert len(list(delivery.iterdir())) == 6
    assert (delivery / 'video.mp4').stat().st_ino == (folder / 'video_subtitulado.mp4').stat().st_ino
    assert (delivery / 'descripcion.txt').stat().st_ino != (folder / 'descripcion_youtube_final.txt').stat().st_ino
    assert inventory(folder)['allocated_bytes'] - before['allocated_bytes'] < 30000
    (delivery / 'descripcion.txt').write_text('operator edit')
    with pytest.raises(ValueError, match='Existing entrega differs'):
        compact_delivery(root, folder)
    assert (folder / 'descripcion_youtube_final.txt').read_text() == 'description'


def test_bundle_rejects_changed_video_rejected_qa_and_active_work(episode):
    root, folder = episode
    with episode_lock(folder), pytest.raises(ValueError, match='already being processed'):
        compact_delivery(root, folder)
    (folder / 'video_subtitulado.mp4').write_bytes(b'changed')
    with pytest.raises(ValueError, match='passed caption QA'):
        compact_delivery(root, folder)
    assert not (folder / 'entrega').exists()


def test_cache_cleanup_preserves_inputs_receipts_links_and_approved_outputs(episode):
    root, folder = episode
    work = folder / '.editorial-work/job'
    work.mkdir(parents=True)
    for name in ['s0000_000000000.mp4', 's0000_000000000.handle.mp4', 's0000_000000000.source.png',
                 'assembled.mp4', 's0000_000000000.json', 's0000_000000000.ass', 'unexpected.mp4']:
        (work / name).write_bytes(name.encode())
    # A resource explicitly referenced by the edit is never disposable.
    (folder / 'video_final.editorial.json').write_text(json.dumps({'assets': {'source': {'path': 'episode/.editorial-work/job/s0000_000000000.source.png'}}}))
    # External hardlinks retain physical bytes, so do not claim them reclaimed.
    os.link(work / 'assembled.mp4', root / 'external.mp4')
    snapshot = {p:sha256(p) for p in folder.rglob('*') if p.is_file()}
    report = clean_visual_cache(root, folder)
    assert report['mode'] == 'dry_run' and len(report['files']) == 3
    assert all(sha256(p) == h for p,h in snapshot.items())
    assert report['reclaimable_allocated_bytes'] == 2 * 4096
    applied = clean_visual_cache(root, folder, apply=True)
    assert applied['mode'] == 'applied'
    assert not (work / 's0000_000000000.mp4').exists()
    for path in [folder / 'voz.mp3', folder / 'imagenes/escena_001.png', folder / 'video_subtitulado.mp4',
                 work / 's0000_000000000.json', work / 's0000_000000000.source.png', work / 'unexpected.mp4', root / 'external.mp4']:
        assert path.is_file()
    assert not clean_visual_cache(root, folder)['files']


def test_cleanup_blocks_renderer_lock_and_symlinks(episode):
    root, folder = episode
    work = folder / '.editorial-work/job'
    work.mkdir(parents=True)
    with (work / 'render.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='render is running'):
            clean_visual_cache(root, folder, apply=True)
    outside = root / 'protected.mp4'
    outside.write_bytes(b'preserve')
    (work / 's0000_000000000.mp4').symlink_to(outside)
    with pytest.raises(ValueError, match='symlinks'):
        clean_visual_cache(root, folder, apply=True)
    assert outside.read_bytes() == b'preserve'


@pytest.mark.parametrize('document,reference', [
    ('montaje.json', {'assets': {'previous_clip': {'path': 'episode/.editorial-work/job/s0000_000000000.mp4'}}}),
    ('montaje__v2.json', {'audio_source': '.editorial-work/job/s0000_000000000.mp4'}),
    ('video_final__v2.editorial.json', {'assets': {'previous_clip': {'path': 'episode/.editorial-work/job/s0000_000000000.mp4'}}}),
    ('plan_visual.json', {'scenes': [{'image_file': '.editorial-work/job/s0000_000000000.mp4'}]}),
    ('configuracion.json', {'references': [{'path': '.editorial-work/job/s0000_000000000.mp4'}]}),
    ('planificacion_visual/plan_visual_prevoz.json', {'scenes': [{'reference_files': ['.editorial-work/job/s0000_000000000.mp4']}]}),
])
def test_cleanup_preserves_resources_referenced_by_all_current_plan_contracts(episode, document, reference):
    root, folder = episode
    work = folder / '.editorial-work/job'
    work.mkdir(parents=True)
    protected = work / 's0000_000000000.mp4'
    protected.write_bytes(b'input reused by another edit or audio source')
    disposable = work / 's0001_000000100.mp4'
    disposable.write_bytes(b'disposable rendering')
    # A cache receipt mentioning its own output is not a source contract.
    (work / 's0001_000000100.json').write_text(json.dumps({'output': str(disposable)}))
    plan = folder / document
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(json.dumps(reference))
    report = clean_visual_cache(root, folder, apply=True)
    assert protected.read_bytes() == b'input reused by another edit or audio source'
    assert not disposable.exists()
    assert [item['path'] for item in report['files']] == [str(disposable.relative_to(folder))]


def test_cleanup_never_visits_workspace_created_after_lock_snapshot(episode, monkeypatch):
    from kitok.youtube_stickman_es import delivery
    root, folder = episode
    existing = folder / '.editorial-work/existing'
    existing.mkdir(parents=True)
    (existing / 's0000_000000000.mp4').write_bytes(b'old cache')
    created = folder / '.editorial-work/new-render'
    real_sha = delivery.sha256
    renderer_lock = None

    def start_concurrent_renderer(path):
        nonlocal renderer_lock
        if renderer_lock is None and path == folder / 'video_subtitulado.mp4':
            created.mkdir()
            renderer_lock = (created / 'render.lock').open('a')
            fcntl.flock(renderer_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            (created / 's0001_000000100.mp4').write_bytes(b'in-flight render')
        return real_sha(path)
    monkeypatch.setattr(delivery, 'sha256', start_concurrent_renderer)
    try:
        report = clean_visual_cache(root, folder, apply=True)
        assert len(report['files']) == 1
        assert (created / 's0001_000000100.mp4').read_bytes() == b'in-flight render'
        assert not (existing / 's0000_000000000.mp4').exists()
    finally:
        if renderer_lock:
            renderer_lock.close()


def test_bundle_carries_unresolved_audio_status_and_never_overwrites_stale_or_edited_delivery(episode):
    root, folder = episode
    metadata = folder / 'metadata_youtube_final.json'
    metadata.write_text(json.dumps({'audio_fidelity_status': 'needs_review',
                                   'audio_fidelity_note': 'Unscripted vocalizations require review.',
                                   'final_video_ready': False}))
    result = compact_delivery(root, folder)
    assert result['audio_fidelity_status'] == 'needs_review'
    assert result['final_video_ready'] is False
    report = json.loads((folder / 'entrega/informe.json').read_text())
    assert report['audio_fidelity_status'] == 'needs_review'
    assert report['source_metadata_sha256'] == sha256(metadata)
    assert 'Unscripted vocalizations' in (folder / 'entrega/LEEME.txt').read_text()
    assert report['final_video_ready'] is False
    before = {p.name:sha256(p) for p in (folder / 'entrega').iterdir()}
    metadata.write_text(json.dumps({'audio_fidelity_status': 'review_changed'}))
    with pytest.raises(ValueError, match='Existing entrega differs'):
        compact_delivery(root, folder)
    assert {p.name:sha256(p) for p in (folder / 'entrega').iterdir()} == before
