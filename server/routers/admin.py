import logging
import mimetypes
import os
import secrets
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from server.schemas import (
    AdminCameraListResponse,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminLogoutResponse,
    AdminSessionValidateResponse,
    CameraHotConfig,
    GalleryResponse,
)
from server.state import server_state

logger = logging.getLogger("parqueame.server.admin")
router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

security = HTTPBearer(auto_error=False)


def get_current_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing administrative authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    session = server_state.validate_admin_session(token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired administrative token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return session


@router.post(
    "/login",
    response_model=AdminLoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate administrator credentials and receive bearer token",
)
def admin_login(payload: AdminLoginRequest) -> AdminLoginResponse:
    expected_user = os.getenv("PARQUEAME_ADMIN_USER", "admin")
    expected_pass = os.getenv("PARQUEAME_ADMIN_PASSWORD", "parqueame_secret_2026")

    if payload.username != expected_user or payload.password != expected_pass:
        logger.warning(f"Failed admin login attempt for user: '{payload.username}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrative credentials.",
        )

    token = secrets.token_hex(16)
    expires_at = server_state.create_admin_session(user=payload.username, token=token)
    logger.info(f"Administrator '{payload.username}' authenticated successfully.")
    return AdminLoginResponse(
        status="authenticated",
        token=token,
        expires_at=expires_at,
        user=payload.username,
    )


@router.get(
    "/me",
    response_model=AdminSessionValidateResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate active administrative session token",
)
def admin_validate_session(
    session: dict = Depends(get_current_admin),
) -> AdminSessionValidateResponse:
    return AdminSessionValidateResponse(
        user=session["user"],
        valid=True,
        expires_at=session["expires_at"],
    )


@router.post(
    "/logout",
    response_model=AdminLogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Invalidate active administrative session token",
)
def admin_logout(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> AdminLogoutResponse:
    if credentials and credentials.credentials:
        server_state.remove_admin_session(credentials.credentials)
    return AdminLogoutResponse(status="logged_out")


@router.get(
    "/gallery",
    response_model=GalleryResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve catalog of captured hardware photographs and annotations",
)
def admin_gallery(
    camera_id: Optional[str] = None,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: dict = Depends(get_current_admin),
) -> GalleryResponse:
    return server_state.get_gallery_catalog(camera_id=camera_id, limit=limit, offset=offset)


@router.get(
    "/gallery/image/{filename}",
    status_code=status.HTTP_200_OK,
    summary="Serve full-resolution diagnostic image from gallery archive",
)
def get_gallery_image(
    filename: str,
    _: dict = Depends(get_current_admin),
) -> Response:
    safe_name = Path(filename).name
    search_dirs = [
        Path("storage/cameras"),
        Path("storage/images"),
        Path("cam_software/fotos"),
    ]
    for d in search_dirs:
        candidate = d / safe_name
        if candidate.exists() and candidate.is_file():
            mime_type, _ = mimetypes.guess_type(str(candidate))
            return Response(
                content=candidate.read_bytes(),
                media_type=mime_type or "image/jpeg",
                headers={
                    "Cache-Control": "public, max-age=3600",
                },
            )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found in gallery.")


@router.get(
    "/cameras",
    response_model=AdminCameraListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all registered cameras with aggregated fleet telemetry",
)
def admin_list_cameras(
    _: dict = Depends(get_current_admin),
) -> AdminCameraListResponse:
    cameras = server_state.get_admin_cameras()
    return AdminCameraListResponse(cameras=cameras)


@router.put(
    "/cameras/{camera_id}/config",
    response_model=CameraHotConfig,
    status_code=status.HTTP_200_OK,
    summary="Authenticated update of dynamic camera hot-configuration",
)
def admin_update_camera_config(
    camera_id: str,
    payload: CameraHotConfig,
    _: dict = Depends(get_current_admin),
) -> CameraHotConfig:
    if camera_id not in server_state.camera_configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found in registered configurations.",
        )
    server_state.set_camera_hot_config(camera_id, payload)
    logger.info(
        f"Admin updated hot-config for camera '{camera_id}': "
        f"interval={payload.interval_seconds}s, active={payload.active}, quality={payload.quality}"
    )
    return payload
