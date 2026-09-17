import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from kitok.batch_import import validate_batch
from kitok.dashboard import _dialogue_lines
from kitok.generation import GenerationPlan
from kitok.models import ContentItem, ContentQueue, MPTTask, ValidationResult
from kitok.pipeline import Pipeline
from kitok.queue_editor import add_batch, edit_item, queue_digest
from kitok.regeneration import ReadyRegenerator


def dialogue(cid="one", visual="minecraft"):
    return ContentItem.model_validate({
        "id": cid, "subject": "Octopus", "keywords": ["octopus"], "caption": "Octopus fact",
        "publish_at": "2026-09-20T13:00:00+02:00", "content_format": "dialogue",
        "visual_profile": visual, "dialogue_preset": "rick_morty_es",
        "dialogue": [{"speaker": "rick_es", "text": "Los pulpos tienen tres corazones."},
                     {"speaker": "morty_es", "text": "¿Tres corazones?"}],
    })


@pytest.mark.parametrize("visual,expect_mpt", [("pexels", True), ("minecraft", False)])
def test_pipeline_dialogue_uses_shared_generation_then_validator(local_kitok, monkeypatch, tmp_path,
                                                                  visual, expect_mpt):
    settings, _, state, _ = local_kitok
    settings.ensure_directories()
    item = dialogue(visual=visual)
    queue = ContentQueue(items=[item])
    state.upsert(item.id, status="pending", attempts=0, mpt_task_id=None)
    client = Mock()
    client.submit_video.return_value = "task"
    client.get_task.return_value = MPTTask(task_id="task", state=1, videos=["visual"])
    client.download_artifact.side_effect = lambda artifact, path: path.write_bytes(b"visual")
    pipeline = Pipeline(settings, queue, state, client, {"voice_name": "alvaro"})
    plan = GenerationPlan({"voice_name": "no-voice", "subtitle_enabled": False},
                          SimpleNamespace(), tmp_path / "clip.mp4" if not expect_mpt else None)
    pipeline.generator.plan = Mock(return_value=plan)
    def finish(item, plan, source, target, workspace):
        target.write_bytes(b"composed")
        return target
    pipeline.generator.finish = Mock(side_effect=finish)
    pipeline.validator.prepare = Mock(return_value=ValidationResult(ok=True))
    pipeline.process(ids={item.id})
    assert state.get(item.id)["status"] == "ready"
    assert settings.local_ready_dir.joinpath(next(settings.local_ready_dir.glob("*.mp4")).name).read_bytes() == b"composed"
    pipeline.validator.prepare.assert_called_once()
    if expect_mpt:
        client.submit_video.assert_called_once_with(item, plan.preset)
        assert pipeline.generator.finish.call_args.args[2].name == "mpt_visual.mp4"
    else:
        client.submit_video.assert_not_called()
        client.download_artifact.assert_not_called()


@pytest.mark.parametrize("visual,expect_mpt", [("minecraft", False), ("pexels", True)])
def test_regenerator_dialogue_uses_shared_generation_and_validation(local_kitok, tmp_path,
                                                                    visual, expect_mpt):
    settings, _, state, _ = local_kitok
    settings.ensure_directories()
    item = dialogue(visual=visual)
    queue = ContentQueue(items=[item])
    state.upsert(item.id, status="ready", attempts=1, mpt_task_id="old")
    client = Mock()
    client.submit_video.return_value = "fresh-task"
    client.get_task.return_value = MPTTask(task_id="fresh-task", state=1, videos=["visual"])
    client.download_artifact.side_effect = lambda artifact, path: path.write_bytes(b"visual")
    regen = ReadyRegenerator(settings, queue, state, client, {}, print_line=lambda _: None)
    plan = GenerationPlan({"voice_name": "no-voice", "subtitle_enabled": False},
                          SimpleNamespace(), tmp_path / "clip.mp4" if not expect_mpt else None)
    regen.generator.plan = Mock(return_value=plan)
    regen.generator.finish = Mock(side_effect=lambda item, plan, source, target, workspace: target.write_bytes(b"composed"))
    regen.validator.prepare = Mock(return_value=ValidationResult(ok=True))
    result = regen.run(ids={item.id})
    assert result.regenerated == 1
    assert state.get(item.id)["regeneration_status"] == "succeeded"
    assert next(settings.local_ready_dir.glob("*.mp4")).read_bytes() == b"composed"
    if expect_mpt:
        client.submit_video.assert_called_once_with(item, plan.preset)
    else:
        client.submit_video.assert_not_called()
    regen.validator.prepare.assert_called_once()


def test_editor_generation_fields_lock_and_batch_atomic(local_kitok):
    settings, _, state, _ = local_kitok
    before = settings.queue_path.read_bytes()
    with pytest.raises(ValueError, match="before generation"):
        edit_item(settings.queue_path, state, "one", {"voice_profile": "rick_es"},
                  expected_revision=queue_digest(settings.queue_path))
    assert settings.queue_path.read_bytes() == before
    state.upsert("one", status="pending", attempts=0, mpt_task_id=None)
    edited = edit_item(settings.queue_path, state, "one", {"voice_profile": "rick_es"},
                       expected_revision=queue_digest(settings.queue_path))
    assert edited.voice_profile == "rick_es"
    valid = dialogue("new").model_dump(mode="json")
    valid["publish_at"] = "2026-09-24T13:00:00+02:00"
    invalid = {**valid, "id": "bad", "voice_profile": "unknown", "publish_at": "2026-09-25T13:00:00+02:00"}
    before = settings.queue_path.read_bytes()
    with pytest.raises(ValueError, match="Batch import rejected"):
        add_batch(settings.queue_path, state, [valid, invalid], expected_revision=queue_digest(settings.queue_path))
    assert settings.queue_path.read_bytes() == before
    added = add_batch(settings.queue_path, state, [valid], expected_revision=queue_digest(settings.queue_path))
    assert added[0].dialogue_preset == "rick_morty_es"
    single = {"id": "single", "topic": "Single voice", "script": "A sufficiently long script for Rick.",
              "caption": "A fact", "video_terms": ["fact"], "voice_profile": "rick_es",
              "visual_profile": "pexels", "publish_at": "2026-09-26T13:00:00+02:00"}
    imported = add_batch(settings.queue_path, state, [single], expected_revision=queue_digest(settings.queue_path))
    assert imported[0].voice_profile == "rick_es"


def test_dashboard_conditional_controls_and_no_external_calls(local_kitok, monkeypatch):
    from kitok.control_panel import ControlPanel
    settings, _, _, _ = local_kitok
    monkeypatch.setattr("kitok.control_panel.Settings", lambda: settings)
    network = Mock(side_effect=AssertionError("external call during render"))
    monkeypatch.setattr(ControlPanel, "refresh_buffer", network)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "dashboard.py", default_timeout=20).run()
    app.sidebar.radio[0].set_value("Content").run()
    assert not app.exception
    assert any(widget.label == "Voice" for widget in app.selectbox)
    next(widget for widget in app.selectbox if widget.label == "Format").set_value("dialogue").run()
    assert not app.exception
    labels = {widget.label for widget in app.selectbox}
    assert {"Dialogue preset", "Visual style", "Character overlay"} <= labels
    assert "Voice" not in labels
    network.assert_not_called()


def test_dialogue_ui_line_parser():
    assert _dialogue_lines("Rick: Hola\nMorty: ¿Qué?") == [
        {"speaker": "rick_es", "text": "Hola"}, {"speaker": "morty_es", "text": "¿Qué?"}]
    with pytest.raises(ValueError, match="one per line"):
        _dialogue_lines("Someone: Hola")
