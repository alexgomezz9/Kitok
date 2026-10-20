import copy
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import wave

import httpx
import pytest

from kitok.audio_library import AudioLibrary, AudioLibraryError, BASE, SFX_KINDS, infer_audio_mood, narrative_transition, synthesize_sfx
from kitok.media.ffprobe import probe_media


CATALOG = Path(__file__).resolve().parents[1] / "presets/music_sources.json"


def tone_bytes(frequency=220, seconds=8):
    import math
    raw = io.BytesIO()
    with wave.open(raw, "wb") as writer:
        writer.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        writer.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * frequency * i / 48000))) for i in range(round(seconds * 48000))))
    return raw.getvalue()


@pytest.fixture
def audio_library(tmp_path):
    catalog = json.loads(CATALOG.read_text())
    # Four contrasting fixtures cover the algorithm; real catalog identity is checked separately.
    catalog["sources"] = catalog["sources"][:4]
    audio = {item["id"]: tone_bytes(180 + index * 130) for index, item in enumerate(catalog["sources"])}
    for item in catalog["sources"]:
        item["sha256"] = hashlib.sha256(audio[item["id"]]).hexdigest()
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog))
    requests = []
    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        if str(request.url) == BASE + "pieces.json":
            return httpx.Response(200, json=[{"title": item["title"], "isrc": item["isrc"], "filename": item["filename"]} for item in catalog["sources"]])
        for source in catalog["sources"]:
            if str(request.url) == source["source_url"]:
                return httpx.Response(200, content=b"Licensed under Creative Commons: By Attribution 4.0 License http://creativecommons.org/licenses/by/4.0/")
            if str(request.url) == source["download_url"]:
                return httpx.Response(200, content=audio[source["id"]])
        raise AssertionError(str(request.url))
    client = httpx.Client(transport=httpx.MockTransport(handler), headers={"Authorization": "secret", "Cookie": "private"}, follow_redirects=True)
    library = AudioLibrary(path, tmp_path / "library", client=client)
    return library, catalog, audio, requests


def test_catalog_exact_sources_and_noncommercial_rejected(tmp_path):
    catalog = json.loads(CATALOG.read_text())
    assert len(catalog["sources"]) == 20
    assert all(item["content_id"] == "unknown" for item in catalog["sources"])
    for field, value in [("download_url", "https://attacker.invalid/song.mp3"), ("license_id", "CC-BY-NC-4.0"),
                         ("source_url", "https://incompetech.com/other"), ("title", "Unreviewed title")]:
        broken = copy.deepcopy(catalog)
        broken["sources"][0][field] = value
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(broken))
        with pytest.raises(AudioLibraryError, match="unapproved"):
            AudioLibrary(path, tmp_path / "cache")


def test_fetch_provenance_hash_and_no_second_get(audio_library):
    library, catalog, audio, calls = audio_library
    result = library.fetch("long_note_two")
    assert result["sha256"] == catalog["sources"][0]["sha256"]
    assert result["content_id"] == "unknown"
    assert len(calls) == 3
    assert not result["cache_hit"]
    second = library.fetch("long_note_two")
    assert second["cache_hit"] and len(calls) == 3
    directory = library.cache / "long_note_two"
    assert (directory / "music.mp3").read_bytes() == audio["long_note_two"]
    assert (directory / "source.json").is_file() and (directory / "license.html").is_file()


def test_redirect_size_and_url_boundaries(audio_library):
    library, *_ = audio_library
    calls = []
    def redirect(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "https://attacker.invalid/track"})
    library.client = httpx.Client(transport=httpx.MockTransport(redirect), follow_redirects=True)
    url = library.sources["long_note_two"].source_url
    with pytest.raises(AudioLibraryError, match="HTTP 307"):
        library._get(url, maximum=1024)
    assert len(calls) == 1
    with pytest.raises(AudioLibraryError, match="audited catalog"):
        library._get("https://attacker.invalid/track", maximum=1024)
    assert len(calls) == 1
    library.client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 64)))
    with pytest.raises(AudioLibraryError, match="size limit"):
        library._get(url, maximum=32)
    class Chunked(httpx.SyncByteStream):
        def __iter__(self):
            yield b"a" * 20
            yield b"b" * 20
    library.client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Chunked())))
    with pytest.raises(AudioLibraryError, match="size limit"):
        library._get(url, maximum=32)


