import fcntl
import json
import os
from pathlib import Path

import pytest

from kitok.youtube_stickman_es.delivery import compact_delivery, clean_visual_cache, inventory, sha256
from kitok.youtube_stickman_es.files import episode_lock
from kitok.youtube_stickman_es.final_paths import final_video


@pytest.fixture
def episode(tmp_path):
    folder = tmp_path / 'episode'
    folder.mkdir()
    for relative, data in [('video_subtitulado.mp4', b'approved final video'),
                           ('video_final.mp4', b'approved clean video'),
                           ('miniaturas/miniatura_final.png', b'approved thumbnail'),
                           ('descripcion_youtube_final.txt', b'description'),
                           ('creditos_finales.txt', b'license'), ('voz.mp3', b'paid original'),
                           ('voz.srt', b'1\n00:00:00,000 --> 00:00:01,000\nTest\n'),
                           ('titulo.txt', b'Approved title'),
                           ('imagenes/escena_001.png', b'original scene')]:
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    qa = folder / 'qa_subtitulado.json'
    qa.write_text(json.dumps({'technical_status': 'passed', 'video_sha256': sha256(folder / 'video_subtitulado.mp4'),
                              'duration': 497.7, 'decoded_frames': 14932, 'copied_audio_identical': True}))
    (folder / 'qa.json').write_text(json.dumps({'technical_status': 'passed',
         'video_sha256': sha256(folder / 'video_final.mp4')}))
    (folder / 'video_final.editorial.json').write_text(json.dumps({'output_sha256': sha256(folder / 'video_final.mp4')}))
    (folder / '.stickman').mkdir()
    (folder / '.stickman/subtitles.json').write_text(json.dumps({'status': 'complete',
           'identity': {'base_video_sha256': sha256(folder / 'video_final.mp4')},
           'output_sha256': sha256(folder / 'video_subtitulado.mp4'), 'qa_sha256': sha256(qa)}))
    return tmp_path, folder


def test_bundle_upload_files_reuses_video_storage_and_is_idempotent(episode):
    root, folder = episode
    before = inventory(folder)
    inode = (folder / 'video_subtitulado.mp4').stat().st_ino
    result = compact_delivery(root, folder)
    assert result['files'] == 8
    assert compact_delivery(root, folder) == result
    delivery = folder / 'entrega'
    assert len(list(delivery.iterdir())) == 8
    assert (delivery / 'video_subtitulado.mp4').stat().st_ino == inode
    assert not (folder / 'video_subtitulado.mp4').exists()
    assert not (folder / 'video_final.mp4').exists()
    assert final_video(folder, 'video_subtitulado.mp4') == delivery / 'video_subtitulado.mp4'
    assert (delivery / 'descripcion.txt').stat().st_ino != (folder / 'descripcion_youtube_final.txt').stat().st_ino
    assert inventory(folder)['allocated_bytes'] - before['allocated_bytes'] < 65536
    (delivery / 'descripcion.txt').write_text('operator edit')
    with pytest.raises(ValueError, match='Existing entrega differs'):
        compact_delivery(root, folder)
    assert (folder / 'descripcion_youtube_final.txt').read_text() == 'description'


def test_bundle_accepts_empty_common_delivery_folder(episode):
    from kitok.youtube_stickman_es.workspace import index_episode
    root, folder = episode
    index_episode(folder)
    assert not list((folder / 'entrega').iterdir())
    assert compact_delivery(root, folder)['files'] == 8
    assert len(list((folder / 'entrega').iterdir())) == 8


def test_bundle_rejects_changed_video_rejected_qa_and_active_work(episode):
    root, folder = episode
    with episode_lock(folder), pytest.raises(ValueError, match='already being processed'):
        compact_delivery(root, folder)
    (folder / 'video_subtitulado.mp4').write_bytes(b'changed')
    with pytest.raises(ValueError, match='Both videos require'):
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
    report = json.loads((folder / '.stickman/delivery.json').read_text())
    assert report['audio_fidelity_status'] == 'needs_review'
    assert report['source_metadata_sha256'] == sha256(metadata)
    assert 'Unscripted vocalizations' in report['audio_fidelity_note']
    assert report['final_video_ready'] is False
    before = {p.name:sha256(p) for p in (folder / 'entrega').iterdir()}
    metadata.write_text(json.dumps({'audio_fidelity_status': 'review_changed'}))
    with pytest.raises(ValueError, match='Existing entrega differs'):
        compact_delivery(root, folder)
    assert {p.name:sha256(p) for p in (folder / 'entrega').iterdir()} == before


