"""Local publication preparation never invents story facts or calls providers."""
import json

from PIL import Image
import pytest

from kitok.youtube_stickman_es.packaging import compose_thumbnail, prepare_packaging


SCRIPT = "El mecanismo mueve una rueda.\n\nLa rueda no genera energía.\n\nUna persona observa el resultado."


def materials(duration=36):
    return {"title": "Título aprobado: la rueda", "script": SCRIPT, "duration": duration,
            "scenes": [{"id": f"s{i}", "start": i * duration / 3, "end": (i + 1) * duration / 3,
                        "narration": text, "visual_description": f"Ilustración {i}"}
                       for i, text in enumerate(SCRIPT.split("\n\n"))]}


def test_preserves_title_and_supplied_narration_with_real_chapter_times(tmp_path):
    supplied = materials()
    result = prepare_packaging(tmp_path, **supplied,
                               sources=[{"title": "Fuente del operador", "url": "https://example.org/material"}])
    metadata = json.loads((tmp_path / "metadata_youtube.json").read_text())
    assert metadata["title"] == supplied["title"]
    assert metadata["title_alternatives"] == []
    assert metadata["description_mode"] == "extractive_supplied_script"
    assert (tmp_path / "capitulos.txt").read_text() == (
        "00:00 El mecanismo mueve una rueda.\n"
        "00:12 La rueda no genera energía.\n"
        "00:24 Una persona observa el resultado.\n")
    description = (tmp_path / "descripcion_youtube.txt").read_text()
    assert SCRIPT in description
    assert "https://example.org/material" in description
    assert result["chapters"]["timing_source"] == "scene_timestamps"
    assert result["concepts_ready"] and not result["thumbnails_ready"]
    assert result["status"] == "thumbnail_images_required"
    assert all(item["status"] == "missing" for item in result["thumbnails"])


def test_three_distinct_concepts_without_placeholder_pngs(tmp_path):
    prepare_packaging(tmp_path, **materials(), references=[{"path": "referencias/interior.png"}])
    concepts = json.loads((tmp_path / "miniaturas/conceptos.json").read_text())["concepts"]
    assert [item["concept"] for item in concepts] == ["mecanismo", "anomalia", "consecuencia_humana"]
    assert len({item["prompt"] for item in concepts}) == 3
    assert all(SCRIPT in item["prompt"] for item in concepts)
    assert all(item["reference_files"] == [{"path": "referencias/interior.png"}] for item in concepts)
    assert not list(tmp_path.rglob("*.png"))


def test_editorial_description_and_optional_real_font_copy_are_explicit(tmp_path):
    description='Descripción editorial aportada para el vídeo.'
    result=prepare_packaging(tmp_path,**materials(),description=description,thumbnail_text={'A':'UNA RUEDA'})
    assert result['metadata']['description_mode']=='editorial_supplied'
    assert description in (tmp_path/'descripcion_youtube.txt').read_text()
    concepts=json.loads((tmp_path/'miniaturas/conceptos.json').read_text())['concepts']
    assert concepts[0]['text']=='UNA RUEDA' and concepts[1]['text']==''


def test_short_fixture_does_not_fabricate_eligible_chapters(tmp_path):
    result = prepare_packaging(tmp_path, **materials(duration=12))
    assert result["chapters"]["status"] == "insufficient_duration"
    assert result["chapters"]["entries"] == []
    assert (tmp_path / "capitulos.txt").read_text() == ""


def test_explicit_chapter_captions_are_preserved(tmp_path):
    result = prepare_packaging(tmp_path, **materials(), chapters=[
        {"scene_id": "s0", "title": "¿Qué mueve la rueda?"},
        {"scene_id": "s1", "title": "No crea energía"},
        {"scene_id": "s2", "title": "La consecuencia"},
    ])
    assert result["chapters"]["entries"][0]["title"] == "¿Qué mueve la rueda?"
    assert "No crea energía" in (tmp_path / "capitulos.txt").read_text()


@pytest.mark.parametrize("chapters", [
    [{"scene_id": "missing", "title": "Desconocido"}],
    [{"scene_id": "s0", "title": "Uno"}],
    [{"scene_id": "s1", "title": "Uno"}, {"scene_id": "s0", "title": "Dos"}, {"scene_id": "s2", "title": "Tres"}],
    [{"scene_id": "s0", "title": "Error\n00:00 Otro"}],
])
def test_invalid_explicit_chapters_rejected_before_writes(tmp_path, chapters):
    with pytest.raises(ValueError):
        prepare_packaging(tmp_path, **materials(), chapters=chapters)
    assert list(tmp_path.iterdir()) == []


