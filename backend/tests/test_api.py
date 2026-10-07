"""End-to-end API tests: DEM upload → simulation in a worker process → downloads."""

import io
import time
import shutil
import base64
from typing import Any
from pathlib import Path
from collections.abc import Iterator, Callable

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient

from titan3d.config import Settings
from titan3d.api.main import create_app
from tests.test_dem import write_tile


TESTS = Path(__file__).resolve().parent


def wait_for(fn: Callable[[], Any], timeout: float = 180.0, every: float = 0.3) -> Any:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = fn()
        if value:
            return value
        time.sleep(every)
    raise TimeoutError("condition not met")


def make_settings(tag: str, **kw: Any) -> Settings:
    data = TESTS / f"out_api_{tag}"
    tiles = TESTS / f"out_api_{tag}_builtin"
    shutil.rmtree(data, ignore_errors=True)
    shutil.rmtree(tiles, ignore_errors=True)
    tiles.mkdir(parents=True)
    write_tile(tiles / "a.tif", 112.82, -8.01, 100, None)
    write_tile(tiles / "b.tif", 112.92, -8.01, 100, None)
    return Settings(
        data_dir=data,
        builtin_dem_dir=tiles,
        builtin_dem_id="semeru",
        frontend_dist=TESTS / "out_no_frontend",
        log_level="WARNING",
        **kw,
    )


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app(make_settings("main"))) as c:
        yield c


def tile_bytes(west: float) -> bytes:
    p = TESTS / f"out_upload_{west}.tif"
    write_tile(p, west, -8.01, 100, None)
    return p.read_bytes()


def scenario(dem_id: str, **kw: Any) -> dict[str, Any]:
    s: dict[str, Any] = {
        "name": "API test",
        "dem_id": dem_id,
        "piles": [{"lon": 112.92, "lat": -8.07, "height": 30.0, "radius": 400.0}],
        "domain": {"west_km": 3.0, "east_km": 3.0, "south_km": 3.0, "north_km": 3.0},
        "material": {"phi_bed_deg": 18.0},
        "numerics": {"dx": 100.0, "backend": "numpy"},
        "t_end": 20.0,
        "output_every": 5.0,
    }
    s.update(kw)
    return s


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_builtin_dem_is_registered_and_stitched(client: TestClient) -> None:
    dem = wait_for(
        lambda: (d := client.get("/api/dems/semeru").json())["status"] == "ready" and d
    )
    assert dem["source"] == "builtin"
    assert dem["info"]["crs"] == "EPSG:4326" and dem["info"]["crs_assumed"]
    assert dem["info"]["shape"] == [100, 200]


def test_upload_rejects_non_tiff_extension(client: TestClient) -> None:
    r = client.post(
        "/api/dems", files=[("files", ("notes.txt", b"hello", "text/plain"))]
    )
    assert r.status_code == 400


def test_upload_invalid_tiff_fails_stitching(client: TestClient) -> None:
    r = client.post(
        "/api/dems", files=[("files", ("broken.tif", b"nope", "image/tiff"))]
    )
    assert r.status_code == 202
    dem_id = r.json()["id"]
    dem = wait_for(
        lambda: (
            (d := client.get(f"/api/dems/{dem_id}").json())["status"] != "processing"
            and d
        )
    )
    assert dem["status"] == "failed" and "not a readable GeoTIFF" in dem["error"]


@pytest.fixture(scope="module")
def uploaded(client: TestClient) -> str:
    files = [
        ("files", ("west.tif", tile_bytes(112.82), "image/tiff")),
        ("files", ("east.tif", tile_bytes(112.92), "image/tiff")),
    ]
    r = client.post("/api/dems", files=files, data={"name": "Two tiles"})
    assert r.status_code == 202, r.text
    dem_id = r.json()["id"]
    wait_for(lambda: client.get(f"/api/dems/{dem_id}").json()["status"] == "ready")
    return dem_id