def legacy_bundle(folder):
    import shutil
    destination = folder / 'entrega'
    destination.mkdir(exist_ok=True)
    sources = {'video.mp4': 'video_subtitulado.mp4', 'miniatura.png': 'miniaturas/miniatura_final.png',
               'descripcion.txt': 'descripcion_youtube_final.txt', 'creditos.txt': 'creditos_finales.txt'}
    for name, source in sources.items():
        shutil.copy2(folder / source, destination / name)
    report = {'version': 1, 'sha256': {name: sha256(destination / name) for name in sources}}
    (destination / 'informe.json').write_text(json.dumps(report))
    (destination / 'LEEME.txt').write_text('Old handoff')


def test_normalize_legacy_moves_only_verified_duplicates_and_preserves_distinct_video(episode):
    from kitok.youtube_stickman_es.delivery import normalize_delivery
    root, folder = episode
    legacy_bundle(folder)
    duplicate = folder / 'revisiones/old/video.mp4'
    duplicate.parent.mkdir(parents=True)
    duplicate.write_bytes((folder / 'video_final.mp4').read_bytes())
    distinct = folder / 'revisiones/old/unique.mp4'
    distinct.write_bytes(b'Historical different edit')
    override = folder / 'editorial/publicacion_youtube.json'
    override.parent.mkdir()
    override.write_text(json.dumps({'title': 'New Studio title', 'description': '*CAPÍTULOS*\n00:00 Prueba',
                                    'tags': ['terror', 'stickman']}))
    report = normalize_delivery(root, folder)
    assert report['mode'] == 'dry_run'
    assert duplicate.exists() and (folder / 'video_final.mp4').exists()
    assert str(distinct.relative_to(folder)) in report['distinct_videos_preserved']
    result = normalize_delivery(root, folder, apply=True)
    assert result['mode'] == 'applied' and not duplicate.exists()
    assert distinct.read_bytes() == b'Historical different edit'
    assert (folder / 'entrega/titulo.txt').read_text().strip() == 'New Studio title'
    assert (folder / 'entrega/etiquetas.txt').read_text().strip() == 'terror, stickman'
    assert (folder / 'entrega/descripcion.txt').read_text() == '*CAPÍTULOS*\n00:00 Prueba\n'
    assert len(list(folder.rglob('*.mp4'))) == 3
    assert not normalize_delivery(root, folder)['duplicate_videos']


def test_normalize_rejects_edited_legacy_delivery_before_removing_sources(episode):
    from kitok.youtube_stickman_es.delivery import normalize_delivery
    root, folder = episode
    legacy_bundle(folder)
    (folder / 'entrega/descripcion.txt').write_text('Operator edit')
    with pytest.raises(ValueError, match='operator edits preserved'):
        normalize_delivery(root, folder, apply=True)
    assert (folder / 'video_final.mp4').exists()
    assert (folder / 'entrega/descripcion.txt').read_text() == 'Operator edit'


def test_bundle_removes_caption_work_duplicate_and_reuses_canonical_files(episode):
    root, folder = episode
    staged = folder / '.stickman/caption-work/done/video_subtitulado.mp4'
    staged.parent.mkdir(parents=True)
    os.link(folder / 'video_subtitulado.mp4', staged)
    compact_delivery(root, folder)
    assert not staged.exists()
    assert len(list(folder.rglob('*.mp4'))) == 2
    assert compact_delivery(root, folder)['files'] == 8
    assert clean_visual_cache(root, folder)['mode'] == 'dry_run'


def test_pending_delivery_receipt_recovers_after_publication_interruption(episode, monkeypatch):
    from kitok.youtube_stickman_es import files
    root, folder = episode
    original = files.replace_state
    def fail_final_receipt(path, value):
        if path.name == 'delivery.json':
            raise OSError('Interrupted receipt publication')
        return original(path, value)
    monkeypatch.setattr(files, 'replace_state', fail_final_receipt)
    with pytest.raises(OSError, match='Interrupted receipt'):
        compact_delivery(root, folder)
    assert (folder / 'entrega/video_final.mp4').exists()
    assert (folder / 'video_final.mp4').exists()
    monkeypatch.setattr(files, 'replace_state', original)
    assert compact_delivery(root, folder)['files'] == 8
    assert not (folder / 'video_final.mp4').exists()
    assert not (folder / '.stickman/delivery-pending.json').exists()


