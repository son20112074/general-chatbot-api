from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.domain.services.user_service import UserService
from app.domain.services.role_service import RoleService
from app.domain.models.user import User
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData, ChangePasswordRequest
from app.presentation.api.v1.schemas.user import UserCreate, UserUpdate, UserResponse, GetUsersQuery

router = APIRouter(prefix="", tags=["Users"])

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    user_service = UserService(db)
    try:
        user = await user_service.create_user(user_data, current_user.user_id)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    user_service = UserService(db)
    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user

@router.post("/children", response_model=Dict)
async def query_users(
    query_params: GetUsersQuery,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Query users with various filters and conditions.
    Supports role-based access control, search, and pagination.
    """
    try:
        user_service = UserService(db)
        result = await user_service.query_users(query_params, current_user.role_id)
        return {
            "data": [user.to_dict() for user in result["data"]],
            "total": result["total"]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error querying users: {str(e)}"
        )

@router.get("/", response_model=List[UserResponse])
async def get_users(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    user_service = UserService(db)
    users = await user_service.get_users(skip, limit)
    return users

@router.get("/with-children/", response_model=List[UserResponse])
async def get_users_with_children(
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Lấy danh sách người dùng gồm user hiện tại và các người dùng cấp con (role con), không lấy các user cùng role với user hiện tại"""
    try:
        user_service = UserService(db)
        role_service = RoleService(db)
        # Lấy role_id của user hiện tại
        current_user_obj = await user_service.get_user(current_user.user_id)
        if not current_user_obj:
            raise HTTPException(status_code=404, detail="Current user not found")
        # Lấy danh sách role_id: chỉ các role con
        child_role_ids = await role_service.get_child_roles(current_user_obj.role_id)
        # Lấy user hiện tại
        result = await db.execute(select(User).where(
            (User.id == current_user.user_id) | (User.role_id.in_(child_role_ids))
        ))
        users = result.scalars().all()
        return [UserResponse.model_validate(u) for u in users]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    user_service = UserService(db)
    try:
        user = await user_service.update_user(user_id, user_data)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    user_service = UserService(db)
    try:
        success = await user_service.delete_user(user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/change-password")
async def change_password(
    password_data: ChangePasswordRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Change the current user's password
    
    Parameters:
    - password_data: Contains current_password and new_password
    
    Returns:
    - Success message if password was changed successfully
    """
    user_service = UserService(db)
    try:
        success = await user_service.change_password(
            user_id=current_user.user_id,
            current_password=password_data.current_password,
            new_password=password_data.new_password
        )
        
        if success:
            return {
                "message": "Password changed successfully",
                "success": True
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to change password"
            )
            
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error changing password: {str(e)}"
        ) 

@router.get("/peers-and-children/", response_model=Dict)
async def get_peers_and_children(
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Lấy danh sách user đồng cấp (cùng role_id, trừ user hiện tại) và user cấp con (role con) của user hiện tại.
    Trả về dạng: { 'peers': [...], 'children': [...] }
    """
    user_service = UserService(db)
    role_service = RoleService(db)
    # Lấy user hiện tại
    current_user_obj = await user_service.get_user(current_user.user_id)
    if not current_user_obj:
        raise HTTPException(status_code=404, detail="Current user not found")
    # Lấy các user đồng cấp (cùng role_id, trừ user hiện tại)
    peer_users_result = await db.execute(
        select(User).where(
            (User.role_id == current_user_obj.role_id) & (User.id != current_user.user_id)
        )
    )
    peer_users = peer_users_result.scalars().all()
    # Lấy các role con
    child_role_ids = await role_service.get_child_roles(current_user_obj.role_id)
    # Lấy các user thuộc role con
    if child_role_ids:
        child_users_result = await db.execute(
            select(User).where(User.role_id.in_(child_role_ids))
        )
        child_users = child_users_result.scalars().all()
    else:
        child_users = []
    return {
        "peers": [UserResponse.model_validate(u) for u in peer_users],
        "children": [UserResponse.model_validate(u) for u in child_users]
    } 