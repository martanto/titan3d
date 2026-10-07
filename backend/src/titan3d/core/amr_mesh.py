"""One-level rectangular leaf patches and conservative raster transfers."""

from dataclasses import dataclass

import numpy as np

from titan3d.core.grid import Grid
from titan3d.core.params import FloatArray


def waterfill(depth: FloatArray, bed: FloatArray) -> FloatArray:
    """Split parent means over four beds, preserving volume and positivity.

    Solve sum(max(z - b_i, 0)) = 4 h by sorting the four bed heights.
    Unlike clipping a reconstructed depth, this does not create volume.
    """
    ordered = np.sort(bed, axis=1)
    levels = (4 * depth[:, None] + np.cumsum(ordered, axis=1)) / np.arange(1, 5)
    valid = levels[:, :3] <= ordered[:, 1:]
    choice = np.argmax(
        np.column_stack((valid, np.ones(len(depth), dtype=bool))), axis=1
    )
    level = levels[np.arange(len(depth)), choice]
    children = np.maximum(level[:, None] - bed, 0)
    # Roundoff correction on a wet child, never a global mass rescaling.
    residual = 4 * depth - children.sum(axis=1)
    children[np.arange(len(depth)), np.argmax(children, axis=1)] += residual
    return children


@dataclass
class LeafMesh:
    """Ownership raster plus unique faces; no covered parent evolves twice."""

    grid: Grid
    refined: np.ndarray

    def __post_init__(self) -> None:
        """Construct leaf ownership, geometry and shared face segments."""
        g = self.grid
        shape = ((g.ny + 1) // 2, (g.nx + 1) // 2)
        if self.refined.shape != shape:
            raise ValueError(f"Refinement mask must have shape {shape}")
        self.refined = self.refined.copy()
        if g.ny % 2:
            self.refined[-1, :] = True
        if g.nx % 2:
            self.refined[:, -1] = True
        coarse = np.argwhere(~self.refined)
        self.coarse_j, self.coarse_i = coarse.T
        self.ncoarse = len(coarse)
        self.owner = np.empty((g.ny, g.nx), dtype=np.int64)
        for dj in range(2):
            for di in range(2):
                self.owner[2 * self.coarse_j + dj, 2 * self.coarse_i + di] = np.arange(
                    self.ncoarse
                )
        fine = np.repeat(np.repeat(self.refined, 2, axis=0), 2, axis=1)[: g.ny, : g.nx]
        self.owner[fine] = self.ncoarse + np.arange(np.count_nonzero(fine))
        self.count = np.bincount(self.owner.ravel()).astype(np.float64)
        self.n = len(self.count)
        self.width = np.sqrt(self.count) * g.dx
        self.area = self.count * g.dx**2
        self.b = self.restrict(g.b)
        yy, xx = np.indices(g.b.shape)
        self.x = self.restrict(g.x0 + xx * g.dx)
        self.y = self.restrict(g.y0 + yy * g.dx)
        self.child_b = self.children(g.b)
        faces = []
        for axis in (0, 1):
            a = self.owner[:, :-1] if axis == 0 else self.owner[:-1, :]
            b = self.owner[:, 1:] if axis == 0 else self.owner[1:, :]
            active = a != b
            codes, counts = np.unique(
                a[active] * self.n + b[active], return_counts=True
            )
            pairs = np.column_stack((codes // self.n, codes % self.n))
            for left, right, length, lr, rr in (
                (pairs[:, 0], pairs[:, 1], counts * g.dx, True, True),
                (
                    self.owner[:, 0] if axis == 0 else self.owner[0, :],
                    self.owner[:, 0] if axis == 0 else self.owner[0, :],
                    None,
                    False,
                    True,
                ),
                (
                    self.owner[:, -1] if axis == 0 else self.owner[-1, :],
                    self.owner[:, -1] if axis == 0 else self.owner[-1, :],
                    None,
                    True,
                    False,
                ),
            ):
                if length is None:
                    left, counts = np.unique(left, return_counts=True)
                    right, length = left, counts * g.dx
                faces.append(
                    (
                        left,
                        right,
                        length,
                        np.full(len(left), axis),
                        np.full(len(left), lr),
                        np.full(len(left), rr),
                    )
                )
        (
            self.left,
            self.right,
            self.length,
            self.axis,
            self.left_real,
            self.right_real,
        ) = (np.concatenate([f[k] for f in faces]) for k in range(6))

    def children(self, raster: FloatArray) -> FloatArray:
        """Four finest values per coarse leaf, in a fixed order."""
        return np.column_stack(
            [
                raster[2 * self.coarse_j + dj, 2 * self.coarse_i + di]
                for dj in range(2)
                for di in range(2)
            ]
        )

    def restrict(self, raster: FloatArray) -> FloatArray:
        """Area-weighted restriction to leaves (accumulate in float64)."""
        return (
            np.bincount(self.owner.ravel(), weights=raster.ravel(), minlength=self.n)
            / self.count
        )

    def raster(
        self, h: FloatArray, hu: FloatArray, hv: FloatArray
    ) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Conservative equilibrium-aware prolongation to the finest grid."""
        fields = [a[self.owner].copy() for a in (h, hu, hv)]
        wet = h[: self.ncoarse] > 0
        child_h = waterfill(h[: self.ncoarse][wet], self.child_b[wet])
        parent_h = h[: self.ncoarse][wet]
        child_fields = [child_h]
        for q in (hu, hv):
            v = np.divide(
                q[: self.ncoarse][wet],
                parent_h,
                out=np.zeros_like(parent_h),
                where=parent_h > 0,
            )
            child_fields.append(child_h * v[:, None])
        for k, (dj, di) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
            for output, child in zip(fields, child_fields, strict=True):
                output[2 * self.coarse_j[wet] + dj, 2 * self.coarse_i[wet] + di] = (
                    child[:, k]
                )
        return fields[0], fields[1], fields[2]

    def slopes(self, field: FloatArray) -> tuple[FloatArray, FloatArray]:
        """Minmod derivatives from face-length-weighted neighbour differences."""
        from titan3d.core.numerics import minmod

        result = []
        for axis in (0, 1):
            mask = self.axis == axis
            left_id, r, length = self.left[mask], self.right[mask], self.length[mask]
            distance = (self.width[left_id] + self.width[r]) / 2
            difference = (field[r] - field[left_id]) / distance * length
            lo = np.bincount(r, weights=difference, minlength=self.n) / self.width
            hi = np.bincount(left_id, weights=difference, minlength=self.n) / self.width
            result.append(minmod(lo, hi))
        return result[0], result[1]

    def divergence(self, u: FloatArray, v: FloatArray) -> FloatArray:
        """Centred velocity divergence; controls active/passive pressure."""
        result = np.zeros(self.n)
        for axis, field in enumerate((u, v)):
            mask = self.axis == axis
            left_id, r, length = self.left[mask], self.right[mask], self.length[mask]
            distance = (self.width[left_id] + self.width[r]) / 2
            diff = (field[r] - field[left_id]) / distance * length
            result += (
                np.bincount(r, weights=diff, minlength=self.n)
                + np.bincount(left_id, weights=diff, minlength=self.n)
            ) / (2 * self.width)
        return result


def dilate(mask: np.ndarray, cells: int) -> np.ndarray:
    """Square buffer without a SciPy dependency or periodic wraparound."""
    result = mask.copy()
    for _ in range(cells):
        padded = np.pad(result, 1)
        result = np.logical_or.reduce(
            [
                padded[dj : dj + mask.shape[0], di : di + mask.shape[1]]
                for dj in range(3)
                for di in range(3)
            ]
        )
    return result
