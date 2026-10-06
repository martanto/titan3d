"""System health endpoint: snapshot shape, caching, regenerable cache clearing."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from titan3d.api.main import create_app
from tests.test_api import make_settings


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app(make_settings("system"))) as c:
        yield c


def test_snapshot_shape(client: TestClient) -> None:
    r = client.get("/api/system")
    assert r.status_code == 200
    s = r.json()
    assert s["condition"] in ("normal", "warning", "critical")
    assert [x["key"] for x in s["resources"]] == ["disk", "memory", "cpu"]
    for res in s["resources"]:
        assert 0.0 <= res["fraction"] <= 1.0
        assert res["thresholds"]["warning"] < res["thresholds"]["critical"]
    keys = {sv["key"] for sv in s["services"]}
    assert {"sqlite", "queue", "numba", "dems"} <= keys
    sqlite = next(sv for sv in s["services"] if sv["key"] == "sqlite")
    assert sqlite["response_ms"] is not None and sqlite["status"] == "normal"
    assert {st["key"] for st in s["storage"]} == {"runs", "dems", "caches", "database", "logs"}
    assert s["cache_seconds"] == 300


def test_reading_is_reused_until_refresh(client: TestClient) -> None:
    a = client.get("/api/system").json()["measured_at"]
    b = client.get("/api/system").json()["measured_at"]
    assert a == b
    assert client.get("/api/system", params={"refresh": True}).status_code == 200


def test_clear_caches_removes_only_regenerable_files(client: TestClient) -> None:
    settings = client.app.state.settings  # type: ignore[attr-defined]
    run = settings.runs_dir / "fake-run"
    dem = settings.dems_dir / "fake-dem"
    run.mkdir(parents=True, exist_ok=True)
    dem.mkdir(parents=True, exist_ok=True)
    (run / "bundle_640.json.gz").write_bytes(b"x" * 1000)
    (run / "max_depth.tif").write_bytes(b"keep")
    (dem / "preview_512.json.gz").write_bytes(b"y" * 500)
    (dem / "mosaic.tif").write_bytes(b"keep")
    out = client.post("/api/system/caches/clear").json()
    assert out["files"] >= 2 and out["bytes"] >= 1500
    assert not (run / "bundle_640.json.gz").exists()
    assert not (dem / "preview_512.json.gz").exists()
    assert (run / "max_depth.tif").exists() and (dem / "mosaic.tif").exists()
