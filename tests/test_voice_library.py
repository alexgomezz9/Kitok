import copy
import hashlib
import json
from pathlib import Path

import pytest
import httpx

from kitok.voice_library import DEFAULT_REFERENCE, VoiceLibrary, VoiceLibraryError, discover_fish_voices


CATALOG = Path(__file__).resolve().parents[1] / "presets/voice_sources.json"


def test_baseline_preserved_and_new_alternatives_are_licensed(tmp_path):
    library = VoiceLibrary(CATALOG, tmp_path / "prefs.json")
    assert library.assigned("loose_thread")["reference_id"] == DEFAULT_REFERENCE
    choices = library.list()
    assert len(choices) == 11
    assert all(voice["api_licensed"] for voice in choices if voice["selectable"] and voice["id"] != "baseline")
    assert all(len(voice["samples"]) == 2 for voice in choices if voice["id"] in ("baseline", "adrian", "ethan", "narrator"))
    assert not (tmp_path / "prefs.json").exists()


def test_spanish_alternatives_have_licensed_metadata_and_existing_previews(tmp_path):
    library = VoiceLibrary(CATALOG, tmp_path / "prefs.json")
    spanish = [voice for voice in library.list() if "es" in voice["languages"]]
    assert {voice["id"] for voice in spanish} == {"gabriel_es", "brian_es"}
    for voice in spanish:
        assert voice["selectable"] and voice["api_licensed"] and voice["rights_status"] == "fish_licensed_api"
        assert voice["samples"][0]["kind"] == "existing_provider_preview"
        assert "?" not in voice["preview_source"]  # Never persist signed preview access URLs.


def test_favorites_assignments_survive_new_instance_without_changing_other_channels(tmp_path):
    path = tmp_path / "state/prefs.json"
    library = VoiceLibrary(CATALOG, path)
    library.favorite("ethan")  # A historical preview can be favorited for listening.
    library.favorite("ethan")
    library.favorite("dave")
    library.assign("science", "dave")
    restored = VoiceLibrary(CATALOG, path)
    assert restored.assigned("science")["id"] == "dave"
    assert restored.assigned("loose_thread")["id"] == "baseline"
    assert [voice["id"] for voice in restored.list() if voice["favorite"]] == ["ethan", "dave"]
    restored.favorite("ethan", False)
    assert [voice["id"] for voice in restored.list() if voice["favorite"]] == ["dave"]
    previous = path.read_bytes()
    with pytest.raises(VoiceLibraryError, match="licensed metadata"):
        restored.assign("science", "ethan")
    with pytest.raises(VoiceLibraryError):
        restored.assign("../outside", "dave")
    assert path.read_bytes() == previous


def test_corrupt_state_preserved_and_concurrent_operation_rejected(tmp_path):
    path = tmp_path / "prefs.json"
    library = VoiceLibrary(CATALOG, path)
    with library._lock():
        with pytest.raises(VoiceLibraryError, match="in progress"):
            library.favorite("dave")
    path.write_text('{"version":1,"favorites":[],"assignments":{"science":"ethan"}}')
    original = path.read_text()
    with pytest.raises(VoiceLibraryError, match="preserve"):
        library.favorite("baseline")
    assert path.read_text() == original


def test_preview_routes_verify_hash_and_controlled_directories(tmp_path):
    catalog = json.loads(CATALOG.read_text())
    path = tmp_path / "outputs/voice-tests/baseline_plain.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"test preview bytes")
    catalog["voices"][0]["samples"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    catalog_path = tmp_path / "voices.json"
    catalog_path.write_text(json.dumps(catalog))
    library = VoiceLibrary(catalog_path, tmp_path / "prefs.json")
    assert library.sample("baseline", 0, root=tmp_path) == path
    path.write_bytes(b"changed")
    with pytest.raises(VoiceLibraryError):
        library.sample("baseline", 0, root=tmp_path)
    for index in [-1, 99]:
        with pytest.raises(VoiceLibraryError):
            library.sample("baseline", index, root=tmp_path)
    outside = tmp_path / "private.mp3"
    outside.write_bytes(b"test preview bytes")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(VoiceLibraryError):
        library.sample("baseline", 0, root=tmp_path)


def test_unlicensed_new_voice_cannot_be_marked_selectable(tmp_path):
    catalog = copy.deepcopy(json.loads(CATALOG.read_text()))
    catalog["voices"][1]["selectable"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(catalog))
    with pytest.raises(VoiceLibraryError, match="catalog"):
        VoiceLibrary(path, tmp_path / "prefs.json")


def test_discovery_is_one_authenticated_metadata_get_and_filters_unlicensed():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.method == "GET" and request.url.path == "/model"
        assert request.url.params["licensed"] == "true"
        assert request.url.params["page_size"] == "3"
        assert request.headers["authorization"] == "Bearer private-test"
        return httpx.Response(200, json={"items": [{"_id": "a" * 32, "title": "Licensed", "licensed": True},
                                                   {"_id": "b" * 32, "title": "Unverified", "licensed": False}]})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = discover_fish_voices("private-test", limit=3, client=client)
    assert len(calls) == 1 and [voice["display_name"] for voice in result] == ["Licensed"]
    assert "private-test" not in json.dumps(result)


def test_metadata_redirect_never_forwards_key_or_retries():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://elsewhere.invalid/"})
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    with pytest.raises(VoiceLibraryError, match="HTTP 302"):
        discover_fish_voices("private-test", client=client)
    assert len(calls) == 1
