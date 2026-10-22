"""Real local input validation; Fish is replaced before any paid operation."""
import hashlib
import json
import math
from pathlib import Path
import struct
import wave

import pytest

from kitok.config import Settings
from kitok.youtube_stickman_es import audio


def _tone(path, *, seconds=4):
    # ffprobe detects the actual audio stream, independently of the .mp3 suffix.
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        output.writeframes(b"".join(struct.pack("<h", round(2000 * math.sin(2 * math.pi * 220 * n / 8000)))
                                   for n in range(round(8000 * seconds))))


@pytest.fixture
def episode(tmp_path):
    folder = tmp_path / "episode"
    folder.mkdir()
    (folder / "guion_final.txt").write_text("[calm] Hola, mundo. Todo cambia.", encoding="utf-8")
    _tone(folder / "voz.mp3")
    (folder / "voz.srt").write_text(
        "\ufeff1\r\n00:00:00,100 --> 00:00:01,500\r\nHola, mundo.\r\n\r\n"
        "2\r\n00:00:02,000 --> 00:00:03,800\r\nTodo cambia.\r\n", encoding="utf-8")
    return folder


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_root=tmp_path, fish_api_key="test-private-value")


def _prepare(episode, settings, **kwargs):
    return audio.prepare_narration(episode, root=episode.parent, settings=settings, **kwargs)


def _alignment(episode, **overrides):
    data = {"method": "fish_provider_timestamps", "words": [
        {"word": "Hola,", "start": .1, "end": .8},
        {"word": "mundo.", "start": .8, "end": 1.5},
        {"word": "Todo", "start": 2, "end": 2.8},
        {"word": "cambia.", "start": 2.8, "end": 3.8}]}
    data.update(overrides)
    (episode / "voz.alignment.json").write_text(json.dumps(data), encoding="utf-8")
    return data


def test_import_measures_real_audio_preserves_inputs_and_requires_sync_review(episode, settings):
    before = {path.name: path.read_bytes() for path in episode.iterdir()}
    result = _prepare(episode, settings)
    assert result["duration"] == 4
    assert result["alignment_method"] == "imported_srt_human_sync_review_required"
    assert result["human_sync_review_required"] and not result["acoustic_sync_verified"]
    assert result["cues"][1] == {"index": 2, "start": 2., "end": 3.8, "text": "Todo cambia."}
    assert result["audio_sha256"] == hashlib.sha256(before["voz.mp3"]).hexdigest()
    assert Path(result["audio_path"]).is_absolute()
    assert _prepare(episode, settings) == result
    assert all((episode / name).read_bytes() == data for name, data in before.items())


@pytest.mark.parametrize("text", [
    "", "0\n00:00:00,000 --> 00:00:01,000\nHola",
    "2\n00:00:00,000 --> 00:00:01,000\nHola",
    "1\n-00:00:00,000 --> 00:00:01,000\nHola",
    "1\n00:60:00,000 --> 00:00:01,000\nHola",
    "1\n00:00:00.000 --> 00:00:01.000\nHola",
    "1\n00:00:00,000 --> 00:00:00,000\nHola",
    "1\n00:00:00,000 --> 00:00:01,000\nHola\n\n2\n00:00:00,999 --> 00:00:02,000\nMundo",
    "1\n00:00:00,000 --> 00:00:01,000 position:50%\nHola",
])
def test_strict_srt_rejects_invalid_cues(text):
    with pytest.raises(audio.StickmanAudioError):
        audio.parse_srt(text)


def test_srt_roundtrip_keeps_multiline_and_real_boundaries():
    cues = audio.parse_srt("1\n01:02:03,004 --> 01:02:04,995\nUna frase\nen dos líneas.\n")
    assert cues[0]["start"] == 3723.004
    assert audio.parse_srt(audio.format_srt(cues)) == cues
    with pytest.raises(audio.StickmanAudioError):
        audio.format_srt([dict(cues[0], end=float("inf"))])


@pytest.mark.parametrize("changed", ["voz.mp3", "voz.srt", "guion_final.txt"])
def test_validated_input_mutation_is_blocked_without_replacing_receipt(episode, settings, changed):
    _prepare(episode, settings)
    receipt = (episode / ".stickman/narration.json").read_bytes()
    with (episode / changed).open("ab") as output:
        output.write(b" ")
    with pytest.raises(audio.StickmanAudioError, match="changed after validation"):
        _prepare(episode, settings)
    assert (episode / ".stickman/narration.json").read_bytes() == receipt


def test_missing_srt_never_estimates_or_synthesizes_existing_audio(episode, settings, monkeypatch):
    (episode / "voz.srt").unlink()
    monkeypatch.setattr(audio, "FishVoiceClient", lambda *a, **k: pytest.fail("must reuse imported voice"))
    with pytest.raises(audio.StickmanAudioError, match="no estimated timing or second synthesis"):
        _prepare(episode, settings, generate=True)
    assert (episode / "voz.mp3").is_file()
    assert not (episode / "voz.srt").exists()