def test_hash_mismatch_and_license_change_never_adopted(audio_library):
    library, catalog, audio, calls = audio_library
    original = library.client
    def changed(request):
        if str(request.url) == library.sources["long_note_two"].download_url:
            return httpx.Response(200, content=b"changed bytes")
        return original.send(request)
    library.client = httpx.Client(transport=httpx.MockTransport(changed))
    with pytest.raises(AudioLibraryError, match="hash changed"):
        library.fetch("long_note_two")
    assert not (library.cache / "long_note_two/music.mp3").exists()
    library.client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"CC BY-NC only")))
    with pytest.raises(AudioLibraryError, match="license"):
        library.fetch("long_note_two")
    assert not (library.cache / "long_note_two/receipt.json").exists()


def test_corrupt_cache_is_not_selected(audio_library):
    library, *_ = audio_library
    library.fetch("long_note_two")
    (library.cache / "long_note_two/music.mp3").write_bytes(b"corrupt")
    with pytest.raises(AudioLibraryError, match="Not enough"):
        library.select("episode-1", channel="loose_thread", mood="investigation", count=1)


def test_available_is_local_non_mutating_and_manual_selection_is_stable(audio_library):
    library, _, _, calls = audio_library
    assert library.available() == []
    assert not (library.cache / "selection.json").exists()
    assert not (library.cache / "long_note_two").exists()
    library.fetch("long_note_two")
    before = len(calls)
    assert [row["id"] for row in library.available(channel="loose_thread", mood="investigation")] == ["long_note_two"]
    assert library.available(channel="horror") == []
    choice = library.select_manual("manual", "long_note_two")
    assert choice["tracks"] == ["long_note_two"]
    assert library.select_manual("manual", "long_note_two") == choice
    assert len(calls) == before
    with pytest.raises(AudioLibraryError, match="different audio selection"):
        library.select("manual", channel="loose_thread", mood="investigation", count=1)
    with pytest.raises(AudioLibraryError, match="missing or corrupted"):
        library.select_manual("another", "echoes_of_time_v2")


def test_mix_rejects_invalid_or_overlapping_cues_before_writing(audio_library, tmp_path):
    library, *_ = audio_library
    for events in [[{"time": float("nan")}], [{"time": 2, "kind": "explosion"}],
                   [{"time": 3.9}], [{"time": 1}, {"time": 1.2}],
                   [{"time": 1, "path": "/untrusted/sample.wav"}]]:
        with pytest.raises(AudioLibraryError):
            library.mix("cue", tmp_path / "missing.wav", tmp_path / "new.wav", duration=4, sfx_events=events)
    assert not (tmp_path / "new.wav").exists()


def test_real_mix_contains_original_cues_with_measured_levels(audio_library, tmp_path):
    library, *_ = audio_library
    library.fetch("long_note_two")
    library.select_manual("sfx", "long_note_two")
    voice = tmp_path / "voice.wav"
    voice.write_bytes(tone_bytes(seconds=4))
    receipt = library.mix("sfx", voice, tmp_path / "sfx.wav", duration=4,
                          sfx_events=[{"time": .5}, {"time": 2.5, "kind": "low_pulse"}])
    assert [event["kind"] for event in receipt["sound_effects"]] == ["soft_tick", "low_pulse"]
    assert all(event["external_samples"] is False for event in receipt["sound_effects"])
    assert "adelay=500:all=1" in receipt["filter"]
    assert receipt["measured"]["true_peak_dbtp"] <= -1.5


