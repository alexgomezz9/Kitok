from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from kitok import cli
from kitok.cloudinary_host import CloudinaryHost, HostingError
from kitok.cloudinary_usage import CloudinaryUsage
from kitok.service_cache import cloudinary_cache


def test_usage_refresh_is_explicit_and_cached(local_kitok, monkeypatch):
    settings, _, _, _ = local_kitok
    cache = cloudinary_cache(settings)
    fetch = Mock(return_value={"credits": {"usage": 2, "limit": 25}, "storage": {"usage": 100},
                               "bandwidth": {"usage": 200}, "transformations": {"usage": 3}})
    service = CloudinaryUsage(settings, cache=cache, fetch=fetch)
    assert service.cached() == {}
    fetch.assert_not_called()
    report = service.refresh()
    assert service.cached() == report
    fetch.assert_called_once()
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    remote = Mock(side_effect=AssertionError("unexpected remote request"))
    monkeypatch.setattr("cloudinary.api.usage", remote)
    assert cli.main(["--cloudinary-usage"]) == 0
    remote.assert_not_called()


@pytest.mark.parametrize("condition", ["unknown", "stale", "high"])
def test_usage_guard_blocks_new_uploads_safely(local_kitok, condition):
    settings, _, state, path = local_kitok
    usage = CloudinaryUsage(settings, cache=cloudinary_cache(settings))
    if condition != "unknown":
        refreshed = datetime.now(timezone.utc) - timedelta(hours=2 if condition == "stale" else 0)
        usage.cache.put("usage", {"refreshed_at": refreshed.isoformat(),
                                  "data": {"credits": {"usage": 24 if condition == "high" else 2, "limit": 25}}})
    uploader = Mock()
    before = state.path.read_bytes()
    host = CloudinaryHost(settings, state, uploader=uploader, lookup=Mock(), usage=usage)
    with pytest.raises(HostingError):
        host.ensure_video("one", path)
    uploader.assert_not_called()
    assert state.path.read_bytes() == before


def test_existing_asset_reuse_ignores_upload_guard(local_kitok):
    settings, _, state, path = local_kitok
    state.update_publishing("one", "cloudinary", public_id="existing", url="https://example.test/v.mp4")
    usage = Mock()
    uploader = Mock()
    host = CloudinaryHost(settings, state, uploader=uploader, lookup=Mock(), usage=usage)
    assert host.ensure_video("one", path)["public_id"] == "existing"
    usage.require_upload_budget.assert_not_called()
    usage.reserve_upload.assert_not_called()
    uploader.assert_not_called()


def test_storage_reservations_prevent_batch_exceeding_threshold(local_kitok):
    settings, _, _, path = local_kitok
    usage = CloudinaryUsage(settings, cache=cloudinary_cache(settings))
    usage.cache.put("usage", {"refreshed_at": datetime.now(timezone.utc).isoformat(),
                              "data": {"storage": {"usage": 70, "limit": 100}}})
    usage.reserve_upload(path)  # ten bytes -> 80; next ten would reach 90%
    with pytest.raises(HostingError, match="threshold"):
        usage.reserve_upload(path)