def test_revision_can_deliver_to_its_parent_and_resolve_both_masters(episode):
    from kitok.youtube_stickman_es.delivery import normalize_delivery
    root, folder = episode
    parent = root / 'parent'
    revision = parent / 'revisiones/active'
    revision.parent.mkdir(parents=True)
    folder.rename(revision)
    legacy_bundle(revision)
    assert normalize_delivery(root, revision, destination_episode=parent)['mode'] == 'dry_run'
    result = normalize_delivery(root, revision, destination_episode=parent, apply=True)
    assert result['bundle']['delivery'] == 'parent/entrega'
    assert final_video(revision, 'video_final.mp4') == parent / 'entrega/video_final.mp4'
    assert final_video(revision, 'video_subtitulado.mp4') == parent / 'entrega/video_subtitulado.mp4'
    assert len(list(parent.rglob('*.mp4'))) == 2
    assert compact_delivery(root, revision)['files'] == 8
    other = root / 'unrelated'
    other.mkdir()
    with pytest.raises(ValueError, match='only to itself or its parent'):
        normalize_delivery(root, revision, destination_episode=other)


@pytest.mark.parametrize('change', ['title', 'description', 'tags', 'settings'])
def test_invalid_editorial_metadata_blocks_bundle_before_publication(episode, change):
    root, folder = episode
    value = {'title': 'Title', 'description': 'Description', 'tags': ['terror'], 'settings': {}}
    value[change] = {'title': 'x' * 101, 'description': '', 'tags': [123], 'settings': []}[change]
    path = folder / 'editorial/publicacion_youtube.json'
    path.parent.mkdir()
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='Editorial'):
        compact_delivery(root, folder)
    assert (folder / 'video_final.mp4').exists()
    assert not (folder / 'entrega').exists()


def test_bundle_respects_independent_renderer_lock_before_moving_videos(episode):
    root, folder = episode
    work = folder / '.editorial-work/job'
    work.mkdir(parents=True)
    with (work / 'render.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='render is running'):
            compact_delivery(root, folder)
    assert (folder / 'video_final.mp4').exists()
    assert not (folder / 'entrega').exists()


@pytest.mark.parametrize('legacy', [True, False])
def test_normalization_retry_accepts_matching_pending_receipt_over_previous_final(episode, monkeypatch, legacy):
    from kitok.youtube_stickman_es.delivery import normalize_delivery
    from kitok.youtube_stickman_es import files
    root, folder = episode
    if legacy:
        legacy_bundle(folder)
    else:
        compact_delivery(root, folder)
    override = folder / 'editorial/publicacion_youtube.json'
    override.parent.mkdir()
    override.write_text(json.dumps({'title': 'Updated title', 'description': 'Updated description', 'tags': ['terror']}))
    original = files.replace_state
    def interrupted(path, value):
        if path.name == 'delivery.json':
            raise OSError('Interrupted migration receipt')
        return original(path, value)
    monkeypatch.setattr(files, 'replace_state', interrupted)
    with pytest.raises(OSError, match='Interrupted migration receipt'):
        normalize_delivery(root, folder, apply=True)
    assert (folder / 'entrega/titulo.txt').read_text().strip() == 'Updated title'
    monkeypatch.setattr(files, 'replace_state', original)
    assert normalize_delivery(root, folder, apply=True)['mode'] == 'applied'
    assert compact_delivery(root, folder)['files'] == 8
    assert len(list(folder.rglob('*.mp4'))) == 2


@pytest.mark.parametrize('omit', ['credit', 'notice'])
def test_editorial_description_cannot_drop_actual_mix_attribution_or_change_notice(episode, omit):
    root, folder = episode
    mix = folder / '.stickman/mix-fixture.m4a'
    mix.write_bytes(b'actual music mix')
    render = json.loads((folder / 'video_final.editorial.json').read_text())
    render.update(audio_is_final_mix=True, audio_source='episode/.stickman/mix-fixture.m4a',
                  audio_source_sha256=sha256(mix))
    (folder / 'video_final.editorial.json').write_text(json.dumps(render))
    credit = 'Track - Author. CC BY 4.0: https://license.example/by Source: https://author.example/track'
    notice = 'Música recortada, enlazada y mezclada bajo la narración.'
    receipt = {'output_sha256': sha256(mix), 'selection': {'credits': [credit], 'changes_notice': 'Music edited.'},
               'sources': [{'source': {'license_id': 'CC-BY-4.0', 'attribution': credit}}]}
    Path(str(mix) + '.json').write_text(json.dumps(receipt))
    override = folder / 'editorial/publicacion_youtube.json'
    override.parent.mkdir()
    value = {'title': 'Title', 'description': credit if omit == 'notice' else notice, 'tags': ['terror']}
    override.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='music attribution|notice of the edits'):
        compact_delivery(root, folder)
    assert (folder / 'video_final.mp4').exists()
    assert not (folder / 'entrega').exists()
    value['description'] = credit + '\n' + notice
    override.write_text(json.dumps(value))
    assert compact_delivery(root, folder)['files'] == 8


