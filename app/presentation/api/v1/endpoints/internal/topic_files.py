from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.presentation.api.v1.schemas.topic import TopicFileMatchRequest, TopicFileBulkRequest
from app.domain.services.topic_files_service import TopicFilesService

router = APIRouter(prefix="", tags=["Topic Files"])


@router.get("/", response_model=Dict)
async def list_topic_files(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    topic_id: int = Query(description="Filter by topic_id"),
    search: Optional[str] = Query(default=None, description="Search by name or description"),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = TopicFilesService(db)
    try:
        result = await service.get_topic_files(
            skip=skip,
            limit=limit,
            topic_id=topic_id,
            search=search,
            current_user_id=current_user.user_id,
            current_role_id=current_user.role_id
        )
        return {
            "data": result["data"],
            "total": result["total"]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error querying topic files: {str(e)}"
        )


@router.post("/", response_model=Dict, status_code=status.HTTP_201_CREATED)
async def add_file_to_topic(
    data: TopicFileMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = TopicFilesService(db)
    try:
        return await service.add_file_to_topic(
            topic_id=data.topic_id,
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
            detail=f"Error adding file to topic: {str(e)}",
        )


@router.post(
    "/bulk_add",
    response_model=Dict,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk add files to a topic",
    description=(
        "Atomic upsert of many `(topic_id, file_id)` pairs.\n\n"
        "Flow (strict pre-check + single transaction):\n"
        "1. Validate the topic exists and current user is the owner.\n"
        "2. Validate every `file_id` in `file_ids` exists and is not soft-deleted. "
        "If any are missing → 400 with the missing list and **no rows are written**.\n"
        "3. For pairs already present → set `is_matched=True` and bump `updated_at`. "
        "For new pairs → insert with `is_matched=True`.\n"
        "4. On any error during step 3, the whole transaction is rolled back.\n\n"
        "`file_ids` are de-duplicated server-side. Response: `inserted`, `updated`, `total`."
    ),
    responses={
        400: {"description": "One or more file IDs are invalid"},
        403: {"description": "Forbidden: not the topic owner"},
        404: {"description": "Topic not found"},
    },
)
async def bulk_add_files_to_topic(
    data: TopicFileBulkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = TopicFilesService(db)
    try:
        return await service.bulk_add_files_to_topic(
            topic_id=data.topic_id,
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
    summary="Bulk soft-remove files from a topic",
    description=(
        "Set `is_matched=False` for every active `(topic_id, file_id)` row in `file_ids`.\n\n"
        "Atomic. Pairs that don't exist are silently ignored. The response reports "
        "the number of rows actually flipped.\n\n"
        "Owner-only."
    ),
    responses={
        403: {"description": "Forbidden: not the topic owner"},
        404: {"description": "Topic not found"},
    },
)
async def bulk_remove_files_from_topic(
    data: TopicFileBulkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = TopicFilesService(db)
    try:
        return await service.bulk_remove_files_from_topic(
            topic_id=data.topic_id,
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


@router.delete("/", response_model=Dict)
async def remove_file_from_topic(
    topic_id: int = Query(..., gt=0, description="Topic ID"),
    file_id: int = Query(..., gt=0, description="File ID"),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = TopicFilesService(db)
    try:
        return await service.remove_file_from_topic(
            topic_id=topic_id,
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
            detail=f"Error removing file from topic: {str(e)}",
        )
