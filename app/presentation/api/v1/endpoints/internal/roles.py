from typing import List, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.config import settings
from app.domain.services.role_service import RoleService
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.presentation.api.v1.schemas.role import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleQuery,
)

router = APIRouter(prefix="", tags=["Roles"])

ADMIN_ROLE_ID = settings.ADMIN_ROLE_ID


def _require_admin(current_user: TokenData):
    if current_user.role_id != ADMIN_ROLE_ID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin can perform this action"
        )


@router.post("/", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    role_data: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Create a new role. Admin only."""
    _require_admin(current_user)
    role_service = RoleService(db)
    try:
        role = await role_service.create_role(role_data, current_user.user_id)
        return role
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/tree", response_model=List[Dict])
async def get_role_tree(
    depth: Optional[int] = Query(default=None, ge=1, description="Max depth (1=root only, null=all)"),
    search: Optional[str] = Query(default=None, description="Search role by name"),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Get all roles as tree. Supports depth limit and name search."""
    try:
        role_service = RoleService(db)
        return await role_service.get_role_tree(depth=depth, search=search)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting role tree: {str(e)}"
        )


@router.post("/query", response_model=Dict)
async def query_roles(
    query_params: RoleQuery,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Query roles with filters. Only returns active (non-deleted) roles."""
    try:
        role_service = RoleService(db)
        result = await role_service.query_roles(query_params)
        return {
            "data": [RoleResponse.model_validate(role) for role in result["data"]],
            "total": result["total"]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error querying roles: {str(e)}"
        )


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Get a role by ID."""
    role_service = RoleService(db)
    role = await role_service.get_role(role_id)
    if not role or role.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return role


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    role_data: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Update a role. Admin only.
    Changing parent_id only allowed if no active users are assigned to the role.
    """
    _require_admin(current_user)
    role_service = RoleService(db)
    try:
        role = await role_service.update_role(role_id, role_data)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        return role
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Soft-delete a role. Admin only.
    Only allowed if no active users are assigned and no active children exist.
    """
    _require_admin(current_user)
    role_service = RoleService(db)
    try:
        role = await role_service.get_role(role_id)
        if not role or role.is_deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        success = await role_service.delete_role(role_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete role"
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{role_id}/children", response_model=List[Dict])
async def get_role_children(
    role_id: int,
    depth: Optional[int] = Query(default=None, ge=1, description="Max depth (null=all)"),
    search: Optional[str] = Query(default=None, description="Search role by name"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get child roles tree. Supports depth limit and name search."""
    try:
        role_service = RoleService(db)
        role = await role_service.get_role(role_id)
        if not role or role.is_deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        return await role_service.get_children_tree(role_id, depth=depth, search=search)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching role children: {str(e)}"
        )
