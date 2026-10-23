"""Optional, deterministic ASS captions from the script and real word timing.

No karaoke fill or estimated word duration: words with zero duration remain
white. Active words immediately become yellow and 110% size; there is no
transition animation. ASS highlight intervals are rounded inward to centiseconds.
"""
from __future__ import annotations

import math
from pathlib import Path
import re

from PIL import ImageFont

from .files import write
from .planner import _word_inputs


_WHITE = r'{\1c&HFFFFFF&\fscx100\fscy100}'
_YELLOW = r'{\1c&H00FFFF&\fscx110\fscy110}'
_OPENING = '¿¡“«([{' + '"'


def _escape(text: str) -> str:
    # A zero-width word joiner prevents a literal backslash from becoming an
    # ASS escape (notably user text containing \N, \h or an override tag).
    return text.replace('\\', '\\\u2060').replace('{', r'\{').replace('}', r'\}')


def _stamp(centiseconds: int) -> str:
    seconds, fraction = divmod(centiseconds, 100)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours}:{minutes:02d}:{seconds:02d}.{fraction:02d}'


def _wrap(chars: list[tuple[str, int | None]], font, maximum: int):
    """Keep punctuation and word identity while breaking measured long tokens."""
    lines: list[list[tuple[str, int | None]]] = []
    current: list[tuple[str, int | None]] = []
    for char in chars:
        if font.getlength(''.join(c for c, _ in current) + char[0]) > maximum:
            spaces = [i for i, (c, _) in enumerate(current) if c == ' ']
            if spaces:
                cut = spaces[-1]
                lines.append(current[:cut])
                current = current[cut + 1:]
            elif current:
                lines.append(current)
                current = []
        current.append(char)
    if current:
        lines.append(current)
    return lines


def _render(lines, active: int | None) -> str:
    result = []
    color = None
    for line_index, line in enumerate(lines):
        if line_index:
            result.append(r'\N')
        for char, word_index in line:
            wanted = active is not None and word_index == active
            if color != wanted:
                result.append(_YELLOW if wanted else _WHITE)
                color = wanted
            result.append(r'\h' if char == ' ' else _escape(char))
    return ''.join(result)


