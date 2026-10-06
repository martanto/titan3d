"""granflow — a Python re-implementation of Titan2D's depth-averaged granular flow model."""
from .solver import FlowParams, Solver, State, earth_pressure_coeff
from .terrain import synthetic_volcano, paraboloid_pile, load_dem

__all__ = ["FlowParams", "Solver", "State", "earth_pressure_coeff",
           "synthetic_volcano", "paraboloid_pile", "load_dem"]
__version__ = "0.1.0"
