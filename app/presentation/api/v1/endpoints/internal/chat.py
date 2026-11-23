from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.presentation.api.v1.schemas.chat import (
    FirstMessageListResponse,
    FirstMessageResponse,
    LatestSessionResponse,
)
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.domain.models.chat_message import ChatMessage
from app.domain.models.session import Session
from app.domain.services.file_service import FileQueryService

router = APIRouter(prefix="", tags=["Chat"])

from app.core.config import settings
# admin: có thể xem tất cả
# non-admin: lọc theo user_id trong Session, chỉ xem session của mình và user con


def _escape_like(value: str) -> str:
    """Escape SQL LIKE wildcards so keyword search is literal."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _empty_first_messages() -> FirstMessageListResponse:
    return FirstMessageListResponse(items=[], total=0)


@router.get("/first-messages", response_model=FirstMessageListResponse)
async def get_first_messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    user_id: Optional[int] = Query(None, description="Filter sessions owned by this user"),
    keyword: Optional[str] = Query(None, description="Search first-message content"),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    # Build a subquery with row_number over each session_id ordered by created_at asc
    subq = (
        select(
            ChatMessage.session_id.label("session_id"),
            ChatMessage.id.label("id"),
            ChatMessage.data.label("data"),
            ChatMessage.type.label("type"),
            ChatMessage.created_at.label("created_at"),
            ChatMessage.chat_type.label("chat_type"),
            ChatMessage.source_path.label("source_path"),
            func.row_number()
            .over(partition_by=ChatMessage.session_id, order_by=ChatMessage.created_at.asc())
            .label("rn"),
        )
        .where(ChatMessage.chat_type == 'file')
        .subquery()
    )

    stmt = (
        select(
            subq.c.session_id,
            subq.c.id,
            subq.c.data,
            subq.c.type,
            subq.c.source_path,
            subq.c.created_at,
        )
        .select_from(subq)
        .where(subq.c.rn == 1)
    )

    # Phân quyền: non-admin chỉ xem session của mình và user role con.
    # user_id ngoài tập đó trả rỗng. Admin không lọc user trừ khi chọn user_id.
    filter_user_ids: Optional[List[str]] = None
    if current_user.role_id != settings.ADMIN_ROLE_ID:
        file_query_service = FileQueryService(db)
        user_ids = await file_query_service.get_user_hierarchy_ids(current_user.user_id)
        allowed_user_ids_str = [str(uid) for uid in user_ids]
        if user_id is not None and str(user_id) not in allowed_user_ids_str:
            return _empty_first_messages()
        if user_id is not None:
            filter_user_ids = [str(user_id)]
        else:
            filter_user_ids = allowed_user_ids_str
        if not filter_user_ids:
            return _empty_first_messages()
    elif user_id is not None:
        filter_user_ids = [str(user_id)]

    if filter_user_ids is not None:
        stmt = stmt.join(Session, subq.c.session_id == Session.session_id)
        stmt = stmt.where(Session.user_id.in_(filter_user_ids))

    search = (keyword or "").strip()
    if search:
        matched_sessions = (
            select(ChatMessage.session_id)
            .where(
                ChatMessage.chat_type == "file",
                ChatMessage.data.ilike(f"%{_escape_like(search)}%", escape="\\"),
            )
            .distinct()
        )
        stmt = stmt.where(subq.c.session_id.in_(matched_sessions))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(subq.c.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    rows = result.mappings().all()
    items = [
        FirstMessageResponse(
            session_id=row["session_id"],
            id=row["id"],
            data=row["data"],
            type=row["type"],
            source_path=row["source_path"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    return FirstMessageListResponse(items=items, total=total)


@router.get("/latest-session", response_model=LatestSessionResponse)
async def get_latest_session_by_source_path(
    source_path: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """Return the most recent chat session for the current user and source_path."""
    stmt = (
        select(
            ChatMessage.session_id,
            ChatMessage.source_path,
            ChatMessage.created_at,
        )
        .join(Session, ChatMessage.session_id == Session.session_id)
        .where(
            ChatMessage.source_path == source_path,
            Session.user_id == str(current_user.user_id),
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(1)
    )

    result = await db.execute(stmt)
    row = result.mappings().first()
    if not row:
        return LatestSessionResponse(session_id=None, source_path=source_path)

    return LatestSessionResponse(
        session_id=row["session_id"],
        source_path=row["source_path"],
        last_message_at=row["created_at"],
    )
