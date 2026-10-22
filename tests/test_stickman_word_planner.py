"""Real lexical boundaries, global feasibility, and approved image ownership."""
import math

import pytest

from kitok.youtube_stickman_es.audio import _tokens
from kitok.youtube_stickman_es.models import Config
from kitok.youtube_stickman_es.planner import plan_illustrations


def plan(tmp_path, starts, *, duration, script=None, config=None, source_spans=None, ends=None):
    script = script or ' '.join(f'palabra{i}' for i in range(len(starts)))
    (tmp_path / 'guion_final.txt').write_text(script)
    words = [{'word': token, 'start': start, 'end': end}
             for token, start, end in zip(_tokens(script), starts, ends if ends is not None else starts)]
    narration = {'duration': duration, 'words': words,
                 'cues': [{'start': 0, 'end': duration, 'text': script}],
                 'audio_sha256': 'a', 'srt_sha256': 's', 'alignment_method': 'coarse_srt'}
    return plan_illustrations(tmp_path, title='Prueba', script=script, narration=narration,
                              config=config or Config(), source_spans=source_spans)


def source(first, last, image='imagenes/original.png', **options):
    return {'word_start': first, 'word_end': last, 'image_file': image,
            'visual_description': 'Un personaje investiga una máquina detenida.',
            'scene_prompt': 'An expressive stick figure investigates the original stationary machine.',
            **options}


def assert_coverage(result, tokens, maximum=8):
    assert _tokens(' '.join(s.narration for s in result.scenes)) == tokens
    assert result.scenes[0].start == 0
    assert result.scenes[-1].end == result.duration
    assert all(a.end == b.start for a, b in zip(result.scenes, result.scenes[1:]))
    assert all(.4-1e-9 <= s.end-s.start <= maximum+1e-9 for s in result.scenes)
    assert all(abs(t*30-round(t*30)) < 1e-6 for s in result.scenes for t in (s.start, s.end))


def test_bursty_words_override_coarse_srt_and_cover_every_token(tmp_path):
    starts = [0, .05, .1, .1, 4, 4.03, 4.06, 9, 9.03, 9.06, 14, 14.02]
    result = plan(tmp_path, starts, duration=16.007)
    assert len(result.scenes) == 3
    assert result.timing_method == 'fish_provider_word_timestamps_full_transcript'
    assert result.duration == math.ceil(16.007*30)/30
    assert_coverage(result, [f'palabra{i}' for i in range(len(starts))])
    for scene in result.scenes[1:]:
        assert min(abs(scene.start-t) for t in starts) <= 1/60 + 1e-9


def test_global_path_avoids_nearest_cut_dead_end(tmp_path):
    # Nearest uniform cuts 7, 9 make a nine-second final scene. The feasible
    # three-scene path 7, 14 requires looking beyond the nearest next cut.
    result = plan(tmp_path, [0, 7, 9, 14], duration=18,
                  config=Config(target_scene_seconds=7, max_scene_seconds=8))
    assert [s.start for s in result.scenes] == [0, 7, 14]
    assert len(result.scenes) == 3
    assert_coverage(result, ['palabra0', 'palabra1', 'palabra2', 'palabra3'])


def test_count_changes_when_target_count_is_infeasible(tmp_path):
    result = plan(tmp_path, [0, 4, 8], duration=12,
                  config=Config(target_scene_seconds=7, max_scene_seconds=5))
    assert len(result.scenes) == 3
    assert_coverage(result, ['palabra0', 'palabra1', 'palabra2'], maximum=5)


def test_zero_duration_words_and_duplicate_starts_are_retained(tmp_path):
    result = plan(tmp_path, [0, 0, 0, 5, 5, 5], duration=10)
    assert_coverage(result, [f'palabra{i}' for i in range(6)])
    assert len(result.scenes) == 2


def test_long_gap_is_rejected_without_interpolation(tmp_path):
    with pytest.raises(ValueError, match=r'0.100s and 10.000s.*9.900s; maximum 8s'):
        plan(tmp_path, [0, .1, 10, 10.1], duration=12)


def test_long_gap_reports_original_image_and_absolute_clock(tmp_path):
    spans = [source(0, 2, 'imagenes/intro.png'),
             source(2, 5, 'imagenes/068.png', source_id='escena_068')]
    with pytest.raises(ValueError) as caught:
        plan(tmp_path, [0, 2, 4, 5, 16], duration=18, source_spans=spans)
    message = str(caught.value)
    assert 'Source scene escena_068 (imagenes/068.png)' in message
    assert '5.000s and 16.000s (11.000s; maximum 8s)' in message
    assert 'timestamp gap does not prove silence' in message
    assert 'Paid voice was preserved' in message


