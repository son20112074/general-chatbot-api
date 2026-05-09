from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.presentation.api.v1.schemas.store import (
    StoreFileMatchRequest,
    StoreFileBulkRequest,
)
from app.domain.services.store_files_service import StoreFilesService

router = APIRouter(prefix="", tags=["Store Files"])


@router.get(
    "/",
    response_model=Dict,
    summary="List active files in a store",
    description=(
        "List paginated files of a store with `store_files.is_deleted=False`.\n\n"
        "Visibility:\n"
        "- The current user must own the store, OR have an active share row in "
        "`shared_store`. If neither holds, the endpoint returns 404 (existence is "
        "not leaked).\n\n"
        "No filtering by `File.type` is applied — share recipients see every file in "
        "the store.\n\n"
        "Search matches file name, owner full name, file summary, or file content."
    ),
    responses={
        404: {"description": "Store not found or not accessible"},
        500: {"description": "Unexpected error"},
    },
)
async def list_store_files(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    store_id: int = Query(..., gt=0, description="Filter by store_id"),
    search: Optional[str] = Query(default=None, description="Search by name / owner / summary / content"),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = StoreFilesService(db)
    try:
        result = await service.get_store_files(
            skip=skip, limit=limit, store_id=store_id, search=search,
            current_user_id=current_user.user_id,
            current_role_id=current_user.role_id,
        )
        return {"data": result["data"], "total": result["total"]}
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error querying store files: {str(e)}",
        )


@router.post(
    "/",
    response_model=Dict,
    status_code=status.HTTP_201_CREATED,
    summary="Add a single file to a store",
    description=(
        "Insert a `(store_id, file_id)` pair with `is_deleted=False`. "
        "If a row for the pair already exists (active or revoked), it is revived.\n\n"
        "Allowed for the store owner OR any user with an active share row. "
        "Pre-checks: store must exist + current user must own it or be in shared_store; "
        "file must exist and not be soft-deleted."
    ),
    responses={
        404: {"description": "Store or file not found"},
    },
)
async def add_file_to_store(
    data: StoreFileMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = StoreFilesService(db)
    try:
        return await service.add_file_to_store(
            store_id=data.store_id,
            file_id=data.file_id,
            current_user_id=current_user.user_id,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding file to store: {str(e)}",
        )


@router.delete(
    "/",
    response_model=Dict,
    summary="Soft-remove a single file from a store",
    description=(
        "Set `is_deleted=True` on the `(store_id, file_id)` row. "
        "If no row exists for that pair, returns 404.\n\n"
        "Allowed for the store owner OR any user with an active share row."
    ),
    responses={
        404: {"description": "Store missing or pair not found"},
    },
)
async def remove_file_from_store(
    store_id: int = Query(..., gt=0, description="Store ID"),
    file_id: int = Query(..., gt=0, description="File ID"),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = StoreFilesService(db)
    try:
        return await service.remove_file_from_store(
            store_id=store_id,
            file_id=file_id,
            current_user_id=current_user.user_id,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error removing file from store: {str(e)}",
        )


@router.post(
    "/bulk_add",
    response_model=Dict,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk add files to a store",
    description=(
        "Atomic upsert of many `(store_id, file_id)` pairs.\n\n"
        "Flow (strict pre-check + single transaction):\n"
        "1. Validate the store exists and current user can access it (owner OR active share row).\n"
        "2. Validate every `file_id` in `file_ids` exists and is not soft-deleted. "
        "If any are missing → 400 with the missing list and **no rows are written**.\n"
        "3. For pairs already present → set `is_deleted=False` and bump `updated_at`. "
        "For new pairs → insert with `is_deleted=False`.\n"
        "4. On any error during step 3, the whole transaction is rolled back.\n\n"
        "`file_ids` are de-duplicated server-side. Response lists `inserted`, `updated`, "
        "and `total = inserted + updated`."
    ),
    responses={
        400: {"description": "One or more file IDs are invalid"},
        404: {"description": "Store not found"},
    },
)
async def bulk_add_files_to_store(
    data: StoreFileBulkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = StoreFilesService(db)
    try:
        return await service.bulk_add_files_to_store(
            store_id=data.store_id,
            file_ids=data.file_ids,
            current_user_id=current_user.user_id,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error bulk-adding files: {str(e)}",
        )


@router.post(
    "/bulk_remove",
    response_model=Dict,
    summary="Bulk soft-remove files from a store",
    description=(
        "Set `is_deleted=True` for every active `(store_id, file_id)` row in `file_ids`.\n\n"
        "Atomic. Pairs that don't exist are silently ignored. The response reports the "
        "number of rows actually flipped.\n\n"
        "Allowed for the store owner OR any user with an active share row."
    ),
    responses={
        404: {"description": "Store not found"},
    },
)
async def bulk_remove_files_from_store(
    data: StoreFileBulkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = StoreFilesService(db)
    try:
        return await service.bulk_remove_files_from_store(
            store_id=data.store_id,
            file_ids=data.file_ids,
            current_user_id=current_user.user_id,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error bulk-removing files: {str(e)}",
        )