def test_repeat_is_identical_and_differing_operator_file_is_preserved(tmp_path):
    prepare_packaging(tmp_path, **materials())
    expected = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    prepare_packaging(tmp_path, **materials())
    assert expected == {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    owned = tmp_path / "descripcion_youtube.txt"
    owned.write_text("Descripción aprobada manualmente.")
    with pytest.raises(FileExistsError, match="new episode revision"):
        prepare_packaging(tmp_path, **materials())
    assert owned.read_text() == "Descripción aprobada manualmente."


def test_output_conflict_preflight_prevents_partial_creation(tmp_path):
    (tmp_path / "metadata_youtube.json").write_text("operator data")
    with pytest.raises(FileExistsError):
        prepare_packaging(tmp_path, **materials())
    assert sorted(path.name for path in tmp_path.iterdir()) == ["metadata_youtube.json"]


@pytest.mark.parametrize("name", ["descripcion_youtube.txt", "miniaturas"])
def test_rejects_output_symlinks(tmp_path, name):
    episode = tmp_path / "episode"
    episode.mkdir()
    target = tmp_path / "protected"
    if name == "miniaturas":
        target.mkdir()
    else:
        target.write_text("protected")
    (episode / name).symlink_to(target)
    with pytest.raises(ValueError, match="Symlinks"):
        prepare_packaging(episode, **materials())
    assert not (episode / "metadata_youtube.json").exists()


def test_real_png_composition_and_idempotent_packaging_availability(tmp_path):
    supplied = materials()
    prepare_packaging(tmp_path, **supplied)
    background = tmp_path / "illustration.png"
    Image.new("RGB", (1600, 900), "#aaccee").save(background)
    for concept in "ABC":
        output = tmp_path / f"miniaturas/miniatura_{concept}.png"
        result = compose_thumbnail(background, output, "NO CREA ENERGÍA")
        assert result["status"] == "prepared_review_required"
        with Image.open(output) as image:
            assert image.size == (1280, 720)
            assert image.format == "PNG"
            assert image.getpixel((0, 0)) == (170, 204, 238)
        # Same result is reproducible and accepted.
        compose_thumbnail(background, output, "NO CREA ENERGÍA")
    result = prepare_packaging(tmp_path, **supplied)
    assert result["thumbnails_ready"]
    assert result["status"] == "human_review_required"


def test_composition_preserves_whole_non_widescreen_illustration(tmp_path):
    background = tmp_path / "portrait.png"
    Image.new("RGB", (640, 720), "red").save(background)
    compose_thumbnail(background, tmp_path / "result.png")
    with Image.open(tmp_path / "result.png") as image:
        assert image.getpixel((640, 360)) == (255, 0, 0)
        assert image.getpixel((0, 360)) == (250, 248, 242)


def test_composition_rejects_missing_small_corrupt_and_operator_overwrite(tmp_path):
    with pytest.raises(FileNotFoundError):
        compose_thumbnail(tmp_path / "missing.png", tmp_path / "result.png")
    source = tmp_path / "source.png"
    source.write_bytes(b"corrupt")
    with pytest.raises(OSError):
        compose_thumbnail(source, tmp_path / "result.png")
    Image.new("RGB", (100, 100)).save(source)
    with pytest.raises(ValueError, match="too small"):
        compose_thumbnail(source, tmp_path / "result.png")
    Image.new("RGB", (1280, 720)).save(source)
    with pytest.raises(ValueError, match="zero to three"):
        compose_thumbnail(source, tmp_path / "result.png", "UNA FRASE CON CUATRO")
    output = tmp_path / "result.png"
    output.write_bytes(b"operator output")
    with pytest.raises(FileExistsError):
        compose_thumbnail(source, output)
    assert output.read_bytes() == b"operator output"


def test_corrupt_thumbnail_is_not_claimed_ready(tmp_path):
    prepare_packaging(tmp_path, **materials())
    (tmp_path / "miniaturas/miniatura_A.png").write_bytes(b"corrupt")
    result = prepare_packaging(tmp_path, **materials())
    assert result["thumbnails"][0]["status"] == "invalid"
    assert not result["thumbnails_ready"]


def test_long_opening_extracts_whole_sentence_and_keeps_negation(tmp_path):
    supplied = materials()
    supplied["script"] = "La rueda no produce energía. " + "Una explicación larga. " * 300
    result = prepare_packaging(tmp_path, **supplied)
    assert result["chapters"]["status"] == "editorial_selection_required"
    assert "La rueda no produce energía.\n" in (tmp_path / "descripcion_youtube.txt").read_text()


def test_rejects_invented_sources_and_bad_scene_clock(tmp_path):
    with pytest.raises(ValueError, match="HTTP"):
        prepare_packaging(tmp_path, **materials(), sources=[{"title": "Fuente", "url": "invented"}])
    supplied = materials()
    supplied["scenes"][1]["start"] = 2
    with pytest.raises(ValueError, match="timestamps"):
        prepare_packaging(tmp_path, **supplied)
    assert list(tmp_path.iterdir()) == []
