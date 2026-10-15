from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from kitok.editing.ass import clip_edit_filters, write_chunk_ass
from kitok.editing.manifest import build_edit_manifest, load_or_create_manifest
from kitok.longform.models import TimelineClip, TimelineSlot, VisualSection
from kitok.longform.timeline import build_semantic_timeline
from kitok.media.ffmpeg import EncoderSettings, FFmpegNativeEngine, RenderSpec


SCRIPT = "In 1998, the experiment began. The budget was $2.5 million. Why did it fail? A quiet room offered no explanation. It grew from 10 to 40."


def test_selective_editing_is_semantic_sparse_and_preserves_decimal_numbers():
    manifest = build_edit_manifest(SCRIPT, 40, ["laboratory", "money"])
    assert len(manifest.sections) == 5
    assert "$2.5 million" in manifest.sections[1].section
    assert {cue.kind for cue in manifest.cues} == {"date", "amount", "question", "comparison"}
    assert not any(cue.section == 3 for cue in manifest.cues)
    assert sum(cue.end - cue.start for cue in manifest.cues) <= 40 * .38
    assert not manifest.alignment["word_aligned"]
    assert manifest.alignment["precision_seconds"] is None
    assert manifest == build_edit_manifest(SCRIPT, 40, ["laboratory", "money"])


def test_provider_alignment_checked_against_exact_spoken_words():
    text = "[calm] The cost was $2 million. Why now?"
    tokens = "The cost was $2 million. Why now?".split()
    words = [{"word": token, "start": i, "end": i + .8} for i, token in enumerate(tokens)]
    manifest = build_edit_manifest(text, 8, ["money"], word_alignment={"method": "fish_provider_timestamps", "words": words})
    assert manifest.alignment["word_aligned"] is True
    assert manifest.alignment["confidence"] is None
    assert manifest.sections[1].audio_start == 5
    assert manifest.sections[0].audio_end == 4.8
    words[0]["word"] = "unrelated"
    with pytest.raises(ValueError, match="do not match"):
        build_edit_manifest(text, 8, ["money"], word_alignment={"words": words})


def test_manifest_preserves_operator_edits_and_rejects_other_script(tmp_path):
    path = tmp_path / "film.edit.json"
    manifest = load_or_create_manifest(path, SCRIPT, 40, ["laboratory"])
    data = manifest.to_dict()
    data["cues"][0]["text"] = "1998 · The beginning"
    path.write_text(json.dumps(data))
    updated = load_or_create_manifest(path, SCRIPT, 40, ["laboratory"])
    assert updated.cues[0].text == "1998 · The beginning"
    with pytest.raises(ValueError, match="another script"):
        load_or_create_manifest(path, SCRIPT + " A new story.", 40, ["laboratory"])
    data["cues"][0]["end"] = 500
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Invalid editable cue"):
        load_or_create_manifest(path, SCRIPT, 40, ["laboratory"])


def test_semantic_timeline_uses_supplied_visual_sections_and_measured_coverage():
    sections = [VisualSection("A busy laboratory.", ("laboratory",), 0, 6), VisualSection("Water fills the city.", ("flood water",), 6, 14)]
    timeline = build_semantic_timeline(sections, 14, ["laboratory", "flood water"])
    assert timeline[0].duration == 6
    assert timeline[0].query == "laboratory"
    assert timeline[1].query == "flood water"
    assert timeline[-1].end == 14


def test_ass_escapes_untrusted_text_and_only_affects_semantic_intervals(tmp_path):
    manifest = build_edit_manifest("Why {\\pos(1,1)} now? Normal narration follows.", 20, ["city"])
    path = tmp_path / "chunk.ass"
    assert write_chunk_ass(manifest, path, start=0, end=10, width=1280, height=720)
    content = path.read_text()
    assert r"{\pos(1,1)}" not in content
    assert r"\move(" in content
    assert r"\p1" in content
    assert not write_chunk_ass(manifest, tmp_path / "quiet.ass", start=10, end=20, width=1280, height=720)
    assert clip_edit_filters(manifest, 10, 10, 1280, 720, 30) == []


def test_color_profile_is_neutral_configurable_and_validated():
    manifest = build_edit_manifest(SCRIPT, 40, ["city"], style={"accent": "#17E0FA", "background": "#FFF3D0", "text": "#112233"})
    assert manifest.style.background == "#FFF3D0"
    with pytest.raises(ValueError, match="Invalid editing color"):
        build_edit_manifest(SCRIPT, 40, ["city"], style={"accent": "red:inject"})
