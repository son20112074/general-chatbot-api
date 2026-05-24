from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.presentation.api.v1.schemas.store import (
    SharedStoreSyncRequest,
    SharedStoreSyncResponse,
)
from app.domain.services.shared_store_service import SharedStoreService

router = APIRouter(prefix="", tags=["Shared Store"])


@router.post(
    "/",
    response_model=SharedStoreSyncResponse,
    summary="Sync the user share-list of a store (owner-only upsert-many)",
    description=(
        "Replace the active share list of a store with exactly the provided users.\n\n"
        "**Semantics of `user_ids`:**\n"
        "- `null` (field omitted) — no-op. The endpoint still validates the store exists "
        "and the current user owns it. Returns the current `total_active`.\n"
        "- `[]` (empty list) — revoke ALL active shares for the store "
        "(every active row gets `is_deleted=True`).\n"
        "- `[u1, u2, ...]` — sync diff:\n"
        "  - users in payload + no row → INSERT with `is_deleted=False`.\n"
        "  - users in payload + soft-deleted row → revive (`is_deleted=False`).\n"
        "  - users in payload + active row → keep (touch `updated_at`).\n"
        "  - users **not** in payload + active row → revoke (`is_deleted=True`).\n\n"
        "All changes happen in a single transaction; any error rolls everything back.\n\n"
        "**Pre-checks:** store must exist and not be deleted; current user must own it; "
        "every user_id (when payload is non-empty) must exist."
    ),
    responses={
        400: {"description": "One or more user IDs are invalid"},
        403: {"description": "Forbidden: not the store owner"},
        404: {"description": "Store not found"},
    },
)
async def sync_shared_store(
    data: SharedStoreSyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = SharedStoreService(db)
    try:
        return await service.sync_shares(
            store_id=data.store_id,
            user_ids=data.user_ids,
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
            detail=f"Error syncing shared store: {str(e)}",
        )