def test_multi_file_upload_and_preview(client: TestClient, uploaded: str) -> None:
    dem = client.get(f"/api/dems/{uploaded}").json()
    assert dem["name"] == "Two tiles" and dem["files"] == ["west.tif", "east.tif"]
    assert dem["info"]["tiles"] == 2
    prev = client.get(f"/api/dems/{uploaded}/preview", params={"max_cells": 64}).json()
    assert prev["meta"]["crs"] == "EPSG:32749"
    assert max(prev["meta"]["nx"], prev["meta"]["ny"]) <= 64
    assert prev["meta"]["summit"]["z"] > 3000
    assert base64.b64decode(prev["terrain"]) and prev["valid"]


def test_yaml_export_import_and_estimate(client: TestClient, uploaded: str) -> None:
    s = scenario(uploaded)
    r = client.post("/api/scenarios/export", json=s)
    assert r.status_code == 200 and r.headers["content-type"].startswith(
        "application/x-yaml"
    )
    r2 = client.post(
        "/api/scenarios/import",
        files={"file": ("s.yaml", r.content, "application/x-yaml")},
    )
    out = r2.json()
    assert out["ok"] and out["scenario"]["piles"][0]["radius"] == 400.0
    bad = client.post(
        "/api/scenarios/import", files={"file": ("s.yaml", b"numerics: {dx: 1}", "x")}
    )
    assert not bad.json()["ok"]
    est = client.post("/api/scenarios/estimate", json=s).json()
    assert est["grid_shape"] == [60, 60] and est["runtime_class"] == "seconds"
    assert client.get("/api/scenarios/presets").json()["standard"] == 20.0


def test_domain_outside_coverage_is_rejected(client: TestClient, uploaded: str) -> None:
    s = scenario(
        uploaded, domain={"west_km": 3, "east_km": 3, "south_km": 8, "north_km": 3}
    )
    r = client.post("/api/simulations", json=s)
    assert r.status_code == 422 and "no elevation data" in r.json()["detail"]


def test_amr_yaml_worker_outputs_and_georeferencing(
    client: TestClient, uploaded: str
) -> None:
    request = scenario(uploaded, numerics={"dx": 100, "backend": "numpy", "amr": True})
    exported = client.post("/api/scenarios/export", json=request)
    imported = client.post(
        "/api/scenarios/import",
        files={"file": ("amr.yaml", exported.content, "application/x-yaml")},
    ).json()
    assert imported["ok"] and imported["scenario"]["numerics"]["amr"]
    response = client.post("/api/simulations", json=imported["scenario"])
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    job = wait_for(
        lambda: (
            (j := client.get(f"/api/simulations/{job_id}").json())["status"]
            in ("completed", "failed")
            and j
        )
    )
    assert job["status"] == "completed", job.get("error")
    mesh = job["provenance"]["mesh"]
    assert (
        mesh["type"] == "adaptive"
        and mesh["finest_dx_m"] == 100
        and mesh["coarsest_dx_m"] == 200
    )
    bundle = client.get(f"/api/simulations/{job_id}/result").json()
    assert bundle["meta"]["provenance"]["mesh"] == mesh
    output = client.get(f"/api/simulations/{job_id}/files/max_depth.tif")
    with rasterio.open(io.BytesIO(output.content)) as src:
        assert src.crs.to_string() == job["grid"]["crs"]
        assert src.res == (100, 100)
        assert src.width == job["grid"]["nx"] and src.height == job["grid"]["ny"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("amr_buffer", 0),
        ("amr_regrid_every", 0),
        ("amr_gradient", 0),
        ("amr_coarsen_delay", 17),
    ],
)
def test_api_rejects_invalid_amr_controls(
    client: TestClient, field: str, value: object
) -> None:
    request = scenario("semeru", numerics={"amr": True, field: value})
    assert client.post("/api/scenarios/estimate", json=request).status_code == 422


def test_unknown_dem(client: TestClient) -> None:
    assert client.post("/api/simulations", json=scenario("nope")).status_code == 404