def test_selection_corruption_is_rejected_without_rewriting_state(audio_library):
    library, *_ = audio_library
    library.fetch("long_note_two")
    library.select("job", channel="loose_thread", mood="investigation", count=1)
    state_path = library.cache / "selection.json"
    state = json.loads(state_path.read_text())
    state["jobs"]["job"]["credits"] = []
    corrupt = json.dumps(state)
    state_path.write_text(corrupt)
    with pytest.raises(AudioLibraryError, match="selection is missing or invalid"):
        library.select("job", channel="loose_thread", mood="investigation", count=1)
    assert state_path.read_text() == corrupt


def test_receipt_created_during_mix_is_preserved(audio_library, tmp_path, monkeypatch):
    library, *_ = audio_library
    library.fetch("long_note_two")
    library.select("race", channel="loose_thread", mood="investigation", count=1)
    narration = tmp_path / "narration.wav"
    narration.write_bytes(tone_bytes(seconds=4))
    output = tmp_path / "new.m4a"
    receipt_path = output.with_suffix(".m4a.json")
    original = library._run
    def racing_run(command, label):
        result = original(command, label)
        if label == "audio mix":
            receipt_path.write_text("operator receipt")
        return result
    monkeypatch.setattr(library, "_run", racing_run)
    with pytest.raises(AudioLibraryError, match="receipt appeared"):
        library.mix("race", narration, output, duration=4)
    assert receipt_path.read_text() == "operator receipt"
    assert not output.exists()


@pytest.mark.parametrize("replace_receipt", [False, True])
def test_output_created_during_mix_preserves_foreign_artifacts(audio_library, tmp_path, monkeypatch, replace_receipt):
    import os
    library, *_ = audio_library
    library.fetch("long_note_two")
    library.select("race-output", channel="loose_thread", mood="investigation", count=1)
    narration = tmp_path / "voice.wav"
    narration.write_bytes(tone_bytes(seconds=4))
    output, foreign = tmp_path / "new.m4a", tmp_path / "foreign.json"
    receipt_path = output.with_suffix(".m4a.json")
    foreign.write_text("operator receipt")
    real_link = os.link
    def racing_link(source, destination, **kwargs):
        if Path(destination) == output:
            output.write_bytes(b"operator output")
            if replace_receipt:
                os.replace(foreign, receipt_path)
            raise FileExistsError
        return real_link(source, destination, **kwargs)
    monkeypatch.setattr(os, "link", racing_link)
    with pytest.raises(AudioLibraryError, match="Output appeared"):
        library.mix("race-output", narration, output, duration=4)
    assert output.read_bytes() == b"operator output"
    assert receipt_path.read_text() == "operator receipt" if replace_receipt else not receipt_path.exists()


def test_selection_repeatable_rotates_primary_and_preserves_mood(audio_library):
    library, *_ = audio_library
    for track in library.sources:
        library.fetch(track)
    first = library.select("job-1", channel="loose_thread", mood="investigation")
    assert library.select("job-1", channel="loose_thread", mood="investigation") == first
    second = library.select("job-2", channel="loose_thread", mood="investigation")
    assert second["tracks"][0] != first["tracks"][0]
    assert set(first["tracks"]) == {"long_note_two", "echoes_of_time_v2"}
    reflective = library.select("job-3", channel="loose_thread", mood="resolution", count=1)
    assert reflective["tracks"] == ["dreams_become_real"]
    with pytest.raises(AudioLibraryError, match="different audio selection"):
        library.select("job-1", channel="lore", mood="mystery")
    assert all("creativecommons.org" in credit for credit in first["credits"])


