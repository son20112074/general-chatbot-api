from typing import Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select, func, or_
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
                        File.type != "private"               # not owner: only include file type "genaral" and "organization"
                    )
                )
            )
        )
        
        count_query = (
            select(func.count())
            .select_from(FileTopic)
            .join(File, FileTopic.file_id == File.id)
            .join(Topic, FileTopic.topic_id == Topic.id)
            .where(
                and_(
                    FileTopic.topic_id == topic_id,
                    File.is_deleted == False,
                    or_(
                        Topic.created_by == current_user_id, 
                        File.type != "private"    
                    ) 
                )
            )
        )

        if search:
            escaped = _escape_like(search)
            search_filter = or_(
                File.name.ilike(f"%{escaped}%"),
                User.full_name.ilike(f"%{escaped}%")
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
    