@pytest.mark.parametrize('spans', [[], [source(1, 4)], [source(0, 2), source(1, 4)],
                                    [source(0, 2), source(3, 4)], [source(0, 3)],
                                    [source(0, 5)], [source(False, 4)]])
def test_invalid_source_coverage_fails(tmp_path, spans):
    with pytest.raises(ValueError, match='cover the full script'):
        plan(tmp_path, [0, 2, 4, 6], duration=8, source_spans=spans)


def test_approved_spans_preserve_number_image_and_semantics(tmp_path):
    spans = [source(0, 2, 'imagenes/uno.png'), source(2, 4, 'imagenes/dos.png')]
    result = plan(tmp_path, [0, 2, 4, 6], duration=8, source_spans=spans)
    assert len(result.scenes) == 2
    assert result.direction_complete
    assert [s.image_file for s in result.scenes] == [s['image_file'] for s in spans]
    assert all(s.scene_prompt == spans[0]['scene_prompt'] for s in result.scenes)
    assert_coverage(result, [f'palabra{i}' for i in range(4)])


def test_long_source_span_splits_using_same_approved_image(tmp_path):
    result = plan(tmp_path, [0, 3, 6, 9, 12, 15], duration=18,
                  source_spans=[source(0, 6)])
    assert len(result.scenes) == 4
    assert {s.image_file for s in result.scenes} == {'imagenes/original.png'}
    assert len({s.visual_description for s in result.scenes}) == 1
    assert result.direction_complete
    assert_coverage(result, [f'palabra{i}' for i in range(6)])


def test_short_source_span_is_not_reassigned_to_other_image(tmp_path):
    with pytest.raises(ValueError, match='shorter than'):
        plan(tmp_path, [0, .1, 5], duration=10,
             source_spans=[source(0, 1), source(1, 3)])


def test_characters_punctuation_and_negation_survive_word_splits(tmp_path):
    script = "¿Él no ganó? [pause] D'Ávila pagó 5,50 euros; ¡nunca £50!"
    tokens = _tokens(script)
    result = plan(tmp_path, [i for i in range(len(tokens))], duration=len(tokens),
                  script=script, config=Config(characters={'A': 'The same expressive figure'}),
                  source_spans=[source(0, len(tokens), characters=['A'])])
    assert all(s.characters == ['A'] for s in result.scenes)
    assert_coverage(result, tokens)
    assert '¿Él no ganó?' in ' '.join(s.narration for s in result.scenes)
    assert '£50!' in result.scenes[-1].narration


@pytest.mark.parametrize('start', [math.nan, math.inf, -1])
def test_invalid_word_times_fail(tmp_path, start):
    with pytest.raises(ValueError, match='finite monotonic'):
        plan(tmp_path, [0, start], duration=8)


def test_overlapping_words_are_rejected_even_with_monotonic_endpoints(tmp_path):
    with pytest.raises(ValueError, match='finite monotonic'):
        plan(tmp_path, [0, .5, 5], ends=[1, 2, 6], duration=10)


def test_subframe_duplicate_boundaries_cannot_create_zero_length_scene(tmp_path):
    starts = [0, .001, .016, .017, 4.999, 5.001, 10]
    result = plan(tmp_path, starts, duration=10)
    assert len(result.scenes) == 2
    assert result.scenes[1].start == 5
    # The last word has zero duration at the audio endpoint and must remain
    # in the final scene rather than creating an empty terminal scene.
    assert result.scenes[-1].narration.endswith('palabra6')
    assert_coverage(result, [f'palabra{i}' for i in range(len(starts))])


def test_rounding_up_cannot_grant_extra_frame_above_scene_maximum(tmp_path):
    with pytest.raises(ValueError, match='cannot satisfy'):
        plan(tmp_path, [0, 8.017], duration=16)


def test_source_span_collapsed_to_zero_frames_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='shorter than'):
        plan(tmp_path, [0, .001, 5], duration=10,
             source_spans=[source(0, 1), source(1, 3)])


def test_final_provider_word_keeps_existing_millisecond_duration_tolerance(tmp_path):
    result = plan(tmp_path, [0, 2], ends=[1, 4.0005], duration=4)
    assert result.duration == result.scenes[-1].end == 4
    assert_coverage(result, ['palabra0', 'palabra1'])
    with pytest.raises(ValueError, match='finite monotonic'):
        plan(tmp_path, [0, 2], ends=[1, 4.0011], duration=4)


@pytest.mark.parametrize(('starts', 'ends'), [([False, 2], [1, 3]), ([0, 2], [True, 3])])
def test_boolean_word_times_are_rejected(tmp_path, starts, ends):
    with pytest.raises(ValueError, match='finite monotonic'):
        plan(tmp_path, starts, ends=ends, duration=4)
