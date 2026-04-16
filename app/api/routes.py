from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.models.classify import ErrorResponse, SuccessResponse
from app.services.classify import ClassifyService
from app.services.profiles import ProfileNotFoundError, ProfilesService

router = APIRouter(prefix="/api", tags=["classification"])


def _build_error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(message=message).model_dump(),
    )


@router.get(
    "/classify",
    response_model=SuccessResponse | ErrorResponse,
    summary="Classify a first name using Genderize",
    response_description="Successful classification payload.",
    responses={
        400: {"model": ErrorResponse, "description": "Missing or empty name"},
        422: {"model": ErrorResponse, "description": "Invalid name value"},
        502: {"model": ErrorResponse, "description": "Upstream service failure"},
        500: {"model": ErrorResponse, "description": "Unexpected server error"},
    },
)
async def classify(request: Request):
    values = request.query_params.getlist("name")
    service = ClassifyService(request.app.state.http_client)
    status_code, payload = await service.classify(values)

    if isinstance(payload, ErrorResponse):
        return _build_error_response(status_code, payload.message)

    return payload


@router.post(
    "/profiles",
    summary="Create profile for a name",
    responses={
        200: {"description": "Profile already exists"},
        201: {"description": "Profile created"},
        400: {"model": ErrorResponse, "description": "Missing or empty name"},
        422: {"model": ErrorResponse, "description": "Invalid type"},
        502: {"model": ErrorResponse, "description": "Upstream service failure"},
        500: {"model": ErrorResponse, "description": "Unexpected server error"},
    },
)
async def create_profile(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    if not isinstance(body, dict):
        return _build_error_response(422, "Invalid type")

    service = ProfilesService(request.app.state.http_client)
    status_code, payload = await service.create_profile(body.get("name"))
    if isinstance(payload, ErrorResponse):
        return _build_error_response(status_code, payload.message)

    return JSONResponse(status_code=status_code, content=payload.model_dump())


@router.get(
    "/profiles/{profile_id}",
    summary="Get profile by ID",
    responses={
        200: {"description": "Profile found"},
        404: {"model": ErrorResponse, "description": "Profile not found"},
        500: {"model": ErrorResponse, "description": "Unexpected server error"},
    },
)
async def get_profile(profile_id: str, request: Request):
    service = ProfilesService(request.app.state.http_client)
    try:
        payload = service.get_profile(profile_id)
    except ProfileNotFoundError:
        return _build_error_response(404, "Profile not found")

    return payload


@router.get(
    "/profiles",
    summary="Get all profiles",
    responses={
        200: {"description": "Profiles fetched"},
        500: {"model": ErrorResponse, "description": "Unexpected server error"},
    },
)
async def get_profiles(
    request: Request,
    gender: str | None = None,
    country_id: str | None = None,
    age_group: str | None = None,
):
    service = ProfilesService(request.app.state.http_client)
    return service.list_profiles(
        gender=gender,
        country_id=country_id,
        age_group=age_group,
    )


@router.delete(
    "/profiles/{profile_id}",
    status_code=204,
    summary="Delete profile by ID",
    responses={
        204: {"description": "Profile deleted"},
        404: {"model": ErrorResponse, "description": "Profile not found"},
        500: {"model": ErrorResponse, "description": "Unexpected server error"},
    },
)
async def delete_profile(profile_id: str, request: Request):
    service = ProfilesService(request.app.state.http_client)
    deleted = service.delete_profile(profile_id)
    if not deleted:
        return _build_error_response(404, "Profile not found")
    return Response(status_code=204)
