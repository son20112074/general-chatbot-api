from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
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
