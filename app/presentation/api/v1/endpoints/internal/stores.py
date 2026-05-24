from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.presentation.api.v1.schemas.store import StoreCreate, StoreUpdate, StoreResponse
from app.domain.services.store_service import StoreService

router = APIRouter(prefix="", tags=["Stores"])


@router.get(
    "/",
    response_model=Dict,
    summary="List stores visible to current user",
    description=(
        "Return paginated stores the current user can see.\n\n"
        "Visibility rules:\n"
        "- **Admin**: every non-deleted store.\n"
        "- **Non-admin**: stores the user owns (`created_by`) **OR** stores actively "
        "shared with the user via `shared_store` (rows with `is_deleted=False`).\n\n"
        "Each item includes:\n"
        "- `owner` — `{id, full_name}` of the creator.\n"
        "- `is_shared` — `true` if the store reaches the user through `shared_store` "
        "(false for own stores).\n"
        "- `file_total` — count of `store_files` with `is_deleted=False`.\n\n"
        "Search matches `name` or `description` (case-insensitive, LIKE-escape applied)."
    ),
    responses={500: {"description": "Unexpected error querying stores"}},
)
async def list_stores(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    search: Optional[str] = Query(default=None, description="Search by name or description"),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = StoreService(db)
    try:
        result = await service.get_stores(
            skip=skip, limit=limit, search=search,
            current_user_id=current_user.user_id,
            current_role_id=current_user.role_id,
        )
        return {"data": result["data"], "total": result["total"]}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error querying stores: {str(e)}",
        )


@router.post(
    "/",
    response_model=StoreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new store",
    description=(
        "Create a store owned by the current user. `created_by` and `created_at` are filled "
        "automatically. `name` must be unique per owner among non-deleted stores."
    ),
    responses={
        400: {"description": "Invalid payload"},
        409: {"description": "Store name already exists for this owner"},
    },
)
async def create_store(
    data: StoreCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = StoreService(db)
    try:
        return await service.create_store(data, current_user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Store with name '{data.name}' already exists",
        )


@router.put(
    "/{store_id}",
    response_model=StoreResponse,
    summary="Update store metadata",
    description=(
        "Update `name` and/or `description` of a store. "
        "Only the owner of the store may call this endpoint. "
        "`updated_at` is refreshed automatically."
    ),
    responses={
        403: {"description": "Forbidden: not the owner"},
        404: {"description": "Store not found or already deleted"},
        409: {"description": "Store name already exists for this owner"},
    },
)
async def update_store(
    store_id: int,
    data: StoreUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = StoreService(db)
    try:
        store = await service.update_store(store_id, data, current_user.user_id)
        if not store:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
        return store
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Store with name '{data.name}' already exists",
        )


@router.delete(
    "/{store_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a store (only if unused)",
    description=(
        "Sets `is_deleted=True` on the store.\n\n"
        "Owner-only. The store can ONLY be deleted when it is NOT in use elsewhere:\n"
        "- No active `store_files` rows (`is_deleted=false`).\n"
        "- No active `shared_store` rows (`is_deleted=false`).\n\n"
        "If the store still has files or active shares, the call returns 409 "
        "Conflict and lists the counts. Remove all files and revoke all shares first."
    ),
    responses={
        403: {"description": "Forbidden: not the owner"},
        404: {"description": "Store not found or already deleted"},
        409: {"description": "Store is still in use by store_files or shared_store"},
    },
)
async def delete_store(
    store_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = StoreService(db)
    try:
        success = await service.delete_store(store_id, current_user.user_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
        return success
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
