from typing import List, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.domain.services.user_service import UserService
from app.domain.services.role_service import RoleService
from app.domain.models.user import User
from app.domain.models.role import Role
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
    """Create user. Admin full access. Others can only create in subordinate roles."""
    user_service = UserService(db)
    try:
        user = await user_service.create_user(
            user_data, current_user.user_id, current_user.role_id
        )
        return user
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/children", response_model=Dict)
async def query_users(
    query_params: GetUsersQuery,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Query users with filters (unchanged logic)."""
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


@router.get(
    "/",
    response_model=Dict,
    summary="List subordinate users (with optional share-context for a store)",
    description=(
        "Return paginated active users that the current caller is allowed to see "
        "(admin sees all; non-admin sees only users in subordinate roles).\n\n"
        "Search matches `full_name` or `account_name`.\n\n"
        "**Optional `store_id` query**: when provided, the caller must be the owner "
        "of that store, OR have an active share row. The endpoint then:\n"
        "- LEFT JOINs `shared_store` on `(user_id, store_id, is_deleted=False)`.\n"
        "- Adds `is_shared: bool` to every returned user.\n"
        "- Orders results so users with `is_shared=true` appear first."
    ),
    responses={
        404: {"description": "Store not found or not accessible"},
    },
)
async def get_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    search: Optional[str] = Query(default=None, description="Search by full_name or account_name"),
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="If set, returned users carry `is_shared` for this store and shared users sort first.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    user_service = UserService(db)
    try:
        result = await user_service.get_users(
            skip=skip, limit=limit, search=search,
            current_role_id=current_user.role_id,
            current_user_id=current_user.user_id,
            store_id=store_id,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    # When store_id is provided, service returns plain dicts already including is_shared.
    if store_id is not None:
        return {"data": result["data"], "total": result["total"]}

    return {
        "data": [UserResponse.model_validate(u) for u in result["data"]],
        "total": result["total"]
    }


@router.get(
    "/all/",
    response_model=Dict,
    summary="List ALL active users (flat, no role hierarchy)",
    description=(
        "Return every user with `status=True`, paginated. Unlike `GET /users/`, "
        "this endpoint does NOT apply role-based RBAC: both admin and non-admin "
        "callers see the full list.\n\n"
        "Search matches `full_name` or `account_name` (case-insensitive).\n\n"
        "**Optional `store_id`:** when provided, the caller must be the owner "
        "of that store OR have an active share row. Each user gets an extra "
        "`is_shared: bool` field, and shared users are sorted first."
    ),
    responses={
        404: {"description": "Store not found or not accessible (only when store_id is set)"},
    },
)
async def get_all_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    search: Optional[str] = Query(default=None, description="Search by full_name or account_name"),
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="If set, returned users carry `is_shared` for this store and shared users sort first.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    user_service = UserService(db)
    try:
        result = await user_service.get_all_users(
            skip=skip, limit=limit, search=search,
            current_user_id=current_user.user_id,
            store_id=store_id,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    if store_id is not None:
        return {"data": result["data"], "total": result["total"]}

    return {
        "data": [UserResponse.model_validate(u) for u in result["data"]],
        "total": result["total"],
    }


@router.get("/with-children/", response_model=List[Dict])
async def get_users_with_children(
    depth: Optional[int] = Query(default=None, ge=1, description="Max role depth (null=all)"),
    search: Optional[str] = Query(default=None, description="Search by full_name or account_name"),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Get user tree by role hierarchy. Supports depth limit and name search."""
    try:
        user_service = UserService(db)
        return await user_service.get_users_with_children(
            current_user_id=current_user.user_id,
            current_role_id=current_user.role_id,
            depth=depth,
            search=search
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Update user. Admin full access. Others can only update subordinate users."""
    user_service = UserService(db)
    try:
        user = await user_service.update_user(user_id, user_data, current_user.role_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Soft-delete user (status=False). Admin full access."""
    user_service = UserService(db)
    try:
        success = await user_service.delete_user(user_id, current_user.role_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/change-password")
async def change_password(
    password_data: ChangePasswordRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Change current user's password. Requires current password verification."""
    user_service = UserService(db)
    try:
        success = await user_service.change_password(
            user_id=current_user.user_id,
            current_password=password_data.current_password,
            new_password=password_data.new_password
        )
        if success:
            return {"message": "Password changed successfully", "success": True}
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/peers-and-children/", response_model=Dict)
async def get_peers_and_children(
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Get peer users + child users. Unchanged logic, added status filter."""
    user_service = UserService(db)
    role_service = RoleService(db)
    current_user_obj = await user_service.get_user(current_user.user_id)
    if not current_user_obj:
        raise HTTPException(status_code=404, detail="Current user not found")
    peer_users_result = await db.execute(
        select(User, Role.parent_path)
        .outerjoin(Role, Role.id == User.role_id)
        .where(
            User.role_id == current_user_obj.role_id,
            User.id != current_user.user_id,
            User.status == True
        )
    )
    peer_users = user_service._attach_role_paths(peer_users_result.all())
    child_role_ids = await role_service.get_child_roles(current_user_obj.role_id)
    if child_role_ids:
        child_users_result = await db.execute(
            select(User, Role.parent_path)
            .outerjoin(Role, Role.id == User.role_id)
            .where(User.role_id.in_(child_role_ids), User.status == True)
        )
        child_users = user_service._attach_role_paths(child_users_result.all())
    else:
        child_users = []
    return {
        "peers": [UserResponse.model_validate(u) for u in peer_users],
        "children": [UserResponse.model_validate(u) for u in child_users]
    }


# NOTE: /{user_id} must be defined AFTER all literal GET routes
# (with-children, peers-and-children) to prevent path parameter capture.
@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """Get a user by ID. Hidden if soft-deleted."""
    user_service = UserService(db)
    user = await user_service.get_user(user_id)
    if not user or not user.status:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
