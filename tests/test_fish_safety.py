"""Paid operations must not repeat after an ambiguous response or a restart."""
import base64
import hashlib
import json
import shutil
import subprocess

import httpx
import pytest

from kitok.fish_voice import FishVoiceClient, FishVoiceError


@pytest.fixture
def audio(tmp_path):
    target = tmp_path / "source.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "sine=frequency=330:duration=0.4", "-c:a", "libmp3lame", str(target)],
                   check=True, timeout=30)
    return target.read_bytes()


@pytest.mark.parametrize("first_mode", [False, True])
def test_timeout_never_posts_again_after_restart_or_timestamp_mode_change(tmp_path, first_mode):
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("unknown result")
    for timestamps in (first_mode, not first_mode):
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            fish = FishVoiceClient("hidden", client=http, attempts=9, cache_dir=tmp_path / "cache",
                                   timestamps=timestamps)
            with pytest.raises(FishVoiceError):
                fish.synthesize("One complete sentence.", "ref", tmp_path / "out.mp3")
    assert len(calls) == 1
    assert "hidden" not in next((tmp_path / "cache").rglob("operation.json")).read_text()


@pytest.mark.parametrize("first_mode", [False, True])
def test_valid_audio_reused_without_key_after_mode_change_and_corrupt_cache_never_repaid(tmp_path, audio, first_mode):
    calls = []
    def handler(request):
        calls.append(request)
        if first_mode:
            return httpx.Response(200, text="data: " + json.dumps({"audio_base64": base64.b64encode(audio).decode()}) + "\n\n")
        return httpx.Response(200, content=audio)
    cache = tmp_path / "cache"
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        fish = FishVoiceClient("hidden", client=http, cache_dir=cache, timestamps=first_mode)
        fish.synthesize("One complete sentence.", "ref", tmp_path / "first.mp3")
        other = FishVoiceClient("", client=http, cache_dir=cache, timestamps=not first_mode)
        other.synthesize("One complete sentence.", "ref", tmp_path / "rerender.mp3")
        assert other.last_cache_hit and len(calls) == 1
        assert (tmp_path / "rerender.mp3").read_bytes() == audio
        next(cache.rglob("audio.mp3")).write_bytes(b"broken")
        with pytest.raises(FishVoiceError, match="needs review"):
            fish.synthesize("One complete sentence.", "ref", tmp_path / "third.mp3")
        assert len(calls) == 1


def legacy_folder(cache, timestamps):
    identity = {"version": 1, "model": "s2.1-pro-free", "timestamps": timestamps,
                "body": {"text": "One complete sentence.", "reference_id": "ref", "format": "mp3"}}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False,
                                            separators=(",", ":")).encode()).hexdigest()
    folder = cache / fingerprint[:2] / fingerprint
    folder.mkdir(parents=True)
    return folder


@pytest.mark.parametrize("legacy_mode", [False, True])
def test_legacy_hashed_audio_is_adopted_without_key_or_new_post(tmp_path, audio, legacy_mode):
    cache = tmp_path / "cache"
    old = legacy_folder(cache, legacy_mode)
    (old / "audio.mp3").write_bytes(audio)
    (old / "operation.json").write_text(json.dumps({"status": "succeeded", "audio_sha256": hashlib.sha256(audio).hexdigest()}))
    if legacy_mode:
        (old / "audio.alignment.json").write_text('{"words": [{"word": "One", "start": 0, "end": 0.1}]}')
    before = {p.name: p.read_bytes() for p in old.iterdir()}
    with httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("must reuse legacy audio"))) as http:
        fish = FishVoiceClient("", client=http, cache_dir=cache, timestamps=not legacy_mode)
        output = fish.synthesize("One complete sentence.", "ref", tmp_path / "adopted.mp3")
    assert fish.last_cache_hit and output.read_bytes() == audio
    for name, content in before.items():
        assert (old / name).read_bytes() == content
    assert len(list(cache.rglob("audio.mp3"))) == 2
    if legacy_mode:
        assert output.with_suffix(".alignment.json").read_bytes() == (old / "audio.alignment.json").read_bytes()


