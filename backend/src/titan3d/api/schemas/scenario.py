"""Scenario request schema: the single source of truth for run configuration.

The same model validates API requests, YAML configs and CLI runs.
"""

from typing import Literal, Annotated

from pydantic import Field, BaseModel, ConfigDict, model_validator

from titan3d.core.params import Backend, Rheology, Precision, EarthPressure


Lon = Annotated[float, Field(ge=-180.0, le=180.0, description="Longitude [deg]")]
Lat = Annotated[float, Field(ge=-90.0, le=90.0, description="Latitude [deg]")]

SEMERU_SUMMIT = (112.9225, -8.1080)
"""Default pile position: Semeru summit area (Mahameru / Jonggring Saloko)."""

RESOLUTION_PRESETS = {"quick": 40.0, "standard": 20.0, "fine": 10.0}
"""Grid-spacing presets offered by the UI [m]."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class PileIn(_Model):
    """Paraboloid pile released at ``t = 0``."""

    lon: Lon = SEMERU_SUMMIT[0]
    lat: Lat = SEMERU_SUMMIT[1]
    height: float = Field(60.0, gt=0, le=1000, description="Peak thickness H [m]")
    radius: float = Field(300.0, gt=0, le=10_000, description="Radius R [m]")


class FluxSourceIn(_Model):
    """Titan2D-style flux (vent) source."""

    lon: Lon = SEMERU_SUMMIT[0]
    lat: Lat = SEMERU_SUMMIT[1]
    radius: float = Field(100.0, gt=0, le=5000, description="Footprint radius [m]")
    influx: float = Field(
        1.0, gt=0, le=50, description="Peak extrusion rate at the centre [m/s]"
    )
    start: float = Field(0.0, ge=0, description="Start time [s]")
    duration: float = Field(60.0, gt=0, description="Duration [s]")
    speed: float = Field(0.0, ge=0, le=200, description="Initial speed [m/s]")
    direction_deg: float = Field(
        0.0, ge=0, lt=360, description="Initial direction, clockwise from north [deg]"
    )


class DomainIn(_Model):
    """Computational domain around an anchor point."""

    center_lon: Lon | None = Field(
        None, description="Anchor longitude; defaults to the first source"
    )
    center_lat: Lat | None = Field(
        None, description="Anchor latitude; defaults to the first source"
    )
    west_km: float = Field(6.0, gt=0, le=100, description="Extent west of anchor [km]")
    east_km: float = Field(16.0, gt=0, le=100, description="Extent east of anchor [km]")
    south_km: float = Field(14.0, gt=0, le=100, description="Extent south [km]")
    north_km: float = Field(6.0, gt=0, le=100, description="Extent north [km]")


class MaterialIn(_Model):
    """Material model."""

    rheology: Rheology = Rheology.COULOMB
    phi_bed_deg: float = Field(
        24.0, gt=0, lt=60, description="Basal friction angle [deg]"
    )
    phi_int_deg: float = Field(
        34.0, gt=0, lt=60, description="Internal friction angle [deg]"
    )
    mu: float = Field(0.12, gt=0, lt=1, description="Voellmy friction coefficient")
    xi: float = Field(
        1000.0, gt=0, le=10_000, description="Voellmy turbulence coefficient [m/s²]"
    )
    earth_pressure: EarthPressure = EarthPressure.SAVAGE_HUTTER
    curvature: bool = Field(True, description="Bed-curvature (centripetal) term")


class NumericsIn(_Model):
    """Grid and solver settings."""

    dx: float = Field(
        20.0, ge=10, le=500, description="Grid spacing [m] (DEMNAS pixel ≈ 8.3 m)"
    )
    cfl: float = Field(0.4, gt=0.05, le=0.9, description="Courant number")
    backend: Backend = Backend.NUMBA
    precision: Precision = Precision.FLOAT64
    h_dry: float = Field(1e-3, gt=0, le=0.1, description="Dry threshold [m]")


class ScenarioRequest(_Model):
    """A complete simulation configuration."""

    schema_version: Literal[1] = 1
    name: str = Field("Semeru summit collapse", min_length=1, max_length=120)
    dem_id: str = Field("semeru", min_length=1, max_length=64)
    piles: list[PileIn] = Field(default_factory=lambda: [PileIn()])
    flux_sources: list[FluxSourceIn] = Field(default_factory=list)
    domain: DomainIn = Field(default_factory=DomainIn)
    material: MaterialIn = Field(default_factory=MaterialIn)
    numerics: NumericsIn = Field(default_factory=NumericsIn)
    t_end: float = Field(300.0, gt=0, le=86_400, description="Simulated time [s]")
    output_every: float = Field(2.0, gt=0, le=3600, description="Output interval [s]")

    @model_validator(mode="after")
    def _check(self) -> "ScenarioRequest":
        if not self.piles and not self.flux_sources:
            raise ValueError("add at least one pile or flux source")
        if len(self.piles) + len(self.flux_sources) > 32:
            raise ValueError("at most 32 sources")
        if self.output_every > self.t_end:
            raise ValueError("output_every must not exceed t_end")
        if self.t_end / self.output_every > 2000:
            raise ValueError("too many output frames (t_end / output_every > 2000)")
        d = self.domain
        if (d.center_lon is None) != (d.center_lat is None):
            raise ValueError(
                "set both domain.center_lon and domain.center_lat, or neither"
            )
        return self

    @property
    def anchor(self) -> tuple[float, float]:
        """Domain anchor ``(lon, lat)``: explicit centre, else the first source."""
        d = self.domain
        if d.center_lon is not None and d.center_lat is not None:
            return d.center_lon, d.center_lat
        src = self.piles[0] if self.piles else self.flux_sources[0]
        return src.lon, src.lat

    def grid_shape(self) -> tuple[int, int]:
        """Estimated ``(ny, nx)`` of the computational grid."""
        d, dx = self.domain, self.numerics.dx
        nx = max(round((d.west_km + d.east_km) * 1000 / dx), 8)
        ny = max(round((d.south_km + d.north_km) * 1000 / dx), 8)
        return ny, nx

    def released_volume_m3(self) -> float:
        """Analytic released volume of all piles and sources [m³]."""
        import math

        v = sum(math.pi * p.radius**2 * p.height / 2 for p in self.piles)
        v += sum(
            math.pi * f.radius**2 * f.influx * f.duration / 2 for f in self.flux_sources
        )
        return v