def test_symlinks_and_duplicate_operations_rejected(audio_library, tmp_path):
    library, catalog, *_ = audio_library
    with library._lock():
        with pytest.raises(AudioLibraryError, match="in progress"):
            library.select("job", channel="lore", mood="horror", count=1)
    directory = library.cache / "long_note_two"
    directory.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("preserve")
    (directory / "music.mp3").symlink_to(outside)
    with pytest.raises(AudioLibraryError, match="symlinks"):
        library.fetch("long_note_two")
    assert outside.read_text() == "preserve"


def test_real_mix_ducking_crossfade_loudness_and_preservation(audio_library, tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg unavailable")
    library, *_ = audio_library
    for track in ("long_note_two", "echoes_of_time_v2"):
        library.fetch(track)
    library.select("real-mix", channel="loose_thread", mood="investigation")
    narration = tmp_path / "narration.wav"
    # A voice-shaped modulated multi-frequency synthetic fixture, with a pause.
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
        "aevalsrc=(0.13*sin(2*PI*180*t)+0.035*sin(2*PI*450*t))*(0.45+0.55*abs(sin(2*PI*3*t)))*if(between(t\\,2\\,3)\\,0\\,1):s=48000:d=6",
        "-c:a", "pcm_s16le", str(narration)], check=True, capture_output=True)
    original = hashlib.sha256(narration.read_bytes()).hexdigest()
    output = tmp_path / "mix.m4a"
    receipt = library.mix("real-mix", narration, output, duration=6)
    assert abs(probe_media(output).duration - 6) < .08
    assert abs(receipt["measured"]["integrated_lufs"] + 16) < 1
    assert receipt["measured"]["true_peak_dbtp"] <= -1.5
    assert "sidechaincompress" in receipt["filter"]
    assert "acrossfade" in receipt["filter"]
    assert receipt["selection"]["changes_notice"]
    assert len(receipt["sources"]) == 2
    assert hashlib.sha256(narration.read_bytes()).hexdigest() == original
    before = output.read_bytes()
    with pytest.raises(AudioLibraryError, match="new separate"):
        library.mix("real-mix", narration, output, duration=6)
    assert output.read_bytes() == before
    decoded = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(output),
        "-af", "bandpass=f=180:width_type=h:width=40", "-ar", "48000", "-ac", "1", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    values = struct.unpack("<" + "h" * (len(decoded) // 2), decoded)
    def tail_rms(start, end):
        segment = values[round(start * 48000):round(end * 48000)]
        return math.sqrt(sum(value * value for value in segment) / len(segment))
    # Bed fades must not fade the last spoken words.
    assert tail_rms(5.8, 5.95) > tail_rms(5, 5.15) * .8


def test_real_sidechain_reduces_music_during_voice(audio_library, tmp_path):
    """Measure the bed itself: it must recover during a narration pause."""
    library, *_ = audio_library
    library.fetch("long_note_two")
    narration = tmp_path / "voice.wav"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
        "aevalsrc=0.12*sin(2*PI*180*t)*if(between(t\\,2\\,3)\\,0\\,1):s=48000:d=6",
        "-c:a", "pcm_s16le", str(narration)], check=True, capture_output=True)
    chain = library._mix_filter(6, 1.5, 1).rsplit(";", 1)[0]
    # Keep the production compressor and discard only the final voice/bed sum.
    chain += ";[voice]anullsink;[bedfaded]anull[mixed]"
    output = tmp_path / "ducked-bed.wav"
    library._run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(narration),
        "-i", str(library.cache / "long_note_two/music.mp3"), "-filter_complex", chain,
        "-map", "[mixed]", "-c:a", "pcm_s16le", str(output)], "ducking fixture")
    with wave.open(str(output)) as source:
        rate, channels = source.getframerate(), source.getnchannels()
        samples = struct.unpack("<" + "h" * source.getnframes() * channels, source.readframes(source.getnframes()))
    def rms(start, end):
        segment = samples[round(start * rate * channels):round(end * rate * channels)]
        return math.sqrt(sum(value * value for value in segment) / len(segment))
    assert rms(2.7, 2.95) > rms(1.2, 1.6) * 1.5


