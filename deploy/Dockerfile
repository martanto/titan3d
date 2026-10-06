# Optional container image: builds the frontend, then runs the API + UI with uv.
# Build from the repository root:  docker build -f deploy/Dockerfile -t titan3d .
FROM node:22-slim AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
COPY backend/openapi.json /src/backend/openapi.json
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
ARG GIT_COMMIT=unknown
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    TITAN3D_GIT_COMMIT=${GIT_COMMIT} \
    TITAN3D_DATA_DIR=/app/backend/data \
    TITAN3D_BUILTIN_DEM_DIR=/app/dem \
    TITAN3D_FRONTEND_DIST=/app/frontend/dist \
    NUMBA_CACHE_DIR=/app/backend/data/numba-cache
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version backend/README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/src ./src
RUN uv sync --locked --no-dev
COPY --from=web /src/frontend/dist /app/frontend/dist
RUN useradd --create-home titan && mkdir -p data && chown titan data
USER titan
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "titan3d", "serve", "--host", "0.0.0.0", "--port", "8000"]
