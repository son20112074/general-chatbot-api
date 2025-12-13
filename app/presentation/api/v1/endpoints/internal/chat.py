from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.presentation.api.v1.schemas.chat import FirstMessageResponse
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.domain.models.chat_message import ChatMessage

router = APIRouter(prefix="", tags=["Chat"])


@router.get("/first-messages", response_model=List[FirstMessageResponse])
async def get_first_messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
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
            func.row_number()
            .over(partition_by=ChatMessage.session_id, order_by=ChatMessage.created_at.asc())
            .label("rn"),
        )
        .subquery()
    )

    stmt = select(
        subq.c.session_id,
        subq.c.id,
        subq.c.data,
        subq.c.type,
        subq.c.created_at,
    ).where(subq.c.rn == 1).order_by(subq.c.created_at.desc())

    # Apply pagination
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    result = await db.execute(stmt)
    rows = result.mappings().all()

    return [
        FirstMessageResponse(
            session_id=row["session_id"],
            id=row["id"],
            data=row["data"],
            type=row["type"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
