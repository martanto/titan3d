"""FastAPI dependencies that hand controllers to route functions."""

from typing import Annotated

from fastapi import Depends, Request

from titan3d.config import Settings
from titan3d.api.controllers.dem_controller import DemController
from titan3d.api.controllers.system_controller import SystemController
from titan3d.api.controllers.scenario_controller import ScenarioController
from titan3d.api.controllers.simulation_controller import SimulationController


def get_settings(request: Request) -> Settings:
    """Settings of the running app."""
    return request.app.state.settings


def get_dems(request: Request) -> DemController:
    """DEM controller."""
    return request.app.state.dems


def get_simulations(request: Request) -> SimulationController:
    """Simulation controller."""
    return request.app.state.simulations


def get_system(request: Request) -> SystemController:
    """System health controller."""
    return request.app.state.system


def get_scenarios(request: Request) -> ScenarioController:
    """Scenario controller."""
    return request.app.state.scenarios


SettingsDep = Annotated[Settings, Depends(get_settings)]
DemsDep = Annotated[DemController, Depends(get_dems)]
SimulationsDep = Annotated[SimulationController, Depends(get_simulations)]
ScenariosDep = Annotated[ScenarioController, Depends(get_scenarios)]
SystemDep = Annotated[SystemController, Depends(get_system)]
