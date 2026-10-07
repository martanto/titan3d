"""Parameters, state and source definitions for the granular-flow solver.

Coordinates are metres in the grid's CRS (UTM easting/northing for DEM runs, or
local metres centred on the summit for synthetic terrain). Arrays are indexed
``[j, i] = [y, x]`` with ``y`` increasing with ``j`` (north up).
"""

from enum import StrEnum
from dataclasses import replace, dataclass

import numpy as np
import numpy.typing as npt


G = 9.81
"""Gravitational acceleration [m/s²]."""

FloatArray = npt.NDArray[np.floating]


class Rheology(StrEnum):
    """Basal resistance law."""

    COULOMB = "coulomb"
    VOELLMY = "voellmy"


class EarthPressure(StrEnum):
    """Earth-pressure coefficient model."""

    HYDROSTATIC = "hydrostatic"
    SAVAGE_HUTTER = "savage-hutter"


class Precision(StrEnum):
    """Floating-point precision of the state arrays."""

    FLOAT64 = "float64"
    FLOAT32 = "float32"

    @property
    def dtype(self) -> np.dtype:
        """NumPy dtype for this precision."""
        return np.dtype(self.value)


class Backend(StrEnum):
    """Compute backend for the flux and friction kernels."""

    NUMPY = "numpy"
    NUMBA = "numba"


@dataclass(frozen=True)
class FlowParams:
    """Material and numerical parameters.

    Attributes:
        rheology: Basal resistance law.
        phi_bed_deg: Basal friction angle (Coulomb) [deg].
        phi_int_deg: Internal friction angle, used by Savage–Hutter k [deg].
        mu: Voellmy dry-friction coefficient [-].
        xi: Voellmy turbulence coefficient [m/s²].
        earth_pressure: Earth-pressure coefficient model.
        curvature: Include the bed-curvature (centripetal) normal-stress term.
        cfl: Courant number for the adaptive time step.
        h_dry: Depth below which velocity is treated as zero [m].
        precision: Floating-point precision.
        backend: Kernel backend.
    """

    rheology: Rheology = Rheology.COULOMB
    phi_bed_deg: float = 24.0
    phi_int_deg: float = 34.0
    mu: float = 0.12
    xi: float = 1000.0
    earth_pressure: EarthPressure = EarthPressure.SAVAGE_HUTTER
    curvature: bool = True
    cfl: float = 0.4
    h_dry: float = 1e-3
    precision: Precision = Precision.FLOAT64
    backend: Backend = Backend.NUMBA
    amr: bool = False
    amr_gradient: float = 0.05
    amr_buffer: int = 2
    amr_regrid_every: int = 4
    amr_coarsen_delay: int = 3

    def __post_init__(self) -> None:
        """Reject invalid adaptive-mesh controls for direct core callers."""
        if not 0 < self.amr_gradient <= 1:
            raise ValueError("amr_gradient must be in (0, 1]")
        if (
            self.amr_buffer < 1
            or self.amr_regrid_every < 1
            or self.amr_coarsen_delay < 1
        ):
            raise ValueError(
                "AMR buffer, interval and coarsening delay must be positive"
            )


@dataclass(frozen=True)
class PileSource:
    """Paraboloid initial pile, Titan2D's default: ``h = H (1 - r²/R²)``.

    Attributes:
        x: Centre easting [m].
        y: Centre northing [m].
        height: Peak thickness H [m].
        radius: Radius R [m].
    """

    x: float
    y: float
    height: float
    radius: float

    @property
    def volume(self) -> float:
        """Analytic volume ``π R² H / 2`` [m³]."""
        return float(np.pi * self.radius**2 * self.height / 2.0)


@dataclass(frozen=True)
class FluxSource:
    """Titan2D-style flux (vent) source with a paraboloid footprint.

    Material is added at ``influx · (1 - r²/R²)`` metres of depth per second
    between ``start`` and ``start + duration``.

    Attributes:
        x: Centre easting [m].
        y: Centre northing [m].
        radius: Footprint radius R [m].
        influx: Peak extrusion rate at the centre [m/s].
        start: Start time [s].
        duration: Duration [s].
        speed: Initial speed of the added material [m/s].
        direction_deg: Azimuth of that velocity, clockwise from north [deg].
    """

    x: float
    y: float
    radius: float
    influx: float
    start: float = 0.0
    duration: float = 60.0
    speed: float = 0.0
    direction_deg: float = 0.0

    @property
    def end(self) -> float:
        """End time [s]."""
        return self.start + self.duration

    @property
    def volume(self) -> float:
        """Analytic total volume ``π R² · influx · duration / 2`` [m³]."""
        return float(np.pi * self.radius**2 * self.influx * self.duration / 2.0)


@dataclass
class State:
    """Conserved variables and bookkeeping at one instant.

    Attributes:
        h: Flow depth [m].
        hu: x-momentum per unit area [m²/s].
        hv: y-momentum per unit area [m²/s].
        t: Simulation time [s].
        step: Number of completed time steps.
        vol_out: Cumulative volume that left the domain [m³].
        vol_source: Cumulative volume added by flux sources [m³].
    """

    h: FloatArray
    hu: FloatArray
    hv: FloatArray
    t: float = 0.0
    step: int = 0
    vol_out: float = 0.0
    vol_source: float = 0.0
    box: tuple[int, int, int, int] | None = None

    def copy(self) -> "State":
        """Deep copy of the arrays (the solver updates states in place)."""
        return replace(self, h=self.h.copy(), hu=self.hu.copy(), hv=self.hv.copy())
