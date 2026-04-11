from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.errors import AppError
from app.domain.services.folder_service import FolderService
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.presentation.api.v1.schemas.folder import (
    FolderCreate,
    FolderUpdate,
    FolderMove,
    FolderResponse,
    FolderQuery,
)

router = APIRouter(prefix="", tags=["Folders"])


@router.post("/", response_model=FolderResponse, status_code=status.HTTP_201_CREATED,
             summary="Create a new folder",
             description="Create folder. owner_id and role_id taken from auth. parent_path computed from parent_id.")
async def create_folder(
    data: FolderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = FolderService(db)
    try:
        folder = await service.create_folder(data, current_user.user_id, current_user.role_id)
        return folder
    except AppError:
        raise  # handled by global handler
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{folder_id}", response_model=FolderResponse,
            summary="Update folder name/description",
            description="Only the owner or admin (role_id=1) can update.")
async def update_folder(
    folder_id: int,
    data: FolderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = FolderService(db)
    try:
        folder = await service.update_folder(folder_id, data, current_user.user_id, current_user.role_id)
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
        return folder
    except AppError:
        raise  # handled by global handler
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Soft delete a folder",
               description="Soft delete folder + all descendant folders + all files inside. Owner or admin only.")
async def delete_folder(
    folder_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = FolderService(db)
    try:
        success = await service.delete_folder(folder_id, current_user.user_id, current_user.role_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    except AppError:
        raise  # handled by global handler
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{folder_id}/move", response_model=FolderResponse,
            summary="Move a folder to a new parent",
            description="Move folder and update parent_path for all descendants. Also re-computes node_path for all files inside. Owner or admin only.")
async def move_folder(
    folder_id: int,
    data: FolderMove,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = FolderService(db)
    try:
        folder = await service.move_folder(folder_id, data, current_user.user_id, current_user.role_id)
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
        return folder
    except AppError:
        raise  # handled by global handler
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{folder_id}", response_model=FolderResponse,
            summary="Get folder by ID")
async def get_folder(
    folder_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = FolderService(db)
    folder = await service.get_folder(folder_id)
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    return folder


@router.get("/tree/root", response_model=Dict,
            summary="Get tree root (lazy load with depth)",
            description="""Get initial tree for a specific type. Use `depth` to control how many levels to load.

**depth=1** (default): only direct children (lazy load, each child has `has_children` flag).
**depth=2**: children + grandchildren.
**depth=4**: load 4 levels deep.

**Admin (role_id=1)**: sees full org tree from root.
**Other users**: see tree from their own role downward.

**Order**: files → folders → roles (newest first in each group).""")
async def get_tree_root(
    type_filter: str = Query(..., regex="^(organization|private|general)$", description="Required: organization, private, or general"),
    depth: int = Query(1, ge=1, le=10, description="How many levels deep to load (1=children only, max 10)"),
    search_text: Optional[str] = Query(None, description="Search by file/folder name, owner name, or role name (partial match)"),
    owner_name: Optional[str] = Query(None, description="Filter by owner (creator) full_name"),
    role_name: Optional[str] = Query(None, description="Filter by role name"),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = FolderService(db)
    try:
        return await service.get_tree_root(
            current_user.user_id, current_user.role_id, type_filter, depth,
            search_text, owner_name, role_name,
        )
    except AppError:
        raise  # handled by global handler
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/tree/{node_id}", response_model=Dict,
            summary="Expand a tree node (lazy load with depth)",
            description="""Click-expand a role or folder node. Returns children with pagination.

**depth=1** (default): direct children only.
**depth=3**: load 3 levels deep from this node.

**Filters**: search_text (name), owner_name (owner full_name), role_name (role name).
**Order**: files → folders → roles (newest first).""")
async def get_tree_children(
    node_id: int,
    node_type: str = Query(..., regex="^(role|folder|user)$", description="Type of node to expand: role, folder, or user"),
    depth: int = Query(1, ge=1, le=10, description="Levels deep to load from this node"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    type_filter: Optional[str] = Query(None, regex="^(private|organization|general)$", description="Filter by folder type"),
    search_text: Optional[str] = Query(None, description="Search by name or description"),
    owner_name: Optional[str] = Query(None, description="Filter by owner name"),
    role_name: Optional[str] = Query(None, description="Search by role name"),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = FolderService(db)
    try:
        return await service.get_tree_children(
            node_id, node_type, current_user.user_id, current_user.role_id,
            depth, page, page_size, type_filter, search_text,
            owner_name, role_name,
        )
    except AppError:
        raise  # handled by global handler
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/query", response_model=Dict,
             summary="Query folders (flat list)",
             description="Query folders with filters, search, and pagination. Returns flat list, not tree.")
async def query_folders(
    query_params: FolderQuery,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = FolderService(db)
    try:
        result = await service.query_folders(query_params, current_user.user_id, current_user.role_id)
        return {
            "data": [FolderResponse.model_validate(f).model_dump() for f in result["data"]],
            "total": result["total"],
        }
    except AppError:
        raise  # handled by global handler
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
