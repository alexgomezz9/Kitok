from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from kitok.editing import graphics


@pytest.mark.parametrize("kind,data", [
    ("identity", {"name": "NioNio", "supporting_line": "An account alias"}),
    ("metric", {"value": "$70,000", "label": "Paredes’ reported loss"}),
    ("metric", {"value": "$300,000", "label": "Reported winnings in one stretch"}),
    ("hidden_information", {}),
    ("hidden_information", {"state": "exposed"}),
    ("identity", {"name": "A question", "icon": "question"}),
    ("identity", {"name": "A wider argument", "icon": "none"}),
])
@pytest.mark.parametrize("dimensions", [(1920, 1080), (1080, 1920), (640, 480)])
def test_templates_render_opaque_landscape_and_portrait(tmp_path, kind, data, dimensions):
    output = tmp_path / "plate.png"
    assert graphics.render_graphic(kind, data, output, width=dimensions[0], height=dimensions[1]) == output
    with Image.open(output) as image:
        assert image.size == dimensions
        assert image.mode == "RGB"
        assert len(image.getcolors(maxcolors=1000000)) > 10


def test_metric_values_and_labels_are_supplied_without_conflation(tmp_path, monkeypatch):
    rendered = []
    original = graphics._write

    def capture(draw, text, *args, **kwargs):
        rendered.append(text)
        return original(draw, text, *args, **kwargs)

    monkeypatch.setattr(graphics, "_write", capture)
    graphics.render_graphic("metric", {"value": "$70,000", "label": "Paredes’ reported loss"}, tmp_path / "loss.png")
    assert "$70,000" in rendered
    assert "Paredes’ reported loss" in rendered
    assert not any("300,000" in value or "winnings" in value for value in rendered)
    rendered.clear()
    graphics.render_graphic("metric", {"value": "$300,000", "label": "Reported winnings in one stretch"}, tmp_path / "winnings.png")
    assert "$300,000" in rendered
    assert "Reported winnings in one stretch" in rendered
    assert not any("70,000" in value or "Paredes" in value for value in rendered)
    with pytest.raises(ValueError, match="label is required"):
        graphics.render_graphic("metric", {"value": "$70,000"}, tmp_path / "missing.png")


def test_illustration_disclaimer_is_visible_in_safe_area(tmp_path, monkeypatch):
    captured = []
    original = graphics._write

    def capture(draw, text, box, *args, **kwargs):
        captured.append((text, box))
        return original(draw, text, box, *args, **kwargs)

    monkeypatch.setattr(graphics, "_write", capture)
    graphics.render_graphic("hidden_information", {}, tmp_path / "diagram.png")
    disclaimer = next(box for text, box in captured if text == graphics.DISCLAIMER)
    assert disclaimer[0] >= 1920 * .06 and disclaimer[2] <= 1920 * .94
    assert disclaimer[1] >= 1080 * .06 and disclaimer[3] <= 1080 * .94
    assert any(text == "OWN PRIVATE CARDS" for text, _ in captured)
    assert any(text == "HIDDEN FROM THIS ACCOUNT" for text, _ in captured)


@pytest.mark.parametrize("value", [
    "María de los Ángeles Fernández — una identidad editorial larga",
    "ANameWithoutSpacesQueDebeDividirseSinSalirDelEncuadre" * 2,
])
def test_long_names_are_wrapped_inside_geometry(value):
    draw = ImageDraw.Draw(Image.new("RGB", (1920, 1080)))
    box = (144, 291, 1286, 626)
    font, text, spacing, bounds = graphics._fit(draw, value, box, 174, minimum=22, bold=True, max_lines=3)
    assert font.size >= 22
    assert bounds[2] - bounds[0] <= box[2] - box[0]
    assert bounds[3] - bounds[1] <= box[3] - box[1]
    assert "".join(text.split()) == "".join(value.split())


