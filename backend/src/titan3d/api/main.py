"""FastAPI application factory.

``create_app()`` wires settings, logging, the SQLite database, the built-in DEM,
the job dispatcher and the routers. When ``frontend/dist`` exists it is served
at ``/``, so ``uv run titan3d serve`` runs the whole app on one port.
"""

import base64
import secrets
from pathlib import Path
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from loguru import logger
from fastapi import FastAPI, Request
from starlette.types import ASGIApp
from fastapi.responses import Response, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from titan3d.config import Settings, get_settings
from titan3d.logging import setup_logging
from titan3d.version import package_version
from titan3d.api.errors import AppError
from titan3d.api.routes import dems, health, system, scenarios, simulations
from titan3d.db.database import init_db
from titan3d.api.workers.dispatcher import Dispatcher
from titan3d.api.controllers.dem_controller import DemController
from titan3d.api.controllers.system_controller import SystemController
from titan3d.api.controllers.scenario_controller import ScenarioController
from titan3d.api.controllers.simulation_controller import SimulationController


API_PREFIX = "/api"
OPEN_PATHS = {f"{API_PREFIX}/health"}

DESCRIPTION = """
Titan2D-style depth-averaged granular-flow simulations (block-and-ash flows,
debris avalanches) on uploaded or built-in DEMs.

Typical flow: pick or upload a DEM (`/dems`), submit a scenario
(`POST /simulations`), poll its progress (`GET /simulations/{id}`), then load
the viewer bundle (`/simulations/{id}/result`) and GIS artifacts.
"""


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """HTTP basic auth for every path except the health check."""

    def __init__(self, app: ASGIApp, user: str, password: str):
        super().__init__(app)
        self.user, self.password = user.encode(), password.encode()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Reject requests without valid credentials."""
        if request.url.path in OPEN_PATHS or request.method == "OPTIONS":
            return await call_next(request)
        header = request.headers.get("authorization", "")
        if header.lower().startswith("basic "):
            try:
                user, _, pwd = base64.b64decode(header[6:]).partition(b":")
            except ValueError:
                user, pwd = b"", b""
            if secrets.compare_digest(user, self.user) and secrets.compare_digest(
                pwd, self.password
            ):
                return await call_next(request)
        return Response(
            "Authentication required",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="titan3d"'},
        )


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    if not index.exists():
        logger.info("frontend build not found at {} — serving API only", dist)
        return
    logger.info("serving frontend from {}", dist)
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        target = (root / path).resolve()
        if path and target.is_file() and target.is_relative_to(root):
            # Vite emits content-hashed file names under assets/: cache them forever
            immutable = target.parent.name == "assets"
            cache = "public, max-age=31536000, immutable" if immutable else "no-cache"
            return FileResponse(target, headers={"Cache-Control": cache})
        # index.html must revalidate so a rebuilt frontend is picked up immediately
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application."""
    settings = settings or get_settings()
    settings.ensure_dirs()
    setup_logging(settings.log_level, settings.logs_dir / "titan3d.log")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db(settings.db_path)
        dispatcher = Dispatcher(settings)
        dems_ctl = DemController(settings)
        app.state.settings = settings
        app.state.dems = dems_ctl
        app.state.dispatcher = dispatcher
        app.state.simulations = SimulationController(settings, dems_ctl, dispatcher)
        app.state.scenarios = ScenarioController()
        app.state.system = SystemController(settings, dispatcher)
        dispatcher.recover()
        dems_ctl.register_builtin()
        dispatcher.start()
        logger.info("titan3d {} ready (data: {})", package_version(), settings.data_dir)
        yield
        await dispatcher.stop()
        dems_ctl.shutdown()

    app = FastAPI(
        title="titan3d",
        version=package_version(),
        description=DESCRIPTION,
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
    )

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if settings.basic_auth_enabled:
        app.add_middleware(
            BasicAuthMiddleware,
            user=settings.basic_auth_user or "",
            password=settings.basic_auth_password or "",
        )
        logger.info("HTTP basic auth enabled")

    for r in (
        health.router,
        dems.router,
        simulations.router,
        scenarios.router,
        system.router,
    ):
        app.include_router(r, prefix=API_PREFIX)
    _mount_frontend(app, settings.frontend_dist)
    return app
