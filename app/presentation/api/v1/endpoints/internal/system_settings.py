from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domain.services.system_setting_service import SystemSettingService
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.presentation.api.v1.schemas.system_setting import (
    SystemSettingUpsertRequest,
    SystemSettingResponse,
)

router = APIRouter(prefix="", tags=["System Settings"])


@router.get("/{key}", response_model=SystemSettingResponse)
async def get_system_setting_by_key(
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = SystemSettingService(db)
    entity = await service.get_by_key(key)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="System setting not found",
        )
    return entity


@router.put("/upsert", response_model=SystemSettingResponse)
async def upsert_system_setting_by_key(
    payload: SystemSettingUpsertRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = SystemSettingService(db)
    return await service.upsert_by_key(
        key=payload.key,
        value=payload.value,
        created_by=current_user.user_id,
    )
