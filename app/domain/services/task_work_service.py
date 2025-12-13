from datetime import datetime
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.domain.models.task_work import TaskWork
from app.domain.schemas.task_work import TaskWorkFilter, TaskWorkResponse, TaskWorkListResponse

class TaskWorkService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_works_by_period(self, filter_data: TaskWorkFilter) -> TaskWorkListResponse:
        """Lấy danh sách work của user trong khoảng thời gian"""
        # Chuyển datetime về UTC để tránh lỗi timezone
        from_time_utc = filter_data.from_time.replace(tzinfo=None) if filter_data.from_time.tzinfo else filter_data.from_time
        to_time_utc = filter_data.to_time.replace(tzinfo=None) if filter_data.to_time.tzinfo else filter_data.to_time
        
        # Query để lấy works của user trong khoảng thời gian
        query = select(TaskWork).where(
            and_(
                TaskWork.created_by == filter_data.user_id,
                TaskWork.created_at >= from_time_utc,
                TaskWork.created_at <= to_time_utc
            )
        ).order_by(TaskWork.created_at.desc())
        
        result = await self.db.execute(query)
        works = result.scalars().all()
        
        # Convert sang response format
        work_responses = []
        for work in works:
            work_response = TaskWorkResponse(
                id=work.id,
                title=work.title,
                description=work.description,
                content=work.content,
                image_links=work.image_links or [],
                file_links=work.file_links or [],
                attributes=work.attributes or {},
                is_difficult=work.is_difficult if work.is_difficult is not None else False,
                task_id=work.task_id,
                created_by=work.created_by,
                created_at=work.created_at
            )
            work_responses.append(work_response)
        
        return TaskWorkListResponse(
            user_id=filter_data.user_id,
            from_time=filter_data.from_time,
            to_time=filter_data.to_time,
            total_count=len(work_responses),
            works=work_responses
        ) 