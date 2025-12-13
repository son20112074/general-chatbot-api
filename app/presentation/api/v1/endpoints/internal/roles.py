from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.domain.services.role_service import RoleService
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.domain.models.role import Role
from app.presentation.api.v1.schemas.role import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleQuery,
    DeleteRoleSchema
)

router = APIRouter(prefix="", tags=["Roles"])

@router.post("/", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    role_data: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Create a new role."""
    role_service = RoleService(db)
    try:
        role = await role_service.create_role(role_data, current_user.user_id)
        return role
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/tree", response_model=List[Dict])
async def get_role_tree(
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Get all roles organized in a tree structure."""
    try:
        role_service = RoleService(db)
        return await role_service.get_role_tree()
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
    """
    Query roles with various filters and conditions.
    Supports search and pagination.
    """
    try:
        role_service = RoleService(db)
        result = await role_service.query_roles(query_params)
        return {
            "data": [RoleResponse.from_orm(role) for role in result["data"]],
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
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    return role

@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    role_data: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Update a role."""
    role_service = RoleService(db)
    try:
        role = await role_service.update_role(role_id, role_data)
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found"
            )
        return role
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Delete a role and all its child roles."""
    role_service = RoleService(db)
    try:
        # Get the role first to get its parent_path
        role = await role_service.get_role(role_id)
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found"
            )

        # Execute deletion
        success = await role_service.delete_role(role_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete role"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/{role_id}/children", response_model=List[RoleResponse])
async def get_role_children(
    role_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all child roles for a given role ID.
    This includes roles that have the given role in their parent_path.
    """
    try:
        async with db.begin():
            role_service = RoleService(db)
            child_roles = await role_service.get_child_roles(role_id)
            
            child_roles.append(role_id)
            # Get full role objects for the child role IDs
            roles = []
            for child_id in child_roles:
                role = await role_service.get_role(child_id)
                if role:
                    roles.append(role)
                    
            return [RoleResponse.from_orm(role) for role in roles]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching role children: {str(e)}"
        )
    finally:
        await db.close() 