@pytest.fixture(scope="module")
def completed(client: TestClient, uploaded: str) -> str:
    r = client.post("/api/simulations", json=scenario(uploaded))
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    job = wait_for(
        lambda: (
            (j := client.get(f"/api/simulations/{job_id}").json())["status"]
            in ("completed", "failed", "interrupted")
            and j
        )
    )
    assert job["status"] == "completed", job.get("error")
    return job_id


def test_simulation_completes_with_progress_and_provenance(
    client: TestClient, completed: str
) -> None:
    job = client.get(f"/api/simulations/{completed}").json()
    p = job["progress"]
    assert p["fraction"] == 1.0 and p["frames"] == 5 and p["steps"] > 0
    assert job["grid"]["nx"] == 60 and job["grid"]["crs"] == "EPSG:32749"
    prov = job["provenance"]
    assert prov["backend"] == "numpy" and len(prov["dem_sha256"]) == 64
    assert {"max_depth.tif", "inundation.geojson", "scenario.yaml"} <= set(
        job["artifacts"]
    )
    frames = client.get(f"/api/simulations/{completed}/frames").json()
    assert [f["t"] for f in frames] == [0.0, 5.0, 10.0, 15.0, 20.0]
    assert any(j["id"] == completed for j in client.get("/api/simulations").json())


def test_result_bundle_and_downloads(client: TestClient, completed: str) -> None:
    b = client.get(f"/api/simulations/{completed}/result").json()
    assert b["meta"]["nframes"] == 5 and b["meta"]["crs"] == "EPSG:32749"
    assert b["meta"]["sources"][0]["kind"] == "pile"
    small = client.get(
        f"/api/simulations/{completed}/result", params={"max_cells": 128}
    ).json()
    assert small["meta"]["nx"] == 60  # grid already smaller than the limit

    tif = client.get(f"/api/simulations/{completed}/files/max_depth.tif")
    assert tif.status_code == 200
    with rasterio.open(io.BytesIO(tif.content)) as src:
        assert src.crs.to_string() == "EPSG:32749"
        assert float(np.nanmax(src.read(1))) > 1.0
    gj = client.get(f"/api/simulations/{completed}/files/inundation.geojson").json()
    assert gj["features"] and gj["properties"]["area_km2"] > 0
    lon, lat = gj["features"][0]["geometry"]["coordinates"][0][0]
    assert 112.8 < lon < 113.0 and -8.2 < lat < -8.0
    kml = client.get(f"/api/simulations/{completed}/files/inundation.kml").text
    assert "<Polygon>" in kml
    yml = client.get(f"/api/simulations/{completed}/files/scenario.yaml").text
    assert "API test" in yml
    assert (
        client.get(f"/api/simulations/{completed}/files/secret.txt").status_code == 422
    )


def test_duplicate_cancel_and_delete(
    client: TestClient, completed: str, uploaded: str
) -> None:
    r = client.post(f"/api/simulations/{completed}/duplicate")
    assert r.status_code == 202
    dup = r.json()["id"]
    assert client.get(f"/api/simulations/{dup}").json()["parent_job_id"] == completed
    client.post(f"/api/simulations/{dup}/cancel")
    final = wait_for(
        lambda: (
            (j := client.get(f"/api/simulations/{dup}").json())["status"]
            in ("cancelled", "completed")
            and j
        )
    )
    assert final["status"] in ("cancelled", "completed")
    assert client.get(f"/api/simulations/{dup}/result").status_code in (200, 409)
    assert client.delete(f"/api/dems/{uploaded}").status_code == 409
    assert client.delete(f"/api/simulations/{dup}").status_code == 204
    assert client.get(f"/api/simulations/{dup}").status_code == 404


def test_basic_auth() -> None:
    settings = make_settings(
        "auth", basic_auth_user="pvmbg", basic_auth_password="s3cret"
    )
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/dems").status_code == 401
        assert c.get("/api/dems", auth=("pvmbg", "wrong")).status_code == 401
        assert c.get("/api/dems", auth=("pvmbg", "s3cret")).status_code == 200
