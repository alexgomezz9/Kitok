"""Storyboard coverage, existing batch contract and real-clock preservation."""
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

from PIL import Image
import pytest

from kitok.youtube_stickman_es.files import digest
from kitok.youtube_stickman_es.models import Config
from kitok.youtube_stickman_es.planner import plan_illustrations
from kitok.youtube_stickman_es.reuse import source_spans
from kitok.youtube_stickman_es.storyboard import PLAN, build, check, main


def beat(text, **kwargs):
    return {'narration': text, 'visual_description': 'Una llave abandonada frente a una puerta cerrada.',
            'scene_prompt': 'Close-up of one iron key on a cream floor in front of a locked wooden door.', **kwargs}


@pytest.fixture
def episode(tmp_path):
    ep = tmp_path/'episode'
    ep.mkdir()
    (ep/'guion_final.txt').write_text('¿No volvió? En 1978 comenzó la búsqueda.', encoding='utf-8')
    (ep/'configuracion.json').write_text(json.dumps(Config(characters={'ana': 'Short curly hair, blue coat.'}).model_dump()))
    return ep


def decisions():
    return [beat('¿No volvió?', visual_type='question', display_text='¿No volvió?', camera='static'),
            beat('En 1978 comenzó la búsqueda.', visual_type='date', display_text='1978', characters=['ana'])]


def test_full_plan_is_exact_batch_input_and_has_no_fictitious_times(episode):
    build(episode, decisions())
    plan = json.loads((episode/PLAN).read_text())
    assert check(episode)['coverage'] == 'complete'
    assert check(episode, timing=True)['timing'] == 'pending_real_alignment'
    text = (episode/plan['script_source']).read_text()
    assert plan['script_sha256'] == digest(episode/plan['script_source'])
    for i, scene in enumerate(plan['scenes'], 1):
        assert scene['narration'] == text[scene['source_char_start']:scene['source_char_end']]
        assert scene['id'] == f'escena_{i:03d}'
        assert scene['image_file'] == f'imagenes/{scene["id"]}.png'
        assert not {'start', 'end', 'estimated_start_seconds'} & scene.keys()
    assert 'Short curly hair' not in plan['scenes'][0]['scene_prompt']
    assert 'Short curly hair' in plan['scenes'][1]['scene_prompt']
    assert 'Intentional visible text ONLY: "1978"' in plan['scenes'][1]['scene_prompt']
    # Production still demands actual images.
    with pytest.raises(ValueError, match='Missing episode resource'):
        source_spans(episode, text)


def test_through_quotes_calculate_all_offsets_without_repeating_script(episode):
    items = decisions()
    for item in items:
        item['through'] = item.pop('narration').split(' ', 1)[-1]
    build(episode, items)
    assert [s['narration'] for s in json.loads((episode/PLAN).read_text())['scenes']] == [x['narration'] for x in decisions()]


@pytest.mark.parametrize('mutation', ['gap', 'tail', 'substitution', 'split', 'character', 'duplicate_character',
                                      'ambiguous', 'timestamp', 'camera'])
def test_bad_decisions_do_not_publish(episode, mutation):
    items = decisions()
    if mutation == 'gap': items[0]['narration'] = 'volvió?'
    elif mutation == 'tail': items.pop()
    elif mutation == 'substitution': items[0]['narration'] = '¿Sí volvió?'
    elif mutation == 'split': items[0]['narration'] = '¿No vol'
    elif mutation == 'character': items[0]['characters'] = ['unknown']
    elif mutation == 'duplicate_character': items[0]['characters'] = ['ana', 'ana']
    elif mutation == 'ambiguous':
        (episode/'guion_final.txt').write_text('¿No volvió? ¿No volvió?')
        items = [beat(None, through='volvió?')]; items[0].pop('narration')
    elif mutation == 'timestamp': items[0]['start'] = 0
    else: items[0]['camera'] = 'invented_camera'
    with pytest.raises(ValueError): build(episode, items)
    assert not (episode/PLAN).exists()


def test_tags_unicode_negation_and_newlines_survive(episode):
    script = '[calm] ¿Él no pagó £50?\n\nPagó 5,50 euros.\n'
    (episode/'guion_final.txt').write_text(script)
    build(episode, [beat('¿Él no pagó £50?'), beat('Pagó 5,50 euros.')])
    assert (episode/'guion_final.txt').read_text() == script
    assert check(episode)['coverage'] == 'complete'
    assert json.loads((episode/PLAN).read_text())['script_source'] == 'guion_lectura_limpia.txt'


def test_preserve_outputs_idempotence_and_hash_drift(episode):
    build(episode, decisions())
    before = digest(episode/PLAN)
    build(episode, decisions())
    items = decisions(); items[0]['scene_prompt'] += ' The door is dark red.'
    with pytest.raises(FileExistsError): build(episode, items)
    assert digest(episode/PLAN) == before
    (episode/'guion_final.txt').write_text('Otra historia.')
    with pytest.raises(ValueError, match='hash'): check(episode)


def test_config_change_cannot_silently_change_character_identity(episode):
    build(episode, decisions())
    config = json.loads((episode/'configuracion.json').read_text()); config['characters']['ana'] = 'Changed identity'
    (episode/'configuracion.json').write_text(json.dumps(config))
    with pytest.raises(ValueError, match='config changed'): check(episode)


@pytest.mark.parametrize('path', ['../outside.json', '/tmp/outside.json', 'planificacion_visual/storyboard.json'])
def test_output_escape_is_rejected(episode, path):
    with pytest.raises(ValueError): build(episode, decisions(), output=path)


