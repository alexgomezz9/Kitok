"""Provided image ownership and immutable revision snapshots, without providers."""
import json
from pathlib import Path

import pytest
from PIL import Image

from kitok.youtube_stickman_es.files import digest
from kitok.youtube_stickman_es.reuse import safe_revision, source_spans


@pytest.fixture
def provided(tmp_path):
    episode = tmp_path / 'episode'
    episode.mkdir()
    script = 'La primera escena.\n\nOtra escena final.'
    (episode / 'guion_lectura_limpia.txt').write_text(script)
    (episode / 'guion_final.txt').write_text('[calm] ' + script)
    (episode / 'titulo.txt').write_text('Título')
    (episode / 'configuracion.json').write_text(json.dumps({'references': [{'path': 'refs/interior.png'}]}))
    (episode / 'refs').mkdir()
    Image.new('RGB', (20, 12), 'red').save(episode / 'refs/interior.png')
    (episode / 'imagenes').mkdir()
    scenes = []
    for i, (start, end) in enumerate(((0, 18), (20, len(script)))):
        image = episode / f'imagenes/escena_{i + 1:03}.png'
        Image.new('RGB', (20, 12), ('red', 'blue')[i]).save(image)
        scenes.append({'id': f'original_{i}', 'source_char_start': start, 'source_char_end': end,
                       'narration': script[start:end], 'source_word_start': 9999,
                       'source_word_end': 0, 'estimated_start_seconds': 500,
                       'image_file': image.relative_to(episode).as_posix(),
                       'image_sha256': digest(image), 'visual_description_en': f'Scene {i}',
                       'scene_prompt': f'Original prompt {i}'})
    plan = {'script_source': 'guion_lectura_limpia.txt',
            'script_sha256': digest(episode / 'guion_lectura_limpia.txt'), 'scenes': scenes}
    (episode / 'plan_visual.json').write_text(json.dumps(plan))
    return tmp_path, episode, plan


def save_plan(episode, plan):
    (episode / 'plan_visual.json').write_text(json.dumps(plan))


def test_reuse_preserves_narrative_associations_ignoring_provisional_times(provided):
    _, episode, _ = provided
    spans = source_spans(episode, (episode / 'guion_final.txt').read_text())
    assert [(s['word_start'], s['word_end']) for s in spans] == [(0, 3), (3, 6)]
    assert [s['image_file'] for s in spans] == ['imagenes/escena_001.png', 'imagenes/escena_002.png']
    assert spans[1]['source_id'] == 'original_1'
    assert spans[1]['scene_prompt'] == 'Original prompt 1'


def test_legacy_plan_path(provided):
    _, episode, _ = provided
    (episode / 'planificacion_visual').mkdir()
    (episode / 'plan_visual.json').rename(episode / 'planificacion_visual/plan_visual_prevoz.json')
    assert len(source_spans(episode, (episode / 'guion_final.txt').read_text())) == 2


@pytest.mark.parametrize('mutation', ['hash', 'narration', 'gap', 'overlap', 'word_split',
                                       'missing_tail', 'duplicate_id', 'image_hash', 'escape', 'missing_image'])
def test_reuse_rejects_changed_or_ambiguous_inputs(provided, mutation):
    _, episode, plan = provided
    first, second = plan['scenes']
    if mutation == 'hash':
        plan['script_sha256'] = 'wrong'
    elif mutation == 'narration':
        first['narration'] = 'Another narration'
    elif mutation == 'gap':
        second['source_char_start'] = 25
        second['narration'] = (episode / 'guion_lectura_limpia.txt').read_text()[25:]
    elif mutation == 'overlap':
        second['source_char_start'] = 10
    elif mutation == 'word_split':
        first['source_char_end'] = 2
        first['narration'] = 'La'
        second['source_char_start'] = 4
    elif mutation == 'missing_tail':
        plan['scenes'].pop()
    elif mutation == 'duplicate_id':
        second['id'] = first['id']
    elif mutation == 'image_hash':
        first['image_sha256'] = 'wrong'
    elif mutation == 'escape':
        first['image_file'] = '../other.png'
    elif mutation == 'missing_image':
        (episode / first['image_file']).unlink()
    save_plan(episode, plan)
    with pytest.raises(ValueError):
        source_spans(episode, (episode / 'guion_final.txt').read_text())


def test_reuse_rejects_transcript_substitution(provided):
    _, episode, _ = provided
    with pytest.raises(ValueError, match='transcript'):
        source_spans(episode, 'La primera escena. Otra mentira final.')


def test_reuse_rejects_linked_image(provided):
    _, episode, plan = provided
    image = episode / plan['scenes'][0]['image_file']
    image.unlink()
    image.symlink_to(episode / 'refs/interior.png')
    with pytest.raises(ValueError, match='symlink'):
        source_spans(episode, (episode / 'guion_final.txt').read_text())


def test_revision_is_independent_atomic_and_resumable(provided):
    root, episode, _ = provided
    (episode / '.stickman').mkdir()
    (episode / '.stickman/narration.json').write_text('approved receipt')
    (episode / 'guia_estilo.md').write_text('generated style')
    (episode / 'personajes.json').write_text('{}')
    (episode / 'plan_imagenes.json').write_text('old generated plan')
    (episode / 'voz.mp3').write_bytes(b'original audio')
    before = {p.relative_to(episode): digest(p) for p in episode.rglob('*') if p.is_file()}
    revision = safe_revision(root, episode, 'alineada')
    assert revision == episode / 'revisiones/alineada'
    assert safe_revision(root, episode, 'alineada') == revision
    assert all(digest(episode / path) == value for path, value in before.items())
    assert (revision / 'voz.mp3').stat().st_ino != (episode / 'voz.mp3').stat().st_ino
    assert not (revision / '.stickman').exists()
    assert not (revision / 'guia_estilo.md').exists()
    assert not (revision / 'personajes.json').exists()
    assert not (revision / 'plan_imagenes.json').exists()
    (revision / 'plan_imagenes.json').write_text('new generated plan')
    assert safe_revision(root, episode, 'alineada') == revision


@pytest.mark.parametrize('location', ['source', 'snapshot'])
def test_revision_rejects_mutated_pinned_inputs(provided, location):
    root, episode, _ = provided
    revision = safe_revision(root, episode, 'alineada')
    ((episode if location == 'source' else revision) / 'guion_final.txt').write_text('changed')
    with pytest.raises(ValueError, match='changed'):
        safe_revision(root, episode, 'alineada')


@pytest.mark.parametrize('name', ['../unsafe', '.', 'bad/name', '', 'a' * 65])
def test_revision_rejects_unsafe_names(provided, name):
    root, episode, _ = provided
    with pytest.raises(ValueError, match='Revision'):
        safe_revision(root, episode, name)


def test_revision_rejects_symlink_folder(provided):
    root, episode, _ = provided
    (episode / 'revisiones').symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        safe_revision(root, episode, 'safe')


def test_failed_revision_does_not_publish_partial_snapshot(provided, monkeypatch):
    root, episode, _ = provided
    import kitok.youtube_stickman_es.reuse as reuse
    def fail(*args, **kwargs):
        raise OSError('copy interrupted')
    monkeypatch.setattr(reuse.shutil, 'copy2', fail)
    with pytest.raises(OSError, match='interrupted'):
        safe_revision(root, episode, 'safe')
    assert list((episode / 'revisiones').iterdir()) == []
