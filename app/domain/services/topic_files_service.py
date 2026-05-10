from datetime import datetime
from typing import List, Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select, func, or_, update
from app.domain.models.user import User
from app.core.config import settings
from app.domain.models.topic import Topic
from app.domain.models.file import File
from app.domain.models.file_topic import FileTopic
from app.utils.helpers import build_file_item

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
            files.append(build_file_item(file, u_id, u_name))

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

    # ── bulk add / remove ────────────────────────────────────

    async def bulk_add_files_to_topic(
        self,
        topic_id: int,
        file_ids: List[int],
        current_user_id: int,
    ) -> dict:
        """Owner-only. Strict pre-check + atomic upsert.

        Steps:
        1. Validate topic ownership.
        2. Validate every file_id exists and is not soft-deleted. If any missing → 400.
        3. Diff existing rows (file_id IN (:ids), topic=this) vs requested.
           - missing → INSERT is_matched=True
           - existing → UPDATE is_matched=True, updated_at=now
        4. Single transaction. Rolls back on any error.
        """
        await self._get_topic_for_owner(topic_id, current_user_id)
        ids = list(dict.fromkeys(int(x) for x in file_ids))

        files_q = select(File.id).where(File.id.in_(ids), File.is_deleted == False)
        existing_files = {row[0] for row in (await self.db.execute(files_q)).all()}
        missing = [fid for fid in ids if fid not in existing_files]
        if missing:
            raise ValueError(f"File ids not found or deleted: {missing}")

        try:
            existing_q = select(FileTopic).where(
                FileTopic.topic_id == topic_id,
                FileTopic.file_id.in_(ids),
            )
            existing_rows = list((await self.db.execute(existing_q)).scalars())
            existing_ids = {row.file_id for row in existing_rows}

            now = datetime.utcnow()
            inserted = 0
            updated = 0

            new_ids = [fid for fid in ids if fid not in existing_ids]
            for fid in new_ids:
                self.db.add(FileTopic(
                    file_id=fid, topic_id=topic_id, is_matched=True,
                    created_at=now, updated_at=now,
                ))
                inserted += 1

            for row in existing_rows:
                row.is_matched = True
                row.updated_at = now
                updated += 1

            await self.db.commit()
            return {"inserted": inserted, "updated": updated, "total": inserted + updated}
        except Exception:
            await self.db.rollback()
            raise

    async def bulk_remove_files_from_topic(
        self,
        topic_id: int,
        file_ids: List[int],
        current_user_id: int,
    ) -> dict:
        """Owner-only. Set is_matched=False for matching (topic_id, file_id) rows.

        Atomic. Only flips currently-active rows; missing pairs are silently ignored.
        """
        await self._get_topic_for_owner(topic_id, current_user_id)
        ids = list(dict.fromkeys(int(x) for x in file_ids))

        try:
            now = datetime.utcnow()
            stmt = (
                update(FileTopic)
                .where(
                    FileTopic.topic_id == topic_id,
                    FileTopic.file_id.in_(ids),
                    FileTopic.is_matched == True,
                )
                .values(is_matched=False, updated_at=now)
                .execution_options(synchronize_session=False)
            )
            result = await self.db.execute(stmt)
            await self.db.commit()
            updated = result.rowcount or 0
            return {"updated": updated, "total": updated}
        except Exception:
            await self.db.rollback()
            raise

