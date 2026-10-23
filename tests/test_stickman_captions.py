"""Script fidelity and real-clock caption behavior, including a libass render."""
from copy import deepcopy
import math
import re
import shutil
import subprocess

from PIL import Image, ImageChops, ImageFont
import pytest

from kitok.youtube_stickman_es.captions import write_captions


def aligned(script, *, step=.5, duration=.3):
    return [{'word': token, 'start': index * step, 'end': index * step + duration}
            for index, token in enumerate(re.findall(r'\w+', script))]


def test_display_is_uppercase_with_original_script_and_alignment_preserved(tmp_path):
    script = '¡Él NO mintió! ¿Qué ocurrió aquí? “Nada”, respondió.'
    words = aligned(script)
    original_words = deepcopy(words)
    result = write_captions(script, words, tmp_path / 'captions.ass')
    assert [g['text'] for g in result['groups']] == [
        '¡ÉL NO MINTIÓ!', '¿QUÉ OCURRIÓ AQUÍ?', '“NADA”, RESPONDIÓ.']
    assert [g['source_text'] for g in result['groups']] == [
        '¡Él NO mintió!', '¿Qué ocurrió aquí?', '“Nada”, respondió.']
    assert result['display_case'] == 'uppercase'
    assert words == original_words
    assert script == '¡Él NO mintió! ¿Qué ocurrió aquí? “Nada”, respondió.'
    assert [g['word_start'] for g in result['groups']] == [0, 3, 6]
    assert all(event['end'] > event['start'] for event in result['events'])
    ass = (tmp_path / 'captions.ass').read_text()
    assert 'PlayResX: 1920' in ass and 'PlayResY: 1080' in ass
    assert r'\k' not in ass and r'\t(' not in ass and r'\move(' not in ass
    assert result == write_captions(script, words, tmp_path / 'captions.ass')


def test_unicode_spanish_and_expanding_uppercase_keep_source_word_identity(tmp_path):
    script = '¡áéíóú üñ Straße!'
    result = write_captions(script, aligned(script), tmp_path / 'captions.ass')
    group = result['groups'][0]
    assert group['text'] == '¡ÁÉÍÓÚ ÜÑ STRASSE!'
    assert group['source_text'] == script
    assert group['lines'] == ['¡ÁÉÍÓÚ ÜÑ STRASSE!']
    assert {e['active_word'] for e in result['events']} == {0, 1, 2, None}
    ass = (tmp_path / 'captions.ass').read_text()
    assert r'{\1c&H00FFFF&\fscx110\fscy110}STRASSE' in ass


def test_real_intervals_gaps_and_zero_duration_words_never_invent_highlights(tmp_path):
    words = [{'word': 'Uno', 'start': .003, 'end': .109},
             {'word': 'dos', 'start': .2, 'end': .2},
             {'word': 'tres', 'start': .421, 'end': .579},
             {'word': 'cuatro', 'start': 4, 'end': 4.3}]
    result = write_captions('Uno dos tres cuatro.', words, tmp_path / 'captions.ass')
    highlighted = [e for e in result['events'] if e['active_word'] is not None]
    assert {e['active_word'] for e in highlighted} == {0, 2, 3}
    for event in highlighted:
        word = words[event['active_word']]
        assert word['start'] <= event['start'] < event['end'] <= word['end']
    assert any(e['active_word'] is None and e['start'] <= .3 < e['end']
               for e in result['events'])
    assert result['groups'][0]['end'] == pytest.approx(1.579)
    assert not any(e['start'] <= 2 < e['end'] for e in result['events'])


@pytest.mark.parametrize('instantaneous_count', [3, 6])
def test_instantaneous_initial_groups_remain_white_with_next_timed_word(tmp_path, instantaneous_count):
    tokens = ['Uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis'][:instantaneous_count] + ['final']
    script = ' '.join(tokens) + '.'
    words = [{'word': token, 'start': 0, 'end': 0} for token in tokens]
    words[-1]['end'] = .5
    output = tmp_path / 'captions.ass'
    result = write_captions(script, words, output)
    assert len(result['groups']) == 1
    assert result['groups'][0]['text'] == script.upper()
    assert result['groups'][0]['word_end'] == len(tokens)
    assert result['events'] == [
        {'group': 0, 'start': 0, 'end': .5, 'active_word': len(tokens) - 1},
        {'group': 0, 'start': .5, 'end': 1.5, 'active_word': None}]
    event = next(line for line in output.read_text().splitlines() if line.startswith('Dialogue:'))
    assert r'{\1c&HFFFFFF&\fscx100\fscy100}UNO\hDOS\hTRES' in event
    assert r'{\1c&H00FFFF&\fscx110\fscy110}FINAL' in event


def test_sub_centisecond_group_is_retained_without_fake_highlight(tmp_path):
    script = 'Uno dos tres cuatro.'
    words = [{'word': token, 'start': index * .001, 'end': index * .001}
             for index, token in enumerate(('Uno', 'dos', 'tres', 'cuatro'))]
    words[-1]['end'] = .5
    result = write_captions(script, words, tmp_path / 'captions.ass')
    assert [group['text'] for group in result['groups']] == [script.upper()]
    assert {event['active_word'] for event in result['events']} == {None, 3}
    assert all(event['start'] >= .003 for event in result['events'] if event['active_word'] == 3)