def test_symlink_output_and_shadow_plan_are_rejected(episode):
    (episode/'planificacion_visual').symlink_to(episode.parent, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'): build(episode, decisions())
    (episode/'planificacion_visual').unlink()
    (episode/'plan_visual.json').write_text('operator plan')
    with pytest.raises(ValueError, match='precedence'): build(episode, decisions())


def test_real_clock_retains_fast_editorial_intro_and_camera(episode):
    text = ' '.join(f'palabra{i}.' for i in range(180))
    (episode/'guion_final.txt').write_text(text)
    # Same real-word fixture, deliberate 2s / 3s / 5s editorial beats.
    groups = [(i, i+2) for i in range(0, 30, 2)] + [(i, i+3) for i in range(30, 60, 3)] + [(i, i+5) for i in range(60, 180, 5)]
    items = [beat(' '.join(text.split()[a:b]), camera='pan_up') for a, b in groups]
    build(episode, items)
    spans = source_spans(episode, text, require_images=False)
    words = [{'word': f'palabra{i}', 'start': i, 'end': i+.8} for i in range(180)]
    plan = plan_illustrations(episode, title='Timing fixture', script=text, config=Config(), source_spans=spans,
                             narration={'words': words, 'duration': 180, 'audio_sha256': 'a', 'srt_sha256': 's'})
    assert len(plan.scenes) == len(groups)
    assert [s.end-s.start for s in plan.scenes[:15]] == [2]*15
    assert [s.end-s.start for s in plan.scenes[15:25]] == [3]*10
    assert [s.end-s.start for s in plan.scenes[25:]] == [5]*24
    assert all(s.camera.preset == 'pan_up' for s in plan.scenes)
    assert all(s.start*30 == round(s.start*30) for s in plan.scenes)


def test_batch_prompt_deduplicates_only_exact_shared_context(episode):
    build(episode, decisions())
    script = Path(__file__).parents[1]/'.agents/skills/kitok-image-batches/scripts/batches.py'
    spec = importlib.util.spec_from_file_location('storyboard_batch_test', script)
    batch = importlib.util.module_from_spec(spec); spec.loader.exec_module(batch)
    Image.new('RGB', (80, 45), 'red').save(episode/'anchor.png')
    result = batch.plan(episode.resolve(), SimpleNamespace(plan=PLAN, start='escena_001', count=2,
        columns=3, batch='proof', reference=['anchor.png'], anchor='anchor.png'))
    prompt = Path(result['prompt']).read_text()
    config = Config.model_validate_json((episode/'configuracion.json').read_text())
    assert prompt.count(config.style_prompt) == 1
    assert prompt.count(config.characters['ana']) == 1
    assert 'CELL 3: empty neutral blank panel' in prompt
    manifest = json.loads(Path(result['manifest']).read_text())
    assert manifest['generation_tool'] == 'not_run'
    assert manifest['references'] == ['anchor.png']
    assert manifest['scenes'][0]['scene_prompt'] == json.loads((episode/PLAN).read_text())['scenes'][0]['scene_prompt']
    assert 'Intentional visible text ONLY: "1978"' in prompt
    assert not (episode/'imagenes').exists()


def test_default_style_survives_batch_compaction(episode):
    (episode/'configuracion.json').write_text('{}')
    build(episode, [beat('¿No volvió?'), beat('En 1978 comenzó la búsqueda.')])
    script = Path(__file__).parents[1]/'.agents/skills/kitok-image-batches/scripts/batches.py'
    spec = importlib.util.spec_from_file_location('default_style_batch_test', script)
    batch = importlib.util.module_from_spec(spec); spec.loader.exec_module(batch)
    Image.new('RGB', (80, 45), 'red').save(episode/'anchor.png')
    result = batch.plan(episode.resolve(), SimpleNamespace(plan=PLAN, start='escena_001', count=2,
        columns=3, batch='proof', reference=[], anchor='anchor.png'))
    assert Path(result['prompt']).read_text().count(Config().style_prompt) == 1


def test_timing_audit_is_read_only_and_uses_measured_audio(episode):
    build(episode, decisions())
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=300:duration=6',
                    '-c:a', 'libmp3lame', str(episode/'voz.mp3')], check=True)
    tokens = ['No', 'volvió', 'En', '1978', 'comenzó', 'la', 'búsqueda']
    alignment = {'method': 'fish_provider_timestamps', 'words': [
        {'word': token, 'start': i*.8, 'end': i*.8+.5} for i, token in enumerate(tokens)]}
    (episode/'voz.alignment.json').write_text(json.dumps(alignment))
    before = {p.relative_to(episode): digest(p) for p in episode.rglob('*') if p.is_file()}
    result = check(episode, timing=True)
    assert result['mapping'][0]['end'] == 1.6
    assert result['mapping'][1]['source_id'] == 'escena_002'
    assert result['acoustic_sync_verified'] is False
    assert result['audio_sha256'] == digest(episode/'voz.mp3')
    assert before == {p.relative_to(episode): digest(p) for p in episode.rglob('*') if p.is_file()}


def test_cli_errors_and_context_do_not_generate(episode, capsys):
    assert main(['context', str(episode)]) == 0
    assert json.loads(capsys.readouterr().out)['script'].startswith('¿No')
    assert main(['check', str(episode)]) == 2
    output = capsys.readouterr()
    assert output.out == ''
    assert json.loads(output.err)['status'] == 'blocked'
