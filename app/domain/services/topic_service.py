from datetime import datetime
from typing import List, Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select, func, or_
from app.domain.models.user import User
from app.core.config import settings
from app.presentation.api.v1.schemas.topic import TopicCreate, TopicUpdate, TopicResponse
from app.domain.models.topic import Topic
from app.domain.models.file_topic import FileTopic

ADMIN_ROLE_ID = settings.ADMIN_ROLE_ID


def _escape_like(value: str) -> str:
    """Escape SQL LIKE wildcards to prevent pattern injection."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class TopicService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── CRUD ─────────────────────────────────────────────────

    async def create_topic(self, topic_data: TopicCreate, current_user_id: int) -> User:
        topic = Topic(
            name=topic_data.name,
            description=topic_data.description,
            reclassify_lookback_day=topic_data.reclassify_lookback_day,
            created_by=current_user_id,
            created_at=datetime.utcnow(),
        )
        self.db.add(topic)
        await self.db.commit()
        await self.db.refresh(topic)
        return topic

    async def get_topic(self, topic_id: int) -> Optional[TopicResponse]:
        query = (
            select(Topic)
            .where(
                and_(
                    Topic.id == topic_id,
                    Topic.is_deleted == False 
                )
            )
        )
        
        result = await self.db.execute(query)
        topic_obj = result.scalar_one_or_none()

        if not topic_obj:
            return None

        return topic_obj

    async def get_topics(
        self,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        current_role_id: Optional[int] = None,
        current_user_id: Optional[int] = None
    ) -> Dict:
        """Get subordinate topics (flat). Admin gets all.
        Search by name or description.
        """
        query = (
            select(Topic, User.id.label("u_id"), User.full_name.label("u_name"))
            .outerjoin(User, Topic.created_by == User.id)
            .where(Topic.is_deleted == False))
        
        count_query = select(func.count()).select_from(Topic).outerjoin(User, Topic.created_by == User.id).where(Topic.is_deleted == False)

        # RBAC: non-admin sees only subordinate users (child roles, not peers) and users => new version: only current users
        if current_role_id and current_role_id != ADMIN_ROLE_ID:
            # child_role_ids = await self.get_child_roles(current_role_id)
            
            # owner
            filter = (User.id == current_user_id)
            # if child_role_ids:
            #     filter = or_(User.role_id.in_(child_role_ids), filter)
            
            query = query.where(filter)
            count_query = count_query.where(filter)

        if search:
            escaped = _escape_like(search)
            search_filter = or_(
                Topic.name.ilike(f"%{escaped}%"),
                Topic.description.ilike(f"%{escaped}%")
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(Topic.created_at.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        rows = list(result)

        # Performance: aggregate file_total only over the paged topic IDs (not all topics).
        # Index `idx_file_topics_topic_id` covers the topic_id IN (...) lookup;
        # is_matched filter is applied during the index scan.
        paged_topic_ids = [topic.id for topic, _u_id, _u_name in rows]
        totals_map: Dict[int, int] = {}
        if paged_topic_ids:
            totals_q = (
                select(FileTopic.topic_id, func.count(FileTopic.id).label("file_total"))
                .where(
                    FileTopic.topic_id.in_(paged_topic_ids),
                    FileTopic.is_matched == True,
                )
                .group_by(FileTopic.topic_id)
            )
            totals_result = await self.db.execute(totals_q)
            totals_map = {tid: cnt for tid, cnt in totals_result.all()}

        topics = []
        for topic, u_id, u_name in rows:
            item = self._build_topic_response(topic, u_id, u_name)
            item["file_total"] = totals_map.get(topic.id, 0)
            topics.append(item)

        return {"data": topics, "total": total}
    
    async def get_child_roles(self, role_id: int) -> List[int]:
        """Delegate to RoleService to avoid duplicating hierarchy logic."""
        from app.domain.services.role_service import RoleService
        return await RoleService(self.db).get_child_roles(role_id)

    async def update_topic(self, topic_id: int, user_data: TopicUpdate, current_user_id: int) -> Optional[TopicResponse]:
        """Update topic. Admin full access. Others can only update subordinate topics."""
        topic = await self.get_topic(topic_id)
        if not topic:
            return None
        
        if topic.created_by != current_user_id:
            raise PermissionError("You can not update this topic")

        update_data = user_data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(topic, field, value)

        await self.db.commit()
        await self.db.refresh(topic)
        return topic
    
    async def delete_topic(self, topic_id: int, current_user_id: int) -> bool:
        """Soft-delete: set is_deleted=True."""
        topic = await self.get_topic(topic_id)
        if not topic:
            return None
        
        if topic.created_by != current_user_id:
            raise PermissionError("You can not delete this topic")

        topic.is_deleted = True
        await self.db.commit()
        return True

    def _build_topic_response(self, topic, u_id: Optional[int], u_name: Optional[str]) -> dict:
        topic_data = {
            column.name: getattr(topic, column.name)
            for column in topic.__table__.columns
        }

        # add owner
        topic_data["owner"] = {
            "id": u_id,
            "full_name": u_name
        } if u_id else None

        return topic_data