def test_missing_srt_uses_only_matching_provider_timestamps(episode, settings):
    (episode / "voz.srt").unlink()
    _alignment(episode)
    result = _prepare(episode, settings)
    assert result["alignment_method"] == "fish_provider_timestamps_full_transcript"
    assert result["cues"] == audio.read_srt(episode / "voz.srt")
    assert result["cues"][0]["start"] == .1
    assert result["cues"][-1]["end"] == 3.8
    assert result["human_sync_review_required"]
    (episode / "voz.alignment.json").unlink()
    with pytest.raises(audio.StickmanAudioError, match="Provider alignment changed"):
        _prepare(episode, settings)


def test_long_sentence_gets_short_cues_only_at_real_provider_word_times(episode, settings):
    (episode / "voz.srt").unlink()
    tokens = [f"palabra{index}" for index in range(70)]
    script = " ".join(tokens) + "."
    (episode / "guion_final.txt").write_text(script)
    _tone(episode / "voz.mp3", seconds=36)
    words = [{"word": token, "start": round(index * .5 + .1, 3),
              "end": round(index * .5 + .45, 3)} for index, token in enumerate(tokens)]
    _alignment(episode, words=words)
    result = _prepare(episode, settings)
    assert len(result["cues"]) >= 12
    assert all(cue["end"] - cue["start"] <= 3 for cue in result["cues"])
    assert all(cue["start"] in {word["start"] for word in words} for cue in result["cues"])
    assert all(cue["end"] in {word["end"] for word in words} for cue in result["cues"])
    assert " ".join(cue["text"] for cue in result["cues"]) == script


def test_provider_zero_length_tokens_and_split_words_do_not_invent_timing(episode, settings):
    (episode / "voz.srt").unlink()
    (episode / "guion_final.txt").write_text("Veinti-cinco personas cambian.")
    words = [{"word": "Veinti-cinco", "start": .1, "end": .8},
             {"word": "personas", "start": .8, "end": .8},
             {"word": "cambian.", "start": 1, "end": 2}]
    _alignment(episode, words=words)
    result = _prepare(episode, settings)
    assert result["cues"] == [{"index": 1, "start": .1, "end": 2,
                                "text": "Veinti-cinco personas cambian."}]


@pytest.mark.parametrize("mutation", ["transcript", "overlap", "negative", "nonfinite", "duration", "method"])
def test_bad_provider_alignment_blocks_without_creating_srt(episode, settings, mutation):
    (episode / "voz.srt").unlink()
    data = _alignment(episode)
    if mutation == "transcript":
        data["words"][0]["word"] = "Adiós"
    elif mutation == "overlap":
        data["words"][1]["start"] = .7
    elif mutation == "negative":
        data["words"][0]["start"] = -.1
    elif mutation == "nonfinite":
        data["words"][0]["start"] = float("nan")
    elif mutation == "duration":
        data["words"][-1]["end"] = 4.1
    else:
        data["method"] = "reading_speed_estimated"
    (episode / "voz.alignment.json").write_text(json.dumps(data))
    with pytest.raises(audio.StickmanAudioError, match="full-transcript Fish alignment"):
        _prepare(episode, settings)
    assert not (episode / "voz.srt").exists()


@pytest.mark.parametrize("replacement", ["Hola mundo. Otra cosa.", "Hola mundo."])
def test_imported_srt_must_match_complete_final_script(episode, settings, replacement):
    (episode / "guion_final.txt").write_text(replacement)
    with pytest.raises(audio.StickmanAudioError, match="transcript does not match"):
        _prepare(episode, settings)


def test_imported_srt_cannot_exceed_measured_audio(episode, settings):
    (episode / "voz.srt").write_text("1\n00:00:00,000 --> 00:00:04,100\nHola mundo. Todo cambia.")
    with pytest.raises(audio.StickmanAudioError, match="measured narration duration"):
        _prepare(episode, settings)


def test_new_voice_is_explicit_no_setup_side_effect(episode, settings, monkeypatch):
    (episode / "voz.mp3").unlink()
    monkeypatch.setattr(audio, "FishVoiceClient", lambda *a, **k: pytest.fail("no setup synthesis"))
    with pytest.raises(audio.StickmanAudioError, match="explicitly generate"):
        _prepare(episode, settings)
    assert not (episode / ".stickman/voice_request.json").exists()


def test_generation_requests_timestamps_once_then_reuses_audio(episode, settings, monkeypatch):
    (episode / "voz.mp3").unlink()
    (episode / "voz.srt").unlink()
    calls = []

    class FakeFish:
        def __init__(self, key, model, **kwargs):
            assert key == "test-private-value" and kwargs["timestamps"] is True
            assert kwargs["cache_dir"] == settings.audio_cache_dir

        def synthesize(self, script, reference_id, destination, **kwargs):
            calls.append((script, reference_id, kwargs))
            _tone(destination)
            _alignment(episode)
            (episode / "voz.alignment.json").rename(destination.with_suffix(".alignment.json"))

        def close(self):
            pass

    monkeypatch.setattr(audio, "FishVoiceClient", FakeFish)
    voice = {"reference_id": "es-test", "model": None, "speed": 1.1}
    result = _prepare(episode, settings, voice=voice, generate=True)
    assert result["source"] == "fish"
    assert len(calls) == 1 and calls[0][2]["speed"] == 1.1
    assert _prepare(episode, settings, voice=voice, generate=True) == result
    assert len(calls) == 1
    assert "test-private-value" not in (episode / ".stickman/voice_request.json").read_text()
    with pytest.raises(audio.StickmanAudioError, match="voice settings changed"):
        _prepare(episode, settings, voice={"reference_id": "different"}, generate=True)