def write_captions(script: str, words: list[dict], output: Path, *,
                   width: int = 1920, height: int = 1080,
                   words_per_group: int = 3) -> dict:
    """Write immutable ASS and return JSON-safe provenance/layout metadata.

    ``words`` must cover the entire narration, with the same lexical tokens as
    the script and finite, ordered, nonoverlapping start/end timestamps. The
    caller supplies real narration alignment; this function does not obtain or
    infer timing. Display text uses Unicode uppercase and normalized whitespace;
    original script spelling and punctuation remain in ``source_text`` metadata.
    Instantaneous groups merge forward so
    words are retained without inventing highlight time. Existing changed
    output is preserved.
    """
    if (isinstance(width, bool) or not isinstance(width, int) or width < 320
            or isinstance(height, bool) or not isinstance(height, int) or height < 180
            or isinstance(words_per_group, bool) or not isinstance(words_per_group, int)
            or not 1 <= words_per_group <= 12):
        raise ValueError('Invalid caption dimensions or words_per_group (1 to 12)')
    # _word_inputs is shared with the scene planner; use its full-transcript and
    # real-clock validation without fabricating an extra narration duration.
    try:
        measured = max(float(word['end']) for word in words)
    except (TypeError, KeyError, ValueError, OverflowError):
        raise ValueError('Captions require finite real word timestamps') from None
    text, _, _ = _word_inputs(script, words, measured)
    if any(ord(c) < 32 and not c.isspace() for c in text):
        raise ValueError('Caption script contains control characters')
    matches = list(re.finditer(r'\w+', text))

    def boundary(index):
        if index == 0:
            return 0
        if index == len(matches):
            return len(text)
        boundary = matches[index].start()
        while boundary > 0 and text[boundary - 1] in _OPENING:
            boundary -= 1
        return boundary

    ranges = []
    first = 0
    for last in range(words_per_group, len(words), words_per_group):
        start = float(words[first]['start'])
        end = min(float(words[last - 1]['end']) + 1.0, float(words[last]['start']))
        # An ASS event needs a nonempty centisecond interval. Keep such a
        # group's original tokens with the next visible group, instead of
        # dropping them or manufacturing positive word durations.
        if math.ceil(start * 100 - 1e-9) < math.floor(end * 100 + 1e-9):
            ranges.append((first, last))
            first = last
    ranges.append((first, len(words)))
    groups = []
    for first, last in ranges:
        left, right = boundary(first), boundary(last)
        chars = []
        for offset in range(left, right):
            char = text[offset]
            owner = next((i for i in range(first, last)
                          if matches[i].start() <= offset < matches[i].end()), None)
            if char.isspace():
                if chars and chars[-1][0] != ' ':
                    chars.append((' ', None))
            else:
                # Uppercase before measuring or wrapping: Unicode characters
                # such as ß expand to multiple glyphs, all with the same real
                # source word identity and timing.
                chars.extend((glyph, owner) for glyph in char.upper())
        if chars and chars[-1][0] == ' ':
            chars.pop()
        start = float(words[first]['start'])
        end = float(words[last - 1]['end']) + 1.0
        if last < len(words):
            end = min(end, float(words[last]['start']))
        groups.append({'text': ''.join(c for c, _ in chars),
                       'source_text': text[left:right].strip(), 'chars': chars,
                       'word_start': first, 'word_end': last, 'start': start, 'end': end})

    margin = round(width * .09)
    bottom = round(height * .11)
    maximum_width = width - margin * 2
    maximum_height = round(height * .25)
    # Use the same installed font as libass, plus width headroom for outlines
    # and small differences between Pillow and libass font shaping.
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    for size in range(max(16, round(height * .052)), max(12, round(height * .023)) - 1, -1):
        font = ImageFont.truetype(font_path, size)
        layouts = [_wrap(group['chars'], font, int(maximum_width * .96 / 1.1)) for group in groups]
        if all(len(lines) * size * 1.35 * 1.1 <= maximum_height for lines in layouts):
            break
    else:
        raise ValueError('Caption text cannot fit the safe lower area legibly')

    header = f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Captions,DejaVu Sans,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{max(2, round(height * .004))},0,2,{margin},{margin},{bottom},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    events = []
    dialogues = []
    for group_index, (group, lines) in enumerate(zip(groups, layouts)):
        start = math.ceil(group['start'] * 100 - 1e-9)
        end = math.floor(group['end'] * 100 + 1e-9)
        highlights = []
        for index in range(group['word_start'], group['word_end']):
            a = math.ceil(float(words[index]['start']) * 100 - 1e-9)
            b = math.floor(float(words[index]['end']) * 100 + 1e-9)
            if a < b:
                highlights.append((a, b, index))
        cuts = sorted({start, end, *(point for a, b, _ in highlights for point in (a, b))})
        for a, b in zip(cuts, cuts[1:]):
            if b <= a or a < start or b > end:
                continue
            active = next((i for first, last, i in highlights if first <= a and b <= last), None)
            payload = _render(lines, active)
            dialogues.append(f'Dialogue: 0,{_stamp(a)},{_stamp(b)},Captions,,0,0,0,,{payload}\n')
            events.append({'group': group_index, 'start': a / 100, 'end': b / 100,
                           'active_word': active})
        group.pop('chars')
        group['lines'] = [''.join(c for c, _ in line) for line in lines]
    write(Path(output), header + ''.join(dialogues))
    return {'path': str(output), 'format': 'ass', 'width': width, 'height': height,
            'font': 'DejaVu Sans', 'font_size': size, 'groups': groups, 'events': events,
            'timing': 'real_word_timestamps_rounded_inward_to_centiseconds',
            'max_hold_seconds': 1.0, 'active_word_scale': 1.1, 'display_case': 'uppercase'}
