"""DEM endpoints: list, upload (multi-file), inspect, preview, delete."""

from typing import Annotated

from fastapi import File, Form, Query, Response, APIRouter, UploadFile, status
from fastapi.responses import FileResponse

from titan3d.api.deps import DemsDep
from titan3d.api.schemas.dem import DemOut


router = APIRouter(prefix="/dems", tags=["dems"])


@router.get("", summary="List DEMs")
def list_dems(dems: DemsDep) -> list[DemOut]:
    """All registered DEMs, the built-in one first."""
    return dems.list_all()


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload GeoTIFF tiles (stitched in the background)",
)
async def upload_dem(
    dems: DemsDep,
    files: Annotated[list[UploadFile], File(description="One or more GeoTIFF tiles")],
    name: Annotated[str, Form(max_length=80)] = "",
) -> DemOut:
    """Store the tiles and start stitching; poll ``GET /dems/{id}`` until ready."""
    return await dems.upload(name, files)


@router.get("/{dem_id}", summary="DEM metadata and stitching status")
def get_dem(dem_id: str, dems: DemsDep) -> DemOut:
    """One DEM."""
    return dems.get(dem_id)


@router.get(
    "/{dem_id}/preview",
    summary="Terrain preview bundle (gzipped JSON)",
    response_class=FileResponse,
    responses={200: {"content": {"application/json": {}}}},
)
def preview_dem(
    dem_id: str,
    dems: DemsDep,
    max_cells: Annotated[int, Query(ge=64, le=1024)] = 512,
) -> FileResponse:
    """Quantised terrain of the whole DEM in its local UTM zone, for placing sources."""
    path = dems.preview_path(dem_id, max_cells)
    return FileResponse(
        path, media_type="application/json", headers={"Content-Encoding": "gzip"}
    )


@router.delete(
    "/{dem_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete DEM"
)
def delete_dem(dem_id: str, dems: DemsDep) -> Response:
    """Delete an uploaded DEM that no simulation uses."""
    dems.delete(dem_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