def test_no_alignment_after_synthesis_preserves_paid_audio_and_never_resubmits(episode, settings, monkeypatch):
    (episode / "voz.mp3").unlink()
    (episode / "voz.srt").unlink()
    calls = []

    class FakeFish:
        def __init__(self, *args, **kwargs):
            pass

        def synthesize(self, script, reference_id, destination, **kwargs):
            calls.append(1)
            _tone(destination)

        def close(self):
            pass

    monkeypatch.setattr(audio, "FishVoiceClient", FakeFish)
    for _ in range(2):
        with pytest.raises(audio.StickmanAudioError, match="full-transcript Fish alignment"):
            _prepare(episode, settings, voice={"reference_id": "es-test"}, generate=True)
    assert len(calls) == 1
    assert (episode / "voz.mp3").is_file()


def test_fish_race_never_replaces_operator_audio(episode, settings, monkeypatch):
    (episode / "voz.mp3").unlink()
    preserved = b"operator audio appeared during paid request"

    class FakeFish:
        def __init__(self, *args, **kwargs):
            pass

        def synthesize(self, script, reference_id, destination, **kwargs):
            _tone(destination)
            (episode / "voz.mp3").write_bytes(preserved)

        def close(self):
            pass

    monkeypatch.setattr(audio, "FishVoiceClient", FakeFish)
    with pytest.raises(audio.StickmanAudioError, match="both the input and paid result were preserved"):
        _prepare(episode, settings, voice={"reference_id": "es-test"}, generate=True)
    assert (episode / "voz.mp3").read_bytes() == preserved
    assert (episode / ".stickman/fish-voz.mp3").stat().st_size > 0


def test_audio_symlink_and_state_symlink_are_rejected(episode, settings, tmp_path):
    original = episode / "voz.mp3"
    backup = tmp_path / "real.mp3"
    original.rename(backup)
    original.symlink_to(backup)
    with pytest.raises(audio.StickmanAudioError, match="symlinks"):
        _prepare(episode, settings)
    original.unlink()
    backup.rename(original)
    (episode / ".stickman").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(audio.StickmanAudioError, match="symlink"):
        _prepare(episode, settings)


def test_off_mix_keeps_original_and_defers_normalization_to_kitok(episode, settings):
    narration = _prepare(episode, settings)
    result = audio.prepare_mix(episode, narration, root=episode.parent, settings=settings)
    assert result["audio_path"] == narration["audio_path"]
    assert result["audio_sha256"] == narration["audio_sha256"]
    assert result["audio_is_final_mix"] is False
    with pytest.raises(audio.StickmanAudioError, match="Sound effects require"):
        audio.prepare_mix(episode, narration, root=episode.parent, settings=settings,
                          music={"mode": "off"}, sfx_events=[{"time": .5}])
    with pytest.raises(audio.StickmanAudioError, match="explicit cached track_id"):
        audio.prepare_mix(episode, narration, root=episode.parent, settings=settings,
                          music={"mode": "manual", "track_id": None})


def test_auto_mix_reuses_kitok_library_and_receipts_without_remixing(episode, settings, monkeypatch):
    narration = _prepare(episode, settings)
    calls = []

    class FakeLibrary:
        def __init__(self, catalog, cache, **kwargs):
            assert catalog == episode.parent / "presets/music_sources.json"

        def select(self, job_id, **kwargs):
            assert kwargs == {"channel": "documentary", "mood": "investigation", "count": 2}
            return {"credits": ["Licensed attribution"]}

        def mix(self, job_id, source, output, **kwargs):
            calls.append(kwargs)
            assert kwargs["sfx_events"] == [{"time": .5, "kind": "soft_tick"}]
            _tone(output)
            receipt = {"version": 1, "duration": 4, "output_sha256": audio._hash(output),
                       "narration_sha256": narration["audio_sha256"],
                       "selection": {"credits": ["Licensed attribution"]}}
            output.with_suffix(".m4a.json").write_text(json.dumps(receipt))
            return receipt

        def close(self):
            pass

    monkeypatch.setattr(audio, "AudioLibrary", FakeLibrary)
    kwargs = dict(root=episode.parent, settings=settings, music={"mode": "auto"},
                  sfx_events=[{"time": .5, "kind": "soft_tick"}])
    result = audio.prepare_mix(episode, narration, **kwargs)
    assert result["audio_is_final_mix"]
    assert audio.prepare_mix(episode, narration, **kwargs) == result
    assert len(calls) == 1
    Path(result["audio_path"]).write_bytes(b"corrupt")
    with pytest.raises(audio.StickmanAudioError, match="incomplete or changed"):
        audio.prepare_mix(episode, narration, **kwargs)