def test_reject_excess_duration_and_input_overwrite(audio_library, tmp_path):
    library, *_ = audio_library
    narration = tmp_path / "narration.wav"
    narration.write_bytes(tone_bytes(seconds=4))
    with pytest.raises(AudioLibraryError, match="new separate"):
        library.mix("job", narration, narration, duration=4)
    with pytest.raises(AudioLibraryError, match="cover"):
        library.mix("job", narration, tmp_path / "new.wav", duration=8)
    assert not (tmp_path / "new.wav").exists()


@pytest.mark.parametrize("kind", SFX_KINDS)
def test_original_sfx_deterministic_quiet_and_non_destructive(tmp_path, kind):
    first, second = tmp_path / "first.wav", tmp_path / "second.wav"
    one, two = synthesize_sfx(first, kind=kind), synthesize_sfx(second, kind=kind)
    assert one["sha256"] == two["sha256"]
    assert not one["external_samples"]
    with wave.open(str(first)) as source:
        samples = struct.unpack("<" + "h" * source.getnframes(), source.readframes(source.getnframes()))
    assert max(abs(value) for value in samples) < .08 * 32768
    with pytest.raises(FileExistsError):
        synthesize_sfx(first)


def test_sfx_families_have_distinct_original_waveforms_and_fit_events(tmp_path):
    from kitok.audio_library import SoundEvent
    hashes = set()
    for kind in SFX_KINDS:
        assert SoundEvent.model_validate({"time": 1, "kind": kind}).kind == kind
        hashes.add(synthesize_sfx(tmp_path / f"{kind}.wav", kind=kind)["sha256"])
    assert len(hashes) == 6


@pytest.mark.parametrize("script,channel,expected", [
    ("A quiet beginning. We examine the evidence in the records and reveal how the fraud survived the audit.", "loose_thread", "investigation"),
    ("The opening is not the whole story. We explore grief and loss through the memories and legacy of the survivors.", "loose_thread", "reflective"),
    ("The film begins years earlier. Now rebuilding and recovery bring healing and reconciliation to the entire community.", "loose_thread", "resolution"),
    ("Today we travel through the forest to study the ocean and its species, ecosystems and biodiversity together.", "science", "ambient"),
    ("A cold evening begins our tale. The haunted house hides a ghost and a supernatural curse in every corridor.", "lore", "horror"),
    ("A cold evening begins our tale. The haunted house hides a ghost and a supernatural curse in every corridor.", "loose_thread", "investigation"),
    ("The recovery and rebuilding continue, while this long and unremarkable paragraph quietly describes the local landscape.", "horror", "horror"),
    ("The word fraud appears only once while this ordinary narration describes a long journey across the country.", "loose_thread", "investigation"),
    ("A short text.", "science", "ambient"),
    ("The evidence and fraud are described alongside grief and loss, with no clear narrative emphasis to choose between them.", "science", "ambient"),
    ("We follow the story in full. The hacker used software to reach the server through the network and its encryption.", "loose_thread", "technology"),
    ("The next chapter tells the story of investors and shares, as debt and revenue reshape the entire corporate market.", "loose_thread", "business"),
    ("This film follows an ancient empire through a century of revolution, with historical archives explaining what changed.", "documentary", "history"),
    ("Everything changes in the final chapter. A revelation exposed what the breakthrough uncovered about the disputed event.", "loose_thread", "revelation"),
])
def test_mood_uses_full_script_conservatively_and_respects_profile(script, channel, expected):
    assert infer_audio_mood(script, channel=channel) == expected


def test_inferred_moods_have_two_catalog_choices_for_supported_channels():
    from kitok.audio_library import AudioLibrary, MusicSource
    catalog = json.loads(CATALOG.read_text())["sources"]
    ordinary = ["investigation", "reflective", "resolution", "ambient", "technology", "business", "history", "revelation"]
    for channel, moods in {"loose_thread": ordinary, "documentary": ordinary, "science": ordinary,
                           "lore": [*ordinary, "horror"],
                           "horror": ["horror"]}.items():
        for mood in moods:
            assert sum(channel in source["channels"] and AudioLibrary._matches_mood(MusicSource.model_validate(source), mood)
                       for source in catalog) >= 2


