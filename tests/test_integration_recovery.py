from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from pydantic import SecretStr

from kitok.config import Settings
from kitok.fish_voice import FishVoiceClient
from kitok.generation import GenerationPlan, GenerationService
from kitok.models import ContentItem, ContentQueue, MPTTask, ValidationResult
from kitok.mpt_client import MPTClient, MPTError, MPTTaskNotFound
from kitok.mpt_watch import MPTTaskStalled, MPTTaskTimedOut, wait_for_mpt_task
from kitok.pipeline import Pipeline
from kitok.smoke_test import run_dialogue_pexels_smoke


def test_fish_uses_configurable_long_read_timeout():
    fish = FishVoiceClient("test-key", timeout=180)
    try:
        assert fish.client.timeout.connect == 10
        assert fish.client.timeout.read == 180
        assert fish.client.timeout.write == 30
        assert fish.client.timeout.pool == 10
    finally:
        fish.close()
    assert Settings(_env_file=None, fish_tts_timeout_seconds=210).fish_tts_timeout_seconds == 210


def test_fish_retries_server_error_and_limits_attempts(tmp_path, monkeypatch):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(503 if len(seen) == 1 else 200,
                              content=b"ID3audio", headers={"content-type": "audio/mpeg"})
    monkeypatch.setattr("kitok.fish_voice.time.sleep", lambda _: None)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        FishVoiceClient("test-key", attempts=2, client=http).synthesize("Hola", "ref", tmp_path / "voice.mp3")
    assert len(seen) == 2


def test_mpt_submit_timeout_never_reposts():
    seen = []
    def handler(request):
        seen.append(request)
        raise httpx.ReadTimeout("ambiguous response")
    client = MPTClient("http://mpt.invalid", retry_attempts=4)
    client.client.close()
    client.client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://mpt.invalid")
    item = ContentItem.model_validate({"id": "one", "subject": "Subject", "script": "A sufficiently long script.",
                                       "keywords": ["ocean"], "caption": "Caption",
                                       "publish_at": "2026-09-20T13:00:00+02:00"})
    with pytest.raises(MPTError, match="Check MPT task history"):
        client.submit_video(item, {"voice_name": "es-ES-AlvaroNeural"})
    assert len(seen) == 1
    client.close()


def test_missing_mpt_task_is_distinct_error():
    client = MPTClient("http://mpt.invalid", retry_attempts=4)
    client.client.close()
    client.client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(404, json={"status": 404, "message": "task not found"})
    ), base_url="http://mpt.invalid")
    with pytest.raises(MPTTaskNotFound, match="MPT task no longer exists: lost-task"):
        client.get_task("lost-task")
    client.close()


