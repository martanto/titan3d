"""DEM response models."""

from typing import Literal

from pydantic import Field, BaseModel


class MosaicInfoOut(BaseModel):
    """Stitched mosaic metadata."""

    crs: str
    bounds: tuple[float, float, float, float]
    bounds_lonlat: tuple[float, float, float, float] = Field(
        description="(west, south, east, north) in degrees"
    )
    res: tuple[float, float]
    res_m: float = Field(description="Approximate pixel size [m]")
    shape: tuple[int, int]
    nan_fraction: float
    summit: tuple[float, float, float] = Field(description="(lon, lat, elevation)")
    zmin: float
    sha256: str
    tiles: int
    crs_assumed: bool


class DemOut(BaseModel):
    """A registered DEM."""

    id: str
    name: str
    source: Literal["builtin", "upload"]
    status: Literal["processing", "ready", "failed"]
    files: list[str]
    info: MosaicInfoOut | None = None
    error: str | None = None
    created_at: str
    updated_at: str
    jobs: int = Field(0, description="Number of simulations that used this DEM")
