from datetime import datetime
from typing import Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select, func, or_, update
from app.domain.models.user import User
from app.core.config import settings
from app.domain.models.topic import Topic
from app.domain.models.file import File
from app.domain.models.file_topic import FileTopic

ADMIN_ROLE_ID = settings.ADMIN_ROLE_ID


def _escape_like(value: str) -> str:
    """Escape SQL LIKE wildcards to prevent pattern injection."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class TopicFilesService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_topic_files(
        self,
        skip: int = 0,
        limit: int = 100,
        topic_id: Optional[int] = None,
        search: Optional[str] = None,
        current_role_id: Optional[int] = None,
        current_user_id: Optional[int] = None
    ) -> Dict:
        """Get subordinate files of topic.
        Search by file name or owner name of files.
        """
        query = (
            select(File, User.id.label("u_id"), User.full_name.label("u_name"))
            .select_from(FileTopic)
            .join(File, FileTopic.file_id == File.id)
            .join(Topic, FileTopic.topic_id == Topic.id)
            .outerjoin(User, File.created_by == User.id)
            .where(
                and_(
                    FileTopic.topic_id == topic_id,
                    FileTopic.is_matched == True,
                    File.is_deleted == False,
                    or_(
                        Topic.created_by == current_user_id, # owner: include all file type
                        File.type == "organization"               # not owner: only include file type "organization"
                    )
                )
            )
        )
        
        count_query = (
            select(func.count())
            .select_from(FileTopic)
            .join(File, FileTopic.file_id == File.id)
            .join(Topic, FileTopic.topic_id == Topic.id)
            .outerjoin(User, File.created_by == User.id)
            .where(
                and_(
                    FileTopic.topic_id == topic_id,
                    FileTopic.is_matched == True,
                    File.is_deleted == False,
                    or_(
                        Topic.created_by == current_user_id,
                        File.type == "organization"
                    )
                )
            )
        )

        if search:
            escaped = _escape_like(search)
            search_filter = or_(
                File.name.ilike(f"%{escaped}%"),
                User.full_name.ilike(f"%{escaped}%"),
                File.summary.ilike(f"%{escaped}%"),
                File.content.ilike(f"%{escaped}%")
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(File.created_at.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        files = []

        for file, u_id, u_name in result:
            files.append(self._build_file_item(file, u_id, u_name))

        return {"data": files, "total": total}
    
    async def _get_topic_for_owner(self, topic_id: int, current_user_id: int) -> Topic:
        """Fetch active topic and verify current user owns it. Raises on missing/forbidden."""
        topic_result = await self.db.execute(
            select(Topic).where(Topic.id == topic_id, Topic.is_deleted == False)
        )
        topic = topic_result.scalar_one_or_none()
        if not topic:
            raise LookupError("Topic not found")
        if topic.created_by != current_user_id:
            raise PermissionError("You can not modify this topic")
        return topic

    async def _get_active_file(self, file_id: int) -> File:
        """Fetch a non-deleted file. Raises if missing or soft-deleted."""
        file_result = await self.db.execute(
            select(File).where(File.id == file_id, File.is_deleted == False)
        )
        f = file_result.scalar_one_or_none()
        if not f:
            raise LookupError("File not found")
        return f

    async def add_file_to_topic(
        self,
        topic_id: int,
        file_id: int,
        current_user_id: int,
    ) -> dict:
        """Owner-only: insert a file→topic match (is_matched=True) or update if it already exists."""
        await self._get_topic_for_owner(topic_id, current_user_id)
        await self._get_active_file(file_id)

        existing_q = select(FileTopic).where(
            FileTopic.topic_id == topic_id, FileTopic.file_id == file_id
        )
        existing = (await self.db.execute(existing_q)).scalar_one_or_none()

        if existing is None:
            now = datetime.utcnow()
            ft = FileTopic(
                file_id=file_id,
                topic_id=topic_id,
                is_matched=True,
                created_at=now,
                updated_at=now,
            )
            self.db.add(ft)
            await self.db.commit()
            await self.db.refresh(ft)
            return {"id": ft.id, "topic_id": topic_id, "file_id": file_id, "is_matched": True}

        existing.is_matched = True
        existing.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(existing)
        return {"id": existing.id, "topic_id": topic_id, "file_id": file_id, "is_matched": True}

    async def remove_file_from_topic(
        self,
        topic_id: int,
        file_id: int,
        current_user_id: int,
    ) -> dict:
        """Owner-only: set is_matched=False on the (topic_id, file_id) record."""
        await self._get_topic_for_owner(topic_id, current_user_id)

        existing_q = select(FileTopic).where(
            FileTopic.topic_id == topic_id, FileTopic.file_id == file_id
        )
        existing = (await self.db.execute(existing_q)).scalar_one_or_none()
        if existing is None:
            raise LookupError("File is not matched to this topic")

        existing.is_matched = False
        existing.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(existing)
        return {"id": existing.id, "topic_id": topic_id, "file_id": file_id, "is_matched": False}

    def _build_file_item(self, f, u_id, u_name) -> dict:
        """Build a file list item dict from a File ORM object and owner info."""
        return {
            "id": f.id, "name": f.name, "size": f.size,
            "hash": f.hash, "path": f.path,
            "url": f.url,
            "extension": f.extension, "mime_type": f.mime_type,
            "node_path": f.node_path,
            "owner": {"id": u_id, "full_name": u_name} if u_id else None,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None,
            "is_processed": f.is_processed,
            "processing_duration": f.processing_duration,
            "content": f.content,
            "summary": f.summary,
        }
    