@pytest.mark.parametrize("data,style,dimensions", [
    ({"value": "1", "label": "a" * 161}, None, (1920, 1080)),
    ({"value": "1", "label": "Label\x00"}, None, (1920, 1080)),
    ({"value": "1", "label": "Label"}, {"accent": "red"}, (1920, 1080)),
    ({"value": "1", "label": "Label"}, {"font": "/tmp/font.ttf"}, (1920, 1080)),
    ({"value": "1", "label": "Label"}, None, (100000, 1080)),
    ({"value": "1", "label": "Label"}, None, (True, 1080)),
])
def test_bad_inputs_do_not_create_output(tmp_path, data, style, dimensions):
    output = tmp_path / "invalid.png"
    with pytest.raises(ValueError):
        graphics.render_graphic("metric", data, output, width=dimensions[0], height=dimensions[1], style=style)
    assert not output.exists()


def test_unfittable_text_is_rejected_without_silent_truncation():
    draw = ImageDraw.Draw(Image.new("RGB", (640, 480)))
    with pytest.raises(ValueError, match="does not fit"):
        graphics._fit(draw, "Too long " * 40, (0, 0, 50, 20), 50, minimum=18, max_lines=2)


def test_hidden_information_state_changes_unilateral_access(tmp_path, monkeypatch):
    texts, segments = [], []
    original_write, original_line = graphics._write, ImageDraw.ImageDraw.line

    def capture_write(draw, text, *args, **kwargs):
        texts.append(text)
        return original_write(draw, text, *args, **kwargs)

    def capture_line(draw, xy, *args, **kwargs):
        # Drawn polylines have flat coordinates, as do card-back stripes.
        segments.append(xy)
        return original_line(draw, xy, *args, **kwargs)

    monkeypatch.setattr(graphics, "_write", capture_write)
    monkeypatch.setattr(ImageDraw.ImageDraw, "line", capture_line)
    graphics.render_graphic("hidden_information", {}, tmp_path / "private.png")
    assert "ACCOUNT VIEW" in texts and "PRIVILEGED VIEW" not in texts
    assert texts.count("VISIBLE") == 2  # Only this account's own two generic cards.
    assert "HIDDEN FROM THIS ACCOUNT" in texts
    assert not any(min(xy[::2]) < 960 < max(xy[::2]) for xy in segments)
    assert graphics.DISCLAIMER in texts
    texts.clear()
    segments.clear()
    graphics.render_graphic("hidden_information", {"state": "exposed"}, tmp_path / "exposed.png")
    assert "PRIVILEGED VIEW" in texts and "ACCOUNT VIEW" not in texts
    assert texts.count("VISIBLE") == 4
    assert "VISIBLE TO THIS ACCOUNT" in texts
    crossing = [xy for xy in segments if min(xy[::2]) < 960 < max(xy[::2])]
    assert crossing and all(xy[0] < xy[2] for xy in crossing)
    assert graphics.DISCLAIMER in texts
    assert (tmp_path / "private.png").read_bytes() != (tmp_path / "exposed.png").read_bytes()


@pytest.mark.parametrize("icon", ["person", "question", "none"])
def test_identity_requested_icon_and_none_wider_text(tmp_path, monkeypatch, icon):
    captured = []
    original = graphics._write

    def capture(draw, text, box, *args, **kwargs):
        captured.append((text, box))
        return original(draw, text, box, *args, **kwargs)

    monkeypatch.setattr(graphics, "_write", capture)
    graphics.render_graphic("identity", {"name": "An argument", "icon": icon}, tmp_path / f"{icon}.png")
    assert any(text == "?" for text, _ in captured) == (icon == "question")
    box = next(box for text, box in captured if text == "An argument")
    assert box[2] == pytest.approx(1920 * (.925 if icon == "none" else .67))


@pytest.mark.parametrize("kind,data", [
    ("identity", {"name": "A question", "icon": "unknown"}),
    ("identity", {"name": "A question", "icon": []}),
    ("hidden_information", {"state": "unknown"}),
    ("hidden_information", {"state": []}),
])
def test_invalid_icon_and_state_are_rejected(tmp_path, kind, data):
    path = tmp_path / "invalid.png"
    with pytest.raises(ValueError, match="Graphic (icon|state)"):
        graphics.render_graphic(kind, data, path)
    assert not path.exists()