@pytest.mark.parametrize("legacy_mode", [False, True])
@pytest.mark.parametrize("status", ["submitted", "unknown", "succeeded"])
def test_uncertain_legacy_operation_blocks_both_timestamp_modes(tmp_path, legacy_mode, status):
    cache = tmp_path / "cache"
    old = legacy_folder(cache, legacy_mode)
    ledger = old / "operation.json"
    ledger.write_text(json.dumps({"status": status}))
    before = ledger.read_bytes()
    with httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("must not repeat old payment"))) as http:
        for timestamps in (False, True):
            with pytest.raises(FishVoiceError, match="uncertain"):
                FishVoiceClient("hidden", client=http, cache_dir=cache, timestamps=timestamps).synthesize(
                    "One complete sentence.", "ref", tmp_path / "out.mp3")
    assert ledger.read_bytes() == before


def test_configured_ffprobe_is_used_for_new_and_cached_audio(tmp_path, audio, monkeypatch):
    from kitok.media import ffprobe as probing
    custom = tmp_path / "custom-ffprobe"
    custom.symlink_to(shutil.which("ffprobe"))
    calls = []
    actual_probe = probing.probe_media
    def probe(path, binary="ffprobe"):
        calls.append(binary)
        return actual_probe(path, binary)
    monkeypatch.setattr(probing, "probe_media", probe)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=audio))) as http:
        fish = FishVoiceClient("hidden", client=http, cache_dir=tmp_path / "cache", ffprobe=str(custom))
        fish.synthesize("Sentence.", "ref", tmp_path / "first.mp3")
        fish.synthesize("Sentence.", "ref", tmp_path / "second.mp3")
    assert calls == [str(custom), str(custom)]


def test_timestamp_modes_share_inflight_request_lock(tmp_path, audio):
    calls = []
    def handler(request):
        calls.append(request)
        with pytest.raises(FishVoiceError, match="already running"):
            FishVoiceClient("hidden", client=http, cache_dir=tmp_path / "cache", timestamps=True).synthesize(
                "Sentence.", "ref", tmp_path / "other.mp3")
        return httpx.Response(200, content=audio)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        FishVoiceClient("hidden", client=http, cache_dir=tmp_path / "cache").synthesize(
            "Sentence.", "ref", tmp_path / "first.mp3")
    assert len(calls) == 1


def test_parameter_change_does_not_reuse_wrong_voice(tmp_path, audio):
    calls = []
    with httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, content=audio))) as http:
        fish = FishVoiceClient("hidden", client=http, cache_dir=tmp_path / "cache")
        fish.synthesize("Sentence.", "ref-one", tmp_path / "a.mp3")
        fish.synthesize("Sentence.", "ref-two", tmp_path / "b.mp3")
    assert len(calls) == 2


def test_timestamp_snapshots_replace_by_sequence_while_audio_always_appends(tmp_path, audio):
    events = [
        {"audio_base64": base64.b64encode(audio).decode(), "alignment": {"segments": [{"text":"One", "start":0, "end":0.1}]},
         "chunk_seq":0, "chunk_audio_offset_sec":0},
        {"audio_base64":"", "alignment":{"segments":[{"text":"One","start":0,"end":0.2}]},
         "chunk_seq":0, "chunk_audio_offset_sec":0},
        {"audio_base64":"", "alignment":{"segments":[{"text":"sentence.","start":0,"end":0.1}]},
         "chunk_seq":1, "chunk_audio_offset_sec":0.2},
    ]
    content = "".join("data: " + json.dumps(e) + "\n\n" for e in events)
    seen=[]
    with httpx.Client(transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200, text=content))) as http:
        target = tmp_path / "out.mp3"
        FishVoiceClient("hidden", client=http, timestamps=True, cache_dir=tmp_path / "cache").synthesize("One sentence.", "ref", target)
    data=json.loads(target.with_suffix(".alignment.json").read_text())
    assert data["method"] == "fish_provider_timestamps" and data["precision"] == "unmeasured"
    assert len(data["words"]) == 2 and data["words"][0]["end"] == 0.2
    assert data["words"][1]["start"] == 0.2
    assert seen[0].url.path == "/v1/tts/stream/with-timestamp"


def test_unknown_model_rejected_before_spending(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("must not POST"))) as http:
        with pytest.raises(FishVoiceError, match="model"):
            FishVoiceClient("hidden", "invalid-model", client=http).synthesize("Sentence.", "ref", tmp_path / "a.mp3")
