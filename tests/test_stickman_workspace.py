import fcntl
import json
from zipfile import ZipFile

import pytest

from kitok.youtube_stickman_es.delivery import sha256
from kitok.youtube_stickman_es.workspace import organize, DIRECTORIES


def test_archive_preserves_unique_media_deduplicates_inputs_and_is_repeatable(tmp_path):
    ep = tmp_path / 'episode'
    revision = ep / 'revisiones/old'
    work = revision / '.editorial-work/job'
    work.mkdir(parents=True)
    (ep / 'guion_final.txt').write_text('original')
    (revision / 'guion_final.txt').write_text('original')
    (revision / 'voz.mp3').write_bytes(b'unique paid voice')
    (revision / 'video_final.mp4').write_bytes(b'unique master')
    (work / 's0001_000000100.mp4').write_bytes(b'regenerable')
    before = sha256(revision / 'voz.mp3')
    report = organize(tmp_path, ep, archive_revisions=True)
    assert report['mode'] == 'dry_run' and revision.exists()
    assert not (ep / 'LEEME.md').exists()
    report = organize(tmp_path, ep, apply=True, archive_revisions=True)
    assert not revision.exists()
    assert (ep / 'entrega/old__video_final.mp4').read_bytes() == b'unique master'
    with ZipFile(tmp_path / report['archives'][0]) as z:
        receipt = json.loads(z.read('restauracion.json'))
        assert receipt['archived']['voz.mp3'] == before
        assert z.read('voz.mp3') == b'unique paid voice'
        assert 'guion_final.txt' in receipt['retained']
        assert '.editorial-work/job/s0001_000000100.mp4' not in z.namelist()
    assert all((ep / name).is_dir() for name in DIRECTORIES)
    assert organize(tmp_path, ep, apply=True, archive_revisions=True)['archives'] == []


def test_active_lock_and_symlink_block_before_source_deletion(tmp_path):
    ep = tmp_path / 'episode'
    work = ep / '.editorial-work/job'
    work.mkdir(parents=True)
    source = work / 's0001_000000100.mp4'
    source.write_bytes(b'cache')
    with (work / 'render.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='render is running'):
            organize(tmp_path, ep, apply=True)
    (ep / 'link').symlink_to(source)
    with pytest.raises(ValueError, match='symlinks'):
        organize(tmp_path, ep, apply=True)
    assert source.read_bytes() == b'cache'


def test_source_referenced_cache_is_preserved(tmp_path):
    ep = tmp_path / 'episode'
    work = ep / '.editorial-work/job'
    work.mkdir(parents=True)
    source = work / 's0001_000000100.mp4'
    source.write_bytes(b'input')
    (ep / 'montaje.json').write_text(json.dumps({'path': str(source)}))
    assert not organize(tmp_path, ep, apply=True)['removed']
    assert source.exists()


def test_atlas_only_removed_after_final_png_hash_and_decode(tmp_path):
    from PIL import Image
    ep = tmp_path / 'episode'
    batch = ep / 'planificacion_visual/lotes_imagenes/batch'
    batch.mkdir(parents=True)
    (ep / 'imagenes').mkdir()
    final = ep / 'imagenes/escena_001.png'
    Image.new('RGB', (1280, 720)).save(final)
    atlas = batch / 'atlas.png'
    atlas.write_bytes(b'original sheet')
    receipt = {'scenes': [{'id': 'escena_001', 'state': 'accepted',
               'image_file': 'imagenes/escena_001.png', 'sha256': 'changed'}]}
    (batch / 'manifest.json').write_text(json.dumps(receipt))
    assert not organize(tmp_path, ep)['removed']
    receipt['scenes'][0]['sha256'] = sha256(final)
    (batch / 'manifest.json').write_text(json.dumps(receipt))
    assert len(organize(tmp_path, ep, apply=True)['removed']) == 1
    assert not atlas.exists() and final.exists()


def test_operator_index_and_unsafe_archive_destination_preserved(tmp_path):
    ep = tmp_path / 'episode'
    ep.mkdir()
    (ep / 'LEEME.md').write_text('operator notes')
    with pytest.raises(ValueError, match='operator LEEME'):
        organize(tmp_path, ep, apply=True)
    assert (ep / 'LEEME.md').read_text() == 'operator notes'


def test_unreviewed_repair_sheet_is_not_resolved_by_another_batch(tmp_path):
    from PIL import Image
    ep = tmp_path / 'episode'
    (ep / 'imagenes').mkdir(parents=True)
    final = ep / 'imagenes/escena_001.png'
    Image.new('RGB', (1280, 720)).save(final)
    for name, state in [('approved', 'accepted'), ('repair', 'cropped_unreviewed')]:
        batch = ep / 'planificacion_visual/lotes_imagenes' / name
        batch.mkdir(parents=True)
        (batch / 'atlas.png').write_bytes(name.encode())
        (batch / 'manifest.json').write_text(json.dumps({'scenes': [{
            'id': 'escena_001', 'state': state,
            'image_file': 'imagenes/escena_001.png', 'sha256': sha256(final)}]}))
    result = organize(tmp_path, ep, apply=True)
    assert len(result['removed']) == 1
    assert (ep / 'planificacion_visual/lotes_imagenes/repair/atlas.png').exists()


def test_active_atlas_and_referenced_revision_paths_survive(tmp_path):
    from PIL import Image
    ep = tmp_path / 'episode'
    batch = ep / 'planificacion_visual/lotes_imagenes/batch'
    batch.mkdir(parents=True)
    (ep / 'imagenes').mkdir()
    final = ep / 'imagenes/escena_001.png'
    Image.new('RGB', (1280, 720)).save(final)
    atlas = batch / 'atlas.png'
    atlas.write_bytes(b'active source')
    (batch / 'manifest.json').write_text(json.dumps({'scenes': [{
        'id': 'escena_001', 'state': 'accepted',
        'image_file': 'imagenes/escena_001.png', 'sha256': sha256(final)}]}))
    (ep / 'montaje.json').write_text(json.dumps({'path': str(atlas)}))
    assert not organize(tmp_path, ep, apply=True)['removed']
    revision = ep / 'revisiones/old/imagenes'
    revision.mkdir(parents=True)
    source = revision / 'source.png'
    source.write_bytes(b'active revision image')
    (ep / 'configuracion.json').write_text(json.dumps({'path': str(source)}))
    with pytest.raises(ValueError, match='current input references'):
        organize(tmp_path, ep, apply=True, archive_revisions=True)
    assert source.exists() and atlas.exists()
