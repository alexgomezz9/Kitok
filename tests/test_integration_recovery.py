from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from pydantic import SecretStr

from kitok.config import Settings
from kitok.fish_voice import FishVoiceClient, FishVoiceError
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


def test_fish_server_error_is_never_retried(tmp_path, monkeypatch):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(503 if len(seen) == 1 else 200,
                              content=b"ID3audio", headers={"content-type": "audio/mpeg"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(FishVoiceError, match="HTTP 503"):
            FishVoiceClient("test-key", attempts=2, client=http).synthesize("Hola", "ref", tmp_path / "voice.mp3")
    assert len(seen) == 1


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
    assert "Historical MPT task lost-task requires review" in record["last_error"]
    client.submit_video.assert_not_called()


def test_stalled_pipeline_task_is_failed_and_retains_id(local_kitok, monkeypatch):
    settings, queue, state, _ = local_kitok
    settings.ensure_directories()
    state.upsert("one", status="generating", mpt_task_id="stuck-task")
    client = Mock()
    Pipeline(settings, queue, state, client, {}).process(ids={"one"})
    record = state.get("one")
    assert record["status"] == "failed" and record["mpt_task_id"] == "stuck-task"
    assert "Historical MPT task stuck-task requires review" in record["last_error"]
    client.submit_video.assert_not_called()


def test_historical_task_retry_preserves_id_and_never_synthesizes(local_kitok, monkeypatch):
    settings, queue, state, _ = local_kitok
    settings.ensure_directories()
    state.upsert("one", status="failed", mpt_task_id="paid-unknown")
    plan = Mock(side_effect=AssertionError("Voice must not be synthesized"))
    monkeypatch.setattr(GenerationService, "plan", plan)
    client = Mock()
    Pipeline(settings, queue, state, client, {}).process(ids={"one"}, retry_failed=True)
    assert state.get("one")["mpt_task_id"] == "paid-unknown"
    assert "requires review" in state.get("one")["last_error"]
    plan.assert_not_called()
    client.get_task.assert_not_called()
    client.submit_video.assert_not_called()


@pytest.mark.parametrize("status", ["generating", "generated", "submitted"])
def test_interrupted_native_job_never_restarts_without_explicit_retry(local_kitok, status):
    settings, queue, state, _ = local_kitok
    settings.ensure_directories()
    state.upsert("one", status=status, generation_renderer="native", attempts=1)
    pipeline = Pipeline(settings, queue, state, None, {})
    pipeline.generator.plan = Mock(side_effect=AssertionError("must not synthesize again"))
    before = state.path.read_bytes()
    pipeline.process(ids={"one"})
    assert state.path.read_bytes() == before
    pipeline.generator.plan.assert_not_called()


def test_interrupted_native_retry_requires_explicit_invocation(local_kitok):
    settings, queue, state, _ = local_kitok
    settings.ensure_directories()
    state.upsert("one", status="generating", generation_renderer="native", attempts=1)
    pipeline = Pipeline(settings, queue, state, None, {})
    pipeline.generator.plan = Mock(side_effect=RuntimeError("explicit retry reached generation"))
    pipeline.process(ids={"one"}, retry_failed=True)
    pipeline.generator.plan.assert_called_once()
    assert state.get("one")["attempts"] == 2


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
    class FakeGenerator:
        def __init__(self, settings, preset, *, on_stage=None): pass
        def plan(self, item, root):
            return GenerationPlan({"video_script": "ocean"}, SimpleNamespace(timeline=[]))
        def finish(self, item, plan, visual, staged, root): staged.write_bytes(b"final")
    monkeypatch.setattr(smoke, "GenerationService", FakeGenerator)
    monkeypatch.setattr(smoke, "PROJECT_ROOT", tmp_path)
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
