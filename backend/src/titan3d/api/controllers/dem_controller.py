"""DEM registration, upload, stitching and previews."""

import re
import uuid
import zlib
import base64
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from loguru import logger
from fastapi import UploadFile

from titan3d.config import Settings
from titan3d.core.dem import (
    DemError,
    MosaicInfo,
    lonlat_to_xy,
    preview_grid,
    stitch_tiles,
    xy_to_lonlat,
)
from titan3d.api.errors import Conflict, NotFound, BadRequest, PayloadTooLarge
from titan3d.core.export import write_json_gz, terrain_preview
from titan3d.api.schemas.dem import DemOut, MosaicInfoOut
from titan3d.db.repositories import DemRecord, DemRepository


TIFF_SUFFIXES = {".tif", ".tiff"}
CHUNK = 1 << 20


def _safe_name(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._") or "tile"
    return stem[:120]


class DemController:
    """Business logic for DEM endpoints."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo = DemRepository(settings.db_path)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dem-stitch")

    def shutdown(self) -> None:
        """Stop the stitching thread pool."""
        self.pool.shutdown(wait=False, cancel_futures=True)

    # --------------------------------------------------------------- queries
    def to_out(self, rec: DemRecord) -> DemOut:
        """Response model for a record."""
        info = MosaicInfoOut.model_validate(rec.info) if rec.info else None
        return DemOut(
            id=rec.id,
            name=rec.name,
            source=rec.source,
            status=rec.status,
            files=[Path(f).name for f in rec.files],
            info=info,
            error=rec.error,
            created_at=rec.created_at,
            updated_at=rec.updated_at,
            jobs=self.repo.job_count(rec.id),
        )

    def list_all(self) -> list[DemOut]:
        """All DEMs."""
        return [self.to_out(r) for r in self.repo.list_all()]

    def record(self, dem_id: str) -> DemRecord:
        """Record or :class:`NotFound`."""
        rec = self.repo.get(dem_id)
        if rec is None:
            raise NotFound(f"DEM '{dem_id}' not found.")
        return rec

    def get(self, dem_id: str) -> DemOut:
        """One DEM."""
        return self.to_out(self.record(dem_id))

    def ready(self, dem_id: str) -> DemRecord:
        """A DEM that can be used for runs (else :class:`Conflict`)."""
        rec = self.record(dem_id)
        if (
            rec.status != "ready"
            or not rec.mosaic_path
            or not Path(rec.mosaic_path).exists()
        ):
            raise Conflict(f"DEM '{dem_id}' is {rec.status}; wait until it is ready.")
        return rec

    def dem_dir(self, dem_id: str) -> Path:
        """Storage directory of a DEM."""
        return self.settings.dems_dir / dem_id

    # ------------------------------------------------------------- stitching
    def _stitch(self, dem_id: str, paths: list[Path]) -> None:
        out = self.dem_dir(dem_id) / "mosaic.tif"
        try:
            logger.info("stitching DEM {} from {} tile(s)", dem_id, len(paths))
            info: MosaicInfo = stitch_tiles(paths, out)
            for old in self.dem_dir(dem_id).glob("preview_*.json.gz"):
                old.unlink()
            self.repo.set_ready(dem_id, str(out), info.to_dict())
            logger.info(
                "DEM {} ready: {} px, summit {}", dem_id, info.shape, info.summit
            )
        except DemError as exc:
            logger.warning("DEM {} rejected: {}", dem_id, exc)
            self.repo.set_failed(dem_id, str(exc))
        except Exception as exc:  # noqa: BLE001 - record every failure
            logger.exception("DEM {} stitching failed", dem_id)
            self.repo.set_failed(dem_id, f"{type(exc).__name__}: {exc}")

    def register_builtin(self) -> None:
        """Register (and stitch once) the built-in DEM directory, if present."""
        s = self.settings
        tiles = sorted(
            p for p in s.builtin_dem_dir.glob("*") if p.suffix.lower() in TIFF_SUFFIXES
        )
        if not tiles:
            logger.info("no built-in DEM tiles in {}", s.builtin_dem_dir)
            return
        rec = self.repo.get(s.builtin_dem_id)
        if rec is None:
            self.repo.create(
                s.builtin_dem_id, s.builtin_dem_name, "builtin", [str(t) for t in tiles]
            )
        elif (
            rec.status == "ready" and rec.mosaic_path and Path(rec.mosaic_path).exists()
        ):
            return
        else:
            self.repo.set_processing(s.builtin_dem_id)
        self.dem_dir(s.builtin_dem_id).mkdir(parents=True, exist_ok=True)
        self.pool.submit(self._stitch, s.builtin_dem_id, tiles)

    async def upload(self, name: str, files: list[UploadFile]) -> DemOut:
        """Store uploaded tiles and start stitching them in the background."""
        s = self.settings
        if not files:
            raise BadRequest("Select at least one GeoTIFF file.")
        if len(files) > s.max_upload_files:
            raise PayloadTooLarge(f"At most {s.max_upload_files} files per upload.")
        for f in files:
            if Path(f.filename or "").suffix.lower() not in TIFF_SUFFIXES:
                raise BadRequest(f"'{f.filename}' is not a .tif/.tiff file.")
        dem_id = f"dem-{uuid.uuid4().hex[:10]}"
        tiles_dir = self.dem_dir(dem_id) / "tiles"
        tiles_dir.mkdir(parents=True, exist_ok=True)
        limit = s.max_upload_file_mb * CHUNK
        paths: list[Path] = []
        try:
            for f in files:
                dest = tiles_dir / _safe_name(f.filename or "tile.tif")
                k = 1
                while dest.exists():
                    dest = tiles_dir / f"{dest.stem}_{k}{dest.suffix}"
                    k += 1
                size = 0
                with open(dest, "wb") as out:
                    while chunk := await f.read(CHUNK):
                        size += len(chunk)
                        if size > limit:
                            raise PayloadTooLarge(
                                f"'{f.filename}' exceeds {s.max_upload_file_mb} MB."
                            )
                        out.write(chunk)
                paths.append(dest)
        except BaseException:
            shutil.rmtree(self.dem_dir(dem_id), ignore_errors=True)
            raise
        clean = name.strip()[:80] or Path(files[0].filename or "Uploaded DEM").stem
        rec = self.repo.create(dem_id, clean, "upload", [str(p) for p in paths])
        self.pool.submit(self._stitch, dem_id, paths)
        return self.to_out(rec)

    # --------------------------------------------------------------- preview
    def preview_path(self, dem_id: str, max_cells: int) -> Path:
        """Gzipped terrain preview bundle, built on first request."""
        rec = self.ready(dem_id)
        out = self.dem_dir(dem_id) / f"preview_{max_cells}.json.gz"
        if out.exists():
            return out
        grid, valid = preview_grid(Path(rec.mosaic_path or ""), max_cells)
        info = rec.info or {}
        crs = grid.crs or ""
        summit = None
        if info.get("summit"):
            lon, lat, z = info["summit"]
            sx, sy = lonlat_to_xy(crs, lon, lat)
            summit = {"lon": lon, "lat": lat, "z": z, "x": sx, "y": sy}
        meta = {
            "dem_id": dem_id,
            "name": rec.name,
            "bounds_lonlat": info.get("bounds_lonlat"),
            "res_m": info.get("res_m"),
            "summit": summit,
        }
        data = terrain_preview(grid, meta, max_cells)
        packed = np.packbits(valid.astype(np.uint8), axis=None)
        data["valid"] = base64.b64encode(zlib.compress(packed.tobytes(), 6)).decode()
        w, s, e, n = grid.bounds
        corners = [xy_to_lonlat(crs, w, s), xy_to_lonlat(crs, e, n)]
        data["meta"]["grid_bounds_lonlat"] = [*corners[0], *corners[1]]
        tmp = out.with_suffix(".tmp")
        write_json_gz(tmp, data)
        tmp.replace(out)
        return out

    # ---------------------------------------------------------------- delete
    def delete(self, dem_id: str) -> None:
        """Delete an uploaded DEM that no simulation uses."""
        rec = self.record(dem_id)
        if rec.source == "builtin":
            raise BadRequest("The built-in DEM cannot be deleted.")
        if rec.status == "processing":
            raise Conflict("The DEM is still being stitched.")
        if self.repo.job_count(dem_id):
            raise Conflict("Simulations use this DEM; delete them first.")
        self.repo.delete(dem_id)
        shutil.rmtree(self.dem_dir(dem_id), ignore_errors=True)
