"""Regular computational grid (cell centres) with optional georeferencing."""

from dataclasses import dataclass

import numpy as np

from titan3d.core.params import FloatArray


@dataclass
class Grid:
    """Bed elevation on a uniform square grid.

    Row ``j`` increases northward. ``x0, y0`` are the coordinates of the centre
    of cell ``[0, 0]`` (the south-west cell).

    Attributes:
        b: Bed elevation [m], shape ``(ny, nx)``.
        dx: Cell size [m].
        x0: Easting of the south-west cell centre [m].
        y0: Northing of the south-west cell centre [m].
        crs: CRS as an authority string (e.g. ``"EPSG:32749"``), or ``None``.
    """

    b: FloatArray
    dx: float
    x0: float = 0.0
    y0: float = 0.0
    crs: str | None = None

    @property
    def ny(self) -> int:
        """Number of rows."""
        return int(self.b.shape[0])

    @property
    def nx(self) -> int:
        """Number of columns."""
        return int(self.b.shape[1])

    @property
    def x(self) -> FloatArray:
        """Cell-centre eastings [m]."""
        return self.x0 + np.arange(self.nx, dtype=np.float64) * self.dx

    @property
    def y(self) -> FloatArray:
        """Cell-centre northings [m]."""
        return self.y0 + np.arange(self.ny, dtype=np.float64) * self.dx

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """Outer cell-edge bounds ``(west, south, east, north)`` [m]."""
        h = self.dx / 2
        return (
            self.x0 - h,
            self.y0 - h,
            self.x0 + (self.nx - 1) * self.dx + h,
            self.y0 + (self.ny - 1) * self.dx + h,
        )

    def index_of(self, x: float, y: float) -> tuple[int, int]:
        """Nearest cell ``(j, i)`` to a point, clipped to the grid."""
        i = int(np.clip(round((x - self.x0) / self.dx), 0, self.nx - 1))
        j = int(np.clip(round((y - self.y0) / self.dx), 0, self.ny - 1))
        return j, i

    def contains(self, x: float, y: float) -> bool:
        """Whether a point lies inside the grid bounds."""
        w, s, e, n = self.bounds
        return w <= x <= e and s <= y <= n