@pytest.mark.parametrize('mutate', [
    lambda w: w.pop(),
    lambda w: w[0].update(word='inventado'),
    lambda w: w[0].update(start=-1),
    lambda w: w[0].update(end=math.nan),
    lambda w: w[0].update(start=math.inf),
    lambda w: w[0].update(start=True),
    lambda w: w[1].update(start=.1),
    lambda w: w[0].update(end=-.1),
])
def test_invalid_transcript_or_timing_fails_before_output(tmp_path, mutate):
    words = aligned('Una prueba real.')
    mutate(words)
    with pytest.raises(ValueError):
        write_captions('Una prueba real.', words, tmp_path / 'captions.ass')
    assert not list(tmp_path.iterdir())


def test_long_token_is_wrapped_without_rewriting_or_horizontal_clipping(tmp_path):
    token = 'extraordinariamente' * 8
    result = write_captions(token + ' sí.', aligned(token + ' sí.'), tmp_path / 'captions.ass')
    group = result['groups'][0]
    assert len(group['lines']) > 1
    assert ''.join(group['lines']).replace(' ', '') == token.upper() + 'SÍ.'
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                              result['font_size'])
    assert all(font.getlength(line) <= 1920 * .82 * .92 for line in group['lines'])


def test_changed_output_is_preserved(tmp_path):
    output = tmp_path / 'captions.ass'
    output.write_text('Operator artifact')
    with pytest.raises(FileExistsError):
        write_captions('Hola.', aligned('Hola.'), output)
    assert output.read_text() == 'Operator artifact'


def test_ffmpeg_actual_highlight_gap_and_safe_placement(tmp_path):
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        pytest.skip('FFmpeg is required for actual libass rendering')
    # Braces and a literal \N must remain visible text, not ASS instructions.
    script = r'¿{Hola} \N adiós?'
    words = [{'word': 'Hola', 'start': 0, 'end': .3},
             {'word': 'N', 'start': .5, 'end': .7},
             {'word': 'adiós', 'start': .8, 'end': 1}]
    output = tmp_path / 'captions.ass'
    write_captions(script, words, output)
    ass = output.read_text()
    assert r'\{' in ass and r'\}' in ass and '\\\u2060' in ass
    result = subprocess.run([
        ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
        'color=c=0x303030:s=1920x1080:r=20:d=1', '-vf',
        f"ass=filename='{output}',select='eq(n,2)+eq(n,7)+eq(n,17)'",
        '-fps_mode', 'vfr', '-frames:v', '3', '-threads', '1',
        str(tmp_path / 'frame-%d.png')], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    frames = [Image.open(tmp_path / f'frame-{i}.png').convert('RGB') for i in (1, 2, 3)]
    yellow = [sum(count for count, (r, g, b) in image.getcolors(image.width * image.height)
                  if r > 190 and g > 190 and b < 80)
              for image in frames]
    assert yellow[0] > 100 and yellow[1] == 0 and yellow[2] > 100
    bounds = [ImageChops.difference(image, Image.new('RGB', image.size, image.getpixel((0, 0)))).getbbox()
              for image in frames]
    for left, top, right, bottom in bounds:
        assert left >= 1920 * .09 and right <= 1920 * .91
        assert 1080 * .65 < top < bottom < 1080 * .91
    # Enlargement is an immediate state change, with no bounce or translation
    # animation. Its extra width stays within the reserved safe-area headroom.
    assert max(right - left for left, _, right, _ in bounds) - min(
        right - left for left, _, right, _ in bounds) < 1920 * .05


def test_ffmpeg_active_word_is_yellow_and_about_ten_percent_larger(tmp_path):
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        pytest.skip('FFmpeg is required for actual libass rendering')
    output = tmp_path / 'growth.ass'
    result = write_captions('Creció', [{'word': 'Creció', 'start': 0, 'end': .5}], output)
    assert result['active_word_scale'] == 1.1
    assert result['display_case'] == 'uppercase'
    assert result['groups'][0]['text'] == 'CRECIÓ'
    assert result['groups'][0]['source_text'] == 'Creció'
    assert 'CRECIÓ' in output.read_text() and 'Creció' not in output.read_text()
    rendered = subprocess.run([
        ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
        'color=black:s=1920x1080:r=10:d=1', '-vf',
        f"ass=filename='{output}',select='eq(n,2)+eq(n,8)'",
        '-fps_mode', 'vfr', '-frames:v', '2', '-threads', '1',
        str(tmp_path / 'growth-%d.png')], capture_output=True, text=True, timeout=30)
    assert rendered.returncode == 0, rendered.stderr
    active = Image.open(tmp_path / 'growth-1.png').convert('RGB')
    inactive = Image.open(tmp_path / 'growth-2.png').convert('RGB')
    # Both colors have high green; using that channel measures glyph geometry
    # without treating the yellow/white color change as apparent enlargement.
    active_box = active.getchannel('G').point(lambda p: 255 if p > 190 else 0).getbbox()
    inactive_box = inactive.getchannel('G').point(lambda p: 255 if p > 190 else 0).getbbox()
    active_width, active_height = active_box[2] - active_box[0], active_box[3] - active_box[1]
    inactive_width = inactive_box[2] - inactive_box[0]
    inactive_height = inactive_box[3] - inactive_box[1]
    assert 1.06 < active_width / inactive_width < 1.16
    assert 1.06 < active_height / inactive_height < 1.16
    yellow_counts = [sum(count for count, (r, g, b) in frame.getcolors(frame.width * frame.height)
                         if r > 190 and g > 190 and b < 80) for frame in (active, inactive)]
    assert yellow_counts[0] > 100 and yellow_counts[1] == 0
