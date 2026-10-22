"""Real acoustic probes: sustained gaps must remain visible under background music."""
import math
import struct
import wave

from kitok.config import Settings
from kitok.youtube_stickman_es.quality import inspect_audio_continuity, silence_intervals


def tone(path, *, gap=False, trailing=False):
    with wave.open(str(path), 'wb') as audio:
        audio.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b''.join(struct.pack('<h',
            0 if gap and 1 <= n/8000 < 3 or trailing and n/8000 >= 2
            else round(4000*math.sin(2*math.pi*220*n/8000))) for n in range(32000)))


def test_source_gap_is_flagged_even_when_music_masks_final_mix(tmp_path):
    settings = Settings(_env_file=None, data_root=tmp_path)
    narration, final = tmp_path/'voice.wav', tmp_path/'mix.wav'
    tone(narration, gap=True)
    tone(final)
    report = inspect_audio_continuity(final, narration, settings=settings)
    assert report['status'] == 'human_review_required'
    assert report['tracks']['final_mix']['quiet_intervals'] == []
    interval, = report['tracks']['source_narration']['quiet_intervals']
    assert abs(interval['start']-1) < .01 and abs(interval['end']-3) < .01
    assert 'intentional pauses' in report['limitation']


def test_continuous_audio_and_trailing_silence_are_distinguished(tmp_path):
    settings = Settings(_env_file=None, data_root=tmp_path)
    source = tmp_path/'voice.wav'
    tone(source)
    assert inspect_audio_continuity(source, source, settings=settings)['status'] == 'no_long_silence_detected'
    tone(source, trailing=True)
    interval, = silence_intervals(source, settings=settings)
    assert abs(interval['start']-2) < .01 and abs(interval['end']-4) < .01