def test_legacy_generated_description_keeps_existing_attribution_without_new_notice_requirement(episode):
    root, folder = episode
    mix = folder / '.stickman/mix-legacy.m4a'
    mix.write_bytes(b'legacy mix')
    render = json.loads((folder / 'video_final.editorial.json').read_text())
    render.update(audio_is_final_mix=True, audio_source='episode/.stickman/mix-legacy.m4a',
                  audio_source_sha256=sha256(mix))
    (folder / 'video_final.editorial.json').write_text(json.dumps(render))
    credit = 'Track - Author. CC BY 4.0: https://license.example/by Source: https://author.example/track'
    (folder / 'descripcion_youtube_final.txt').write_text('Legacy generated description\n' + credit)
    Path(str(mix) + '.json').write_text(json.dumps({
        'output_sha256': sha256(mix), 'selection': {'credits': [credit], 'changes_notice': 'Music edited.'},
        'sources': [{'source': {'license_id': 'CC-BY-4.0', 'attribution': credit}}]}))
    assert compact_delivery(root, folder)['files'] == 8


def test_directory_swap_crash_recovers_verified_backup_before_rebuilding_delivery(episode, monkeypatch):
    from kitok.youtube_stickman_es.delivery import normalize_delivery
    root, folder = episode
    compact_delivery(root, folder)
    override = folder / 'editorial/publicacion_youtube.json'
    override.parent.mkdir()
    override.write_text(json.dumps({'title': 'New title', 'description': 'New description', 'tags': ['terror']}))
    original = Path.rename
    def simulate_process_loss(path, target):
        if path.name.startswith('.delivery-') and target == folder / 'entrega':
            raise SystemExit('Process lost between directory renames')
        return original(path, target)
    monkeypatch.setattr(Path, 'rename', simulate_process_loss)
    with pytest.raises(SystemExit, match='between directory renames'):
        normalize_delivery(root, folder, apply=True)
    assert not (folder / 'entrega').exists()
    # Read-only callers can still locate validated bytes. They do not perform
    # recovery while another cooperative writer may own the production lease.
    assert final_video(folder, 'video_final.mp4').read_bytes() == b'approved clean video'
    assert normalize_delivery(root, folder)['mode'] == 'dry_run'
    assert not (folder / 'entrega').exists()
    monkeypatch.setattr(Path, 'rename', original)
    assert normalize_delivery(root, folder, apply=True)['mode'] == 'applied'
    assert (folder / 'entrega/titulo.txt').read_text() == 'New title\n'
    assert compact_delivery(root, folder)['files'] == 8
    assert len(list(folder.rglob('*.mp4'))) == 2


def test_interrupted_directory_swap_rejects_tampered_backup(episode, monkeypatch):
    from kitok.youtube_stickman_es.delivery import normalize_delivery
    root, folder = episode
    compact_delivery(root, folder)
    override = folder / 'editorial/publicacion_youtube.json'
    override.parent.mkdir()
    override.write_text(json.dumps({'title': 'New title', 'description': 'New description', 'tags': ['terror']}))
    original = Path.rename
    def process_loss(path, target):
        if path.name.startswith('.delivery-') and target == folder / 'entrega':
            raise SystemExit('Process lost')
        return original(path, target)
    monkeypatch.setattr(Path, 'rename', process_loss)
    with pytest.raises(SystemExit):
        normalize_delivery(root, folder, apply=True)
    monkeypatch.setattr(Path, 'rename', original)
    record = json.loads((folder / '.stickman/delivery-transaction.json').read_text())
    backup = folder / record['backup']
    (backup / 'titulo.txt').write_text('Unexpected edit after interruption')
    with pytest.raises(ValueError, match='backup hashes changed'):
        normalize_delivery(root, folder, apply=True)
    assert not (folder / 'entrega').exists()
    assert (backup / 'video_final.mp4').exists()
    assert (backup / 'video_subtitulado.mp4').exists()