def test_editorial_affinities_are_selectable_without_changing_source_receipts(audio_library):
    library, *_ = audio_library
    library.fetch("echoes_of_time_v2")
    receipt_path = library.cache / "echoes_of_time_v2/receipt.json"
    before = receipt_path.read_bytes()
    rows = library.available(channel="loose_thread", mood="history")
    assert [row["id"] for row in rows] == ["echoes_of_time_v2"]
    assert "history" in rows[0]["editorial_affinities"]
    choice = library.select("history-job", channel="loose_thread", mood="history", count=1)
    assert choice["tracks"] == ["echoes_of_time_v2"]
    assert "editorial affinity" in choice["mood_basis"]
    assert "history" not in library.sources["echoes_of_time_v2"].moods
    assert receipt_path.read_bytes() == before


def test_music_preview_is_hash_verified_local_and_non_mutating(audio_library):
    library, _, _, calls = audio_library
    with pytest.raises(AudioLibraryError, match="preview missing"):
        library.preview("long_note_two")
    assert not (library.cache / "long_note_two").exists()
    library.fetch("long_note_two")
    before = len(calls)
    assert library.preview("long_note_two").read_bytes()
    assert len(calls) == before
    assert not (library.cache / "selection.json").exists()
    library.preview("long_note_two").write_bytes(b"changed")
    with pytest.raises(AudioLibraryError, match="preview missing"):
        library.preview("long_note_two")
    with pytest.raises(AudioLibraryError):
        library.preview("../../outside")


OPENING = "The investigation follows the evidence of fraud hidden in the records, while the audit exposes the scandal. " * 3
CLOSING = "The aftermath brings grief and loss to the survivors, whose memories and legacy remain with the community. " * 2


def test_narrative_preflight_and_selection_use_two_moods_and_preserve_revisions(audio_library):
    library, _, _, calls = audio_library
    script = OPENING + CLOSING
    options = library.narrative_options(script)
    assert options["eligible"] is False
    assert not (library.cache / "selection.json").exists()
    for track in ("long_note_two", "echoes_of_time_v2", "dreams_become_real"):
        library.fetch(track)
    before = len(calls)
    options = library.narrative_options(script)
    assert options["eligible"] and options["opening_mood"] == "investigation" and options["closing_mood"] == "reflective"
    choice = library.select_narrative("narrative", script)
    assert choice["tracks"][0] in {"long_note_two", "echoes_of_time_v2"}
    assert choice["tracks"][1] == "dreams_become_real"
    assert choice["count"] == 2 and choice["method"] == "narrative-v1"
    assert library.select_narrative("narrative", script) == choice
    assert library.select_narrative("next", script)["tracks"][0] != choice["tracks"][0]
    with pytest.raises(AudioLibraryError, match="different audio selection"):
        library.select_narrative("narrative", script + " Another closing sentence.")
    assert len(calls) == before


def test_narrative_selection_requires_two_distinct_verified_tracks(audio_library):
    library, *_ = audio_library
    library.fetch("dreams_become_real")
    script = "The survivors reflect on grief, loss and memories in the aftermath of an event that changed their community."
    assert library.narrative_options(script)["eligible"] is False
    with pytest.raises(AudioLibraryError, match="distinct cached"):
        library.select_narrative("insufficient", script)
    assert not (library.cache / "selection.json").exists()


