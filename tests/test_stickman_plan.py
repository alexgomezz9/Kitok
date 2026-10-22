"""Real cue boundaries and immutable editorial inputs for stickman planning."""
from __future__ import annotations

import math

import pytest
from PIL import Image

from kitok.youtube_stickman_es.files import digest
from kitok.youtube_stickman_es.models import Config, IllustrationPlan
from kitok.youtube_stickman_es.planner import combined_prompt, plan_illustrations, write_plan


@pytest.fixture
def planning(tmp_path):
    script = '¿No ocurrió? El narrador no atribuye esta cifra a nadie.\n'
    (tmp_path / 'guion_final.txt').write_text(script, encoding='utf-8')
    cues = [{'start': i * 2., 'end': (i + 1) * 2., 'text': f'Frase {i}.'} for i in range(300)]
    narration = {'cues': cues, 'duration': 600., 'audio_sha256': 'audio',
                 'srt_sha256': 'srt', 'alignment_method': 'supplied_real_srt'}
    return tmp_path, script, narration, Config()


def make_plan(planning, **options):
    root, script, narration, config = planning
    return plan_illustrations(root, title='Título aprobado', script=script,
                              narration=narration, config=config, **options)


def directions_for(plan):
    return [{'scene_id': scene.id,
             'visual_description': 'Un personaje observa una máquina detenida.',
             'scene_prompt': 'An anonymous stick figure watches the supplied stationary mechanism.',
             'characters': []} for scene in plan.scenes]


def test_ten_minutes_uses_120_scenes_with_real_cue_boundaries(planning):
    plan = make_plan(planning)
    assert len(plan.scenes) == 120
    assert plan.duration == plan.narration_duration == 600
    assert plan.timing_method == 'supplied_real_srt'
    assert not plan.direction_complete
    assert plan.scenes[0].start == 0 and plan.scenes[-1].end == 600
    assert all(a.end == b.start for a, b in zip(plan.scenes, plan.scenes[1:]))
    boundaries = {round(c['start'] * 30) / 30 for c in planning[2]['cues']}
    assert all(s.start in boundaries for s in plan.scenes)
    assert all(4 <= s.end - s.start <= 6 for s in plan.scenes)
    assert ' '.join(s.narration for s in plan.scenes) == ' '.join(c['text'] for c in planning[2]['cues'])


def test_quantization_preserves_voice_tail_and_exact_frame_clock(planning):
    planning[2]['duration'] = 600.007
    plan = make_plan(planning)
    assert plan.duration == math.ceil(600.007 * 30) / 30
    assert 0 <= plan.duration - plan.narration_duration < 1 / 30
    assert all(abs(t * 30 - round(t * 30)) < 1e-6 for s in plan.scenes for t in (s.start, s.end))


@pytest.mark.parametrize('cues', [
    [{'start': 0., 'end': 600., 'text': 'Toda la voz.'}],
    [{'start': i * 9., 'end': (i + 1) * 9., 'text': 'Frase.'} for i in range(120)],
])
def test_coarse_alignment_fails_instead_of_inventing_timestamps(planning, cues):
    planning[2]['cues'] = cues
    with pytest.raises(ValueError, match='coarse|too long'):
        make_plan(planning)


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'unknown', 'character'])
def test_direction_requires_exact_scene_identity_and_known_characters(planning, mutation):
    directions = directions_for(make_plan(planning))
    if mutation == 'missing':
        directions.pop()
    elif mutation == 'duplicate':
        directions.append(directions[0])
    elif mutation == 'unknown':
        directions[0]['scene_id'] = 's9999_999999999'
    else:
        directions[0]['characters'] = ['Undefined character']
    with pytest.raises(ValueError, match='every planned scene|unknown character'):
        make_plan(planning, directions=directions)


def test_completed_plan_preserves_script_references_and_separate_prompts(planning):
    root, script, _, config = planning
    Image.new('RGB', (20, 20), 'red').save(root / 'interior.png')
    Image.new('RGB', (20, 20), 'blue').save(root / 'thumbnail.png')
    from kitok.youtube_stickman_es.models import Reference
    config.references = [Reference(path='interior.png', role='interior'),
                         Reference(path='thumbnail.png', role='thumbnail')]
    draft = make_plan(planning)
    plan = make_plan(planning, directions=directions_for(draft))
    assert plan.direction_complete
    assert plan.script_sha256 == digest(root / 'guion_final.txt')
    assert plan.config_sha256 == digest(config.model_dump())
    assert plan.references[0]['sha256'] == digest(root / 'interior.png')
    assert all(s.reference_files == ['interior.png'] for s in plan.scenes)
    prompt = combined_prompt(plan.scenes[0], config)
    assert all(label in prompt for label in ('STYLE PROMPT', 'SCENE PROMPT', 'VISUAL DESCRIPTION'))
    assert plan.scenes[0].narration in prompt
    write_plan(root, plan)
    assert (root / 'guion_final.txt').read_text() == script
    assert IllustrationPlan.model_validate_json((root / 'plan_imagenes.json').read_text()) == plan
    assert 'SCENE PROMPT' in (root / 'plan_imagenes.md').read_text()


@pytest.mark.parametrize('mutation', ['gap', 'frame', 'duplicate', 'tail'])
def test_plan_model_rejects_invalid_timeline(planning, mutation):
    data = make_plan(planning).model_dump()
    if mutation == 'gap':
        data['scenes'][1]['start'] += 1 / 30
    elif mutation == 'frame':
        data['scenes'][0]['end'] += .001
        data['scenes'][1]['start'] += .001
    elif mutation == 'duplicate':
        data['scenes'][1]['id'] = data['scenes'][0]['id']
    else:
        data['duration'] += 1 / 30
    with pytest.raises(ValueError):
        IllustrationPlan.model_validate(data)


def test_missing_semantic_direction_cannot_be_generated(planning):
    with pytest.raises(ValueError, match='Specific visual direction'):
        combined_prompt(make_plan(planning).scenes[0], planning[3])


def test_fractional_real_boundaries_round_to_nearest_shared_frame(planning):
    for cue in planning[2]['cues'][1:]:
        cue['start'] += .019
    plan = make_plan(planning)
    starts = [cue['start'] for cue in planning[2]['cues']]
    assert any(abs(s.start - round(s.start)) > .01 for s in plan.scenes[1:])
    for scene in plan.scenes[1:]:
        assert min(abs(scene.start - t) for t in starts) <= 1 / 60 + 1e-6
    assert all(a.end == b.start for a, b in zip(plan.scenes, plan.scenes[1:]))
