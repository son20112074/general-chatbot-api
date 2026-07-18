from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.domain.services.linked_system_service import LinkedSystemService
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.presentation.api.v1.schemas.linked_system import (
    LinkedSystemCreate,
    LinkedSystemResponse,
    LinkedSystemUpdate,
)

router = APIRouter(prefix="", tags=["Linked Systems"])

ADMIN_ROLE_ID = settings.ADMIN_ROLE_ID


def _require_admin(current_user: TokenData):
    if current_user.role_id != ADMIN_ROLE_ID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin can perform this action",
        )


@router.get("/", response_model=List[LinkedSystemResponse])
async def list_linked_systems(
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """List active linked systems ordered by sort_order."""
    service = LinkedSystemService(db)
    return await service.list_active()


@router.post("/", response_model=LinkedSystemResponse, status_code=status.HTTP_201_CREATED)
async def create_linked_system(
    payload: LinkedSystemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """Create a linked system. Admin only."""
    _require_admin(current_user)
    service = LinkedSystemService(db)
    try:
        return await service.create(payload, current_user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{system_id}", response_model=LinkedSystemResponse)
async def update_linked_system(
    system_id: int,
    payload: LinkedSystemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """Update a linked system. Admin only."""
    _require_admin(current_user)
    service = LinkedSystemService(db)
    try:
        entity = await service.update(system_id, payload)
        if not entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Linked system not found",
            )
        return entity
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{system_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_linked_system(
    system_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """Soft-delete a linked system. Admin only."""
    _require_admin(current_user)
    service = LinkedSystemService(db)
    success = await service.soft_delete(system_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Linked system not found",
        )