def test_narrative_crossfade_uses_validated_semantic_boundary_and_labels_fallback():
    script = OPENING + CLOSING
    sections = [{"text": OPENING, "start": 0, "end": 11}, {"text": CLOSING, "start": 11.5, "end": 30}]
    result = narrative_transition(script, 30, sections=sections)
    assert result["transition_at"] == 11.25 and result["method"] == "validated-mood-boundary"
    assert narrative_transition(script, 30)["transition_at"] == 15
    assert narrative_transition(script, 30)["method"] == "fallback-central-estimated"
    changed = [{**sections[0], "text": "An unrelated transcript"}, sections[1]]
    assert narrative_transition(script, 30, sections=changed)["method"] == "fallback-central-estimated"
    changed = [{**sections[0], "start": float("nan")}, sections[1]]
    assert narrative_transition(script, 30, sections=changed)["method"] == "fallback-central-estimated"


def test_real_mix_crossfade_can_follow_an_off_center_boundary(audio_library, tmp_path):
    library, *_ = audio_library
    for track in ("long_note_two", "echoes_of_time_v2"):
        library.fetch(track)
    library.select("boundary", channel="loose_thread", mood="investigation")
    narration = tmp_path / "voice.wav"
    narration.write_bytes(tone_bytes(seconds=6))
    receipt = library.mix("boundary", narration, tmp_path / "boundary.m4a", duration=6, transition_at=2)
    assert receipt["transition_at"] == 2
    assert "atrim=duration=2.750000" in receipt["filter"] and "atrim=duration=4.750000" in receipt["filter"]
    assert abs(receipt["duration"]-6) < .08
    assert abs(receipt["measured"]["integrated_lufs"]+16) < 1
    assert receipt["measured"]["true_peak_dbtp"] <= -1.5
    for at in [float("nan"), -.5, .1, 5.9]:
        with pytest.raises(AudioLibraryError, match="transition"):
            library.mix("boundary", narration, tmp_path / "invalid.m4a", duration=6, transition_at=at)


def test_long_documentary_automatic_mix_has_continuous_sample_clock(audio_library, tmp_path):
    """A six-minute MP3 voice and looped beds exercise loudnorm's rate changes.

    This is entirely local synthesized test audio, not a paid voice. Keep the
    native renderer's PCM output, a noncentral crossfade and sparse SFX together.
    """
    library, catalog, audio, calls = audio_library
    for index, track in enumerate(("long_note_two", "echoes_of_time_v2")):
        # No Xing/gapless metadata, as in the confirmed Fish MP3. Ordinary LAME
        # files with skip metadata hide this defect even with long narration.
        # Loop boundaries and 44.1 -> 48 -> 192 -> 48 kHz exercise all branches.
        music = tmp_path / f"bed-{index}.mp3"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                        f"sine=frequency={220+index*130}:sample_rate=44100:duration=8.13",
                        "-af", "volume='0.6+0.35*sin(t)':eval=frame", "-c:a", "libmp3lame", "-write_xing", "0", str(music)],
                       check=True, capture_output=True)
        data = music.read_bytes()
        audio[track] = data
        source = library.sources[track]
        sha = hashlib.sha256(data).hexdigest()
        library.sources[track] = source.model_copy(update={"sha256": sha})
        next(row for row in catalog["sources"] if row["id"] == track)["sha256"] = sha
        library.fetch(track)
    script = "The evidence in the records explains the fraud. " * 80
    selection = library.select_narrative("long-documentary", script)
    assert len(selection["tracks"]) == 2
    narration = tmp_path / "voice.mp3"
    # Sparse transients force the final normalizer into true-peak-limited dynamic
    # mode; a low-crest sine would normalize linearly and miss the actual defect.
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                    "aevalsrc=(0.13*sin(2*PI*180*t)+0.035*sin(2*PI*450*t))*(0.45+0.55*abs(sin(2*PI*3*t)))*if(lt(mod(t\\,17)\\,1)\\,0\\,1)+0.8*sin(2*PI*950*t)*lt(mod(t\\,53)\\,0.008):s=44100:d=360.70",
                    "-c:a", "libmp3lame", "-b:a", "128k", "-write_xing", "0", str(narration)], check=True, capture_output=True)
    duration = probe_media(narration).duration
    original = hashlib.sha256(narration.read_bytes()).hexdigest()
    calls_before = len(calls)
    events = [{"time": 23.5324, "kind": "soft_tick"}, {"time": 47.2509, "kind": "low_pulse"},
              {"time": 227.3727, "kind": "soft_tick"}, {"time": 301.8549, "kind": "low_pulse"}]
    receipt = library.mix("long-documentary", narration, tmp_path / "documentary.wav", duration=duration,
                          transition_at=223.1457, sfx_events=events)
    assert len(calls) == calls_before
    assert hashlib.sha256(narration.read_bytes()).hexdigest() == original
    assert abs(receipt["duration"] - duration) <= .08
    assert abs(receipt["measured"]["integrated_lufs"] + 16) <= 1
    assert receipt["measured"]["true_peak_dbtp"] <= -1.5
    assert math.isfinite(receipt["measured"]["loudness_range_lu"])
    assert receipt["transition_at"] == 223.1457
    assert len(receipt["sound_effects"]) == 4
    assert receipt["mixer_revision"] == "sample-clock-v2"
    diagnostics = Path(receipt["diagnostics_directory"])
    assert (diagnostics / "mixed.wav").is_file()
    assert json.loads((diagnostics / "validation.json").read_text())["status"] == "validated"


