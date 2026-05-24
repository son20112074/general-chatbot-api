from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, List
from datetime import datetime


# ── Store CRUD ────────────────────────────────────────────────

class StoreCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Store name")
    description: Optional[str] = Field(default=None)


class StoreUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None)


class StoreResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_by: Optional[int] = None
    owner: Optional[Dict[str, Any]] = None
    is_deleted: bool = False
    is_shared: Optional[bool] = False
    file_total: Optional[int] = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


# ── Store Files ───────────────────────────────────────────────

class StoreFileMatchRequest(BaseModel):
    store_id: int = Field(..., gt=0)
    file_id: int = Field(..., gt=0)


class StoreFileBulkRequest(BaseModel):
    """Body for bulk add/remove of files into a store.

    `file_ids` must be non-empty. Duplicates are de-duplicated server-side.
    """
    store_id: int = Field(..., gt=0, description="Target store ID")
    file_ids: List[int] = Field(..., min_length=1, description="List of file IDs to add or remove")


# ── Shared Store ──────────────────────────────────────────────

class SharedStoreSyncRequest(BaseModel):
    """Sync-style upsert request for share_store.

    - `user_ids = None`  → no-op (only validates ownership).
    - `user_ids = []`    → revoke ALL active shares for the store.
    - `user_ids = [...]` → set the share-list to exactly these users:
        * pairs in payload but not in DB → insert (is_deleted=False)
        * pairs in payload and in DB     → update is_deleted=False
        * pairs in DB but not in payload → set is_deleted=True
    """
    store_id: int = Field(..., gt=0, description="Store to share")
    user_ids: Optional[List[int]] = Field(
        default=None,
        description="Full list of users that should have active access. None = no-op."
    )


class SharedStoreSyncResponse(BaseModel):
    added: int = 0
    kept: int = 0
    revoked: int = 0
    total_active: int = 0
