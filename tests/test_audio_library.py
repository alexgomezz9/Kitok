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

from kitok.audio_library import AudioLibrary, AudioLibraryError, BASE, synthesize_sfx
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
    assert len(catalog["sources"]) == 4
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


def test_original_sfx_deterministic_quiet_and_non_destructive(tmp_path):
    first, second = tmp_path / "first.wav", tmp_path / "second.wav"
    one, two = synthesize_sfx(first), synthesize_sfx(second)
    assert one["sha256"] == two["sha256"]
    assert not one["external_samples"]
    with wave.open(str(first)) as source:
        samples = struct.unpack("<" + "h" * source.getnframes(), source.readframes(source.getnframes()))
    assert max(abs(value) for value in samples) < .08 * 32768
    with pytest.raises(FileExistsError):
        synthesize_sfx(first)