@pytest.mark.parametrize("measurement,expected", [
    ({"integrated_lufs": -16., "true_peak_dbtp": -1.8, "loudness_range_lu": 3.5}, "duration="),
    ({"integrated_lufs": -20., "true_peak_dbtp": -1.8, "loudness_range_lu": 3.5}, "integrated_lufs=-20.0"),
    ({"integrated_lufs": -16., "true_peak_dbtp": -1.2, "loudness_range_lu": 3.5}, "true_peak_dbtp=-1.2"),
    ({"integrated_lufs": -16., "true_peak_dbtp": -1.8, "loudness_range_lu": float("nan")}, "loudness_range_lu=nan"),
])
def test_mix_validation_reports_measurements_and_preserves_failed_master(
        audio_library, tmp_path, monkeypatch, measurement, expected):
    from dataclasses import replace
    import kitok.audio_library as audio_module
    library, *_ = audio_library
    library.fetch("long_note_two")
    library.select_manual("rejected", "long_note_two")
    narration = tmp_path / "voice.wav"
    narration.write_bytes(tone_bytes(seconds=4))
    original_probe = audio_module.probe_media
    def probe(path, *args):
        info = original_probe(path, *args)
        return replace(info, duration=3.866) if Path(path).name == "mixed.wav" and expected == "duration=" else info
    monkeypatch.setattr(audio_module, "probe_media", probe)
    monkeypatch.setattr(audio_module, "measure_loudness", lambda *args: measurement)
    output = tmp_path / "rejected.wav"
    with pytest.raises(AudioLibraryError, match=expected) as caught:
        library.mix("rejected", narration, output, duration=4)
    assert "measured LUFS=" in str(caught.value)
    assert "LRA=" in str(caught.value) and "true_peak_dbtp=" in str(caught.value)
    assert not output.exists() and not output.with_suffix(".wav.json").exists()
    workspaces = list(tmp_path.glob(".audio-mix-*"))
    assert len(workspaces) == 1
    workspace = workspaces[0]
    assert (workspace / "mixed.wav").is_file()
    assert (workspace / "analysis.log").is_file() and (workspace / "encode.log").is_file()
    assert json.loads((workspace / "failure.json").read_text())["status"] == "failed"
    validation = json.loads((workspace / "validation.json").read_text())
    assert validation["status"] == "rejected"
    if expected == "duration=":
        assert "delta=-0.134000s" in str(caught.value)
        assert validation["actual_duration"] == 3.866