def test_stall_and_global_timeout_include_task_context(monkeypatch):
    task = MPTTask(task_id="task-1", state=4, progress=50, failed_stage=None, error=None)
    client = Mock(get_task=Mock(return_value=task))
    clock = iter([0, 0, 5, 11])
    monkeypatch.setattr("kitok.mpt_watch.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("kitok.mpt_watch.time.sleep", lambda _: None)
    with pytest.raises(MPTTaskStalled) as error:
        wait_for_mpt_task(client, "task-1", poll_seconds=1, timeout_seconds=100,
                          stall_seconds=10, on_update=lambda task: None)
    assert all(part in str(error.value) for part in ("task_id=task-1", "state=4", "progress=50",
                                                    "unchanged=11s", "failed_stage=None", "error=None"))
    clock = iter([0, 0, 5, 11])
    with pytest.raises(MPTTaskTimedOut, match="global timeout"):
        wait_for_mpt_task(client, "task-1", poll_seconds=1, timeout_seconds=10,
                          stall_seconds=100, on_update=lambda task: None)


def test_disappeared_task_fails_without_new_submit(local_kitok):
    settings, queue, state, _ = local_kitok
    settings.ensure_directories()
    state.upsert("one", status="submitted", mpt_task_id="lost-task")
    client = Mock()
    client.get_task.side_effect = MPTTaskNotFound("MPT task no longer exists: lost-task")
    Pipeline(settings, queue, state, client, {}).process(ids={"one"})
    record = state.get("one")
    assert record["status"] == "failed"
    assert record["mpt_task_id"] == "lost-task"
    assert "MPT task no longer exists: lost-task" in record["last_error"]
    client.submit_video.assert_not_called()


def test_stalled_pipeline_task_is_failed_and_retains_id(local_kitok, monkeypatch):
    settings, queue, state, _ = local_kitok
    settings.ensure_directories()
    state.upsert("one", status="generating", mpt_task_id="stuck-task")
    client = Mock()
    monkeypatch.setattr("kitok.pipeline.wait_for_mpt_task", Mock(
        side_effect=MPTTaskStalled("MPT task progress stalled (task_id=stuck-task, state=4, progress=50, unchanged=720s)")))
    Pipeline(settings, queue, state, client, {}).process(ids={"one"})
    record = state.get("one")
    assert record["status"] == "failed" and record["mpt_task_id"] == "stuck-task"
    assert "progress=50" in record["last_error"]
    client.submit_video.assert_not_called()


def test_dialogue_pexels_payload_is_short_and_preserves_explainer(local_kitok, monkeypatch, tmp_path):
    settings = local_kitok[0]
    fish = Mock()
    monkeypatch.setattr("kitok.generation.FishVoiceClient", Mock(return_value=fish))
    monkeypatch.setattr("kitok.generation.DialogueAudioService.generate", lambda *args: SimpleNamespace())
    raw = {"id": "dialogue", "subject": "The surprising story of octopuses",
           "script": "", "keywords": ["octopus", "ocean"], "caption": "A fact",
           "publish_at": "2026-09-20T13:00:00+02:00", "content_format": "dialogue",
           "dialogue": [{"speaker": "rick_es", "text": "A fairly long first dialogue turn."},
                        {"speaker": "morty_es", "text": "A fairly long second dialogue turn."}]}
    item = ContentItem.model_validate(raw)
    preset = {"video_aspect": "9:16", "video_clip_duration": 2, "video_concat_mode": "sequential",
              "video_transition_mode": None, "video_count": 1, "video_source": "pexels",
              "voice_name": "es-ES-AlvaroNeural", "subtitle_enabled": True,
              "bgm_type": "", "bgm_volume": 0}
    plan = GenerationService(settings, preset).plan(item, tmp_path)
    request = MPTClient.build_payload(item, plan.preset)
    assert request["video_script"] == "octopus"
    assert request["video_subject"] == item.subject
    assert request["video_terms"] == item.keywords
    assert request["voice_name"] == "no-voice" and request["subtitle_enabled"] is False
    assert {key: request[key] for key in ("video_aspect", "video_clip_duration", "video_concat_mode",
                                           "video_transition_mode", "video_count", "video_source",
                                           "bgm_type", "bgm_volume")} == {key: preset[key] for key in
                                                                        ("video_aspect", "video_clip_duration",
                                                                         "video_concat_mode", "video_transition_mode",
                                                                         "video_count", "video_source", "bgm_type", "bgm_volume")}
    explainer = ContentItem.model_validate({**raw, "content_format": "explainer", "dialogue": None,
                                            "script": "A sufficiently long explainer narration."})
    exp = MPTClient.build_payload(explainer, GenerationService(settings, preset).plan(explainer, tmp_path).preset)
    assert exp["video_script"] == explainer.script
    assert exp["subtitle_enabled"] is True
    assert preset["voice_name"] == "es-ES-AlvaroNeural"


def test_smoke_command_uses_only_temporary_state(local_kitok, tmp_path, monkeypatch):
    import kitok.smoke_test as smoke
    settings, _, state, _ = local_kitok
    settings.fish_api_key = SecretStr("test-key")
    preset = tmp_path / "preset.json"
    preset.write_text('{"video_source":"pexels","voice_name":"es-ES-AlvaroNeural"}')
    settings.mpt_preset_path = preset
    before_queue = settings.queue_path.read_bytes()
    before_state = state.path.read_bytes()
    settings.local_ready_dir.mkdir(parents=True, exist_ok=True)
    existing_ready = settings.local_ready_dir / "existing.mp4"
    existing_ready.write_bytes(b"existing-ready-video")
    class FakeMPT:
        build_payload = staticmethod(MPTClient.build_payload)
        def __init__(self, *args, **kwargs): pass
        def check(self): return {}
        def submit_video(self, item, preset): return "task"
        def download_artifact(self, artifact, destination): destination.write_bytes(b"visual")
        def close(self): pass
    class FakeGenerator:
        def __init__(self, settings, preset, *, on_stage=None): pass
        def plan(self, item, root):
            return GenerationPlan({"video_script": "ocean"}, SimpleNamespace(timeline=[]))
        def finish(self, item, plan, visual, staged, root): staged.write_bytes(b"final")
    monkeypatch.setattr(smoke, "MPTClient", FakeMPT)
    monkeypatch.setattr(smoke, "GenerationService", FakeGenerator)
    monkeypatch.setattr(smoke, "wait_for_mpt_task", lambda client, task_id, **kwargs:
                        MPTTask(task_id=task_id, state=1, videos=["visual"]))
    monkeypatch.setattr(smoke.VideoValidator, "prepare", lambda *args:
                        ValidationResult(ok=True, duration=8, width=1080, height=1920,
                                         fps=30, video_codec="h264", pixel_format="yuv420p",
                                         audio_codec="aac", audio_profile="LC", audio_sample_rate=48000,
                                         audio_bitrate=120000))
    lines = []
    assert run_dialogue_pexels_smoke(settings=settings, output=lines.append) == 0
    assert settings.queue_path.read_bytes() == before_queue
    assert state.path.read_bytes() == before_state
    assert existing_ready.read_bytes() == b"existing-ready-video"
    assert not list(tmp_path.glob("kitok-dialogue-smoke-*"))
    assert any("Validation" in line and "OK" in line for line in lines)


def test_smoke_cli_routes_before_production_queue_load(monkeypatch):
    from kitok import cli
    import kitok.smoke_test as smoke
    called = Mock(return_value=0)
    monkeypatch.setattr(smoke, "run_dialogue_pexels_smoke", called)
    monkeypatch.setattr(cli, "load_all", Mock(side_effect=AssertionError("production queue loaded")))
    assert cli.main(["--smoke-test", "dialogue-pexels"]) == 0
    called.assert_called_once()
