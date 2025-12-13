from typing import List, Dict, Any, Optional
from sqlalchemy import select, func, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from app.domain.models.task import Task
from app.domain.models.task_work import TaskWork
from app.domain.models.user import User
from app.domain.models.role import Role
from datetime import datetime

class TaskService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_difficult_task_works_from_children(
        self, 
        current_user_id: int, 
        page: int = 1, 
        page_size: int = 10,
        task_id: Optional[int] = None,
        ids: Optional[List[int]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        search_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get difficult task works (is_difficult = true) from the current user and all children users
        
        Args:
            current_user_id: The ID of the current user
            page: Page number for pagination
            page_size: Number of items per page
            task_id: Optional filter by specific task ID
            start_date: Optional filter by start date (created_at >= start_date)
            end_date: Optional filter by end date (created_at <= end_date)
            search_text: Optional search text in title and description
            
        Returns:
            Dictionary containing difficult task works and metadata
        """
        try:
            # First get the current user's role
            user_query = select(User).where(User.id == current_user_id)
            user_result = await self.session.execute(user_query)
            current_user = user_result.scalar_one_or_none()
            
            if not current_user:
                raise ValueError("Current user not found")
            
            # Get all child role IDs based on the current user's role hierarchy
            child_roles_query = text("""
                SELECT r.id 
                FROM roles r 
                WHERE r.parent_path ILIKE :exact_path 
                OR r.parent_path ILIKE :anywhere_path
            """)
            
            child_roles_result = await self.session.execute(
                child_roles_query,
                {
                    "exact_path": f",{current_user.role_id},",
                    "anywhere_path": f"%,{current_user.role_id},%"
                }
            )
            child_role_ids = [row[0] for row in child_roles_result]
            
            # Get all users who have these child roles
            child_users_query = select(User.id).where(User.role_id.in_(child_role_ids))
            child_users_result = await self.session.execute(child_users_query)
            child_user_ids = [row[0] for row in child_users_result]
            
            # Include current user in the list of users to query
            all_user_ids = [current_user_id] + child_user_ids
            
            if not all_user_ids:
                return {
                    "items": [],
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                    "child_users_count": 0,
                    "current_user_included": True,
                    "filters_applied": {
                        "task_id": task_id,
                        "start_date": start_date.isoformat() if start_date else None,
                        "end_date": end_date.isoformat() if end_date else None,
                        "search_text": search_text
                    }
                }
            
            # Build base query for difficult task works
            difficult_works_query = select(
                TaskWork, Task, User
            ).join(
                Task, TaskWork.task_id == Task.id, isouter=True
            ).join(
                User, TaskWork.created_by == User.id
            ).where(
                and_(
                    TaskWork.is_difficult == True,
                    TaskWork.created_by.in_(all_user_ids)
                )
            )
            
            # Apply filters
            filter_conditions = []
            
            # Filter by task_id
            if task_id is not None:
                filter_conditions.append(TaskWork.task_id == task_id)
            
            # Filter by IDs
            if ids is not None and len(ids) > 0:
                filter_conditions.append(TaskWork.id.in_(ids))
            
            # Filter by date range
            if start_date is not None:
                # Convert to naive datetime if timezone-aware
                if start_date.tzinfo is not None:
                    start_date = start_date.replace(tzinfo=None)
                filter_conditions.append(TaskWork.created_at >= start_date)
            
            if end_date is not None:
                # Convert to naive datetime if timezone-aware
                if end_date.tzinfo is not None:
                    end_date = end_date.replace(tzinfo=None)
                # Set time to end of day for end_date
                end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
                filter_conditions.append(TaskWork.created_at <= end_date)
            
            # Filter by search text in title and description
            if search_text:
                search_conditions = [
                    TaskWork.title.ilike(f"%{search_text}%"),
                    TaskWork.description.ilike(f"%{search_text}%")
                ]
                filter_conditions.append(or_(*search_conditions))
            
            # Apply all filters
            if filter_conditions:
                difficult_works_query = difficult_works_query.where(and_(*filter_conditions))
            
            # Order by created_at desc
            difficult_works_query = difficult_works_query.order_by(TaskWork.created_at.desc())
            
            # Get total count with same filters
            count_query = select(func.count(TaskWork.id)).where(
                and_(
                    TaskWork.is_difficult == True,
                    TaskWork.created_by.in_(all_user_ids)
                )
            )
            
            # Apply same filters to count query
            if filter_conditions:
                count_query = count_query.where(and_(*filter_conditions))
            
            total_result = await self.session.execute(count_query)
            total = total_result.scalar()
            
            # Add pagination
            difficult_works_query = difficult_works_query.offset((page - 1) * page_size).limit(page_size)
            
            # Execute the main query
            result = await self.session.execute(difficult_works_query)
            rows = result.all()
            
            # Process results
            items = []
            for row in rows:
                task_work_dict = row[0].to_dict()
                if row[1]:  # Task exists
                    task_work_dict['task'] = row[1].to_dict()
                else:
                    task_work_dict['task'] = None
                
                if row[2]:  # User exists
                    task_work_dict['creator'] = row[2].to_dict()
                    # Add flag to identify if this is the current user's work
                    task_work_dict['is_current_user'] = (row[2].id == current_user_id)
                else:
                    task_work_dict['creator'] = None
                    task_work_dict['is_current_user'] = False
                
                items.append(task_work_dict)
            
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "child_users_count": len(child_user_ids),
                "current_user_role_id": current_user.role_id,
                "current_user_included": True,
                "total_users_queried": len(all_user_ids),
                "filters_applied": {
                    "task_id": task_id,
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None,
                    "search_text": search_text
                }
            }
            
        except ValueError as e:
            raise e
        except Exception as e:
            raise Exception(f"Error getting difficult task works from children: {str(e)}")

    async def delete_task(self, task_id: int, user_id: int) -> Dict[str, Any]:
        """
        Delete a task by ID with proper authorization and dependency checks
        
        Args:
            task_id: The ID of the task to delete
            user_id: The ID of the user attempting to delete the task
            
        Returns:
            Dictionary containing deletion result and metadata
            
        Raises:
            ValueError: If task doesn't exist or user doesn't have permission
            Exception: If task has dependencies or other errors occur
        """
        try:
            # Check if task exists
            task_query = select(Task).where(Task.id == task_id)
            result = await self.session.execute(task_query)
            task = result.scalar_one_or_none()
            
            if not task:
                raise ValueError("Task not found")
            
            # Check if user is the task creator
            if task.created_by != user_id:
                raise ValueError("Only task creator can delete the task")
            
            # Check if task has any associated task works
            works_query = select(func.count(TaskWork.id)).where(TaskWork.task_id == task_id)
            works_result = await self.session.execute(works_query)
            works_count = works_result.scalar()
            
            if works_count > 0:
                raise Exception(f"Cannot delete task that has {works_count} associated task works. Please delete all task works first.")
            
            # Check if task has any child tasks
            child_tasks_query = select(func.count(Task.id)).where(
                Task.parent_path.like(f"%,{task_id},%")
            )
            child_result = await self.session.execute(child_tasks_query)
            child_count = child_result.scalar()
            
            if child_count > 0:
                raise Exception(f"Cannot delete task that has {child_count} child tasks. Please delete all child tasks first.")
            
            # Store task info before deletion for response
            task_info = task.to_dict()
            
            # Delete the task
            delete_stmt = delete(Task).where(Task.id == task_id)
            await self.session.execute(delete_stmt)
            await self.session.commit()
            
            return {
                "success": True,
                "message": "Task deleted successfully",
                "deleted_task": task_info,
                "deleted_count": 1
            }
            
        except ValueError as e:
            # Rollback transaction for validation errors
            await self.session.rollback()
            raise e
        except Exception as e:
            # Rollback transaction for other errors
            await self.session.rollback()
            raise Exception(f"Error deleting task: {str(e)}")

    async def get_all_task_works_with_children(self, task_id: int) -> Dict[str, Any]:
        """
        Get all task works for a task and its child tasks, trả về cả thông tin creator
        """
        try:
            # First get the parent task to verify it exists
            parent_task = await self.session.execute(
                select(Task).where(Task.id == task_id)
            )
            parent_task = parent_task.scalar_one_or_none()
            
            if not parent_task:
                return {
                    "items": [],
                    "total": 0,
                    "parent_task": None
                }

            # Get all child task IDs by matching parent_path
            child_tasks_query = select(Task.id).where(
                Task.parent_path.like(f"%,{task_id},%")
            )
            child_tasks_result = await self.session.execute(child_tasks_query)
            child_task_ids = [row[0] for row in child_tasks_result]
            
            # Combine parent and child task IDs
            all_task_ids = [task_id] + child_task_ids
            
            # Get all task works for these tasks, join với User để lấy creator
            works_query = select(TaskWork, User).join(User, TaskWork.created_by == User.id).where(
                TaskWork.task_id.in_(all_task_ids)
            ).order_by(
                TaskWork.created_at.desc()
            )
            result = await self.session.execute(works_query)
            rows = result.all()
            # Process results
            items = []
            for work, creator in rows:
                work_dict = work.to_dict()
                work_dict["creator"] = creator.to_dict() if creator else None
                items.append(work_dict)
            return {
                "items": items,
                "total": len(items),
                "parent_task": parent_task.to_dict(),
                "child_task_count": len(child_task_ids)
            }
        except Exception as e:
            raise Exception(f"Error getting task works with children: {str(e)}")

    async def get_assigned_tasks(self, user_id: int) -> Dict[str, Any]:
        """
        Get all tasks assigned to the current user
        
        Args:
            user_id: The ID of the user to get assigned tasks for
            
        Returns:
            Dictionary containing assigned tasks and metadata
        """
        try:
            # Query tasks where user_id is in the assigned_to array, only select id and title
            tasks_query = select(Task.id, Task.title).where(
                Task.assigned_to.any(user_id)
            ).order_by(
                Task.created_at.desc()
            )
            
            result = await self.session.execute(tasks_query)
            tasks = result.all()
            
            # Get total count
            count_query = select(func.count(Task.id)).where(
                Task.assigned_to.any(user_id)
            )
            total_result = await self.session.execute(count_query)
            total = total_result.scalar()
            
            # Process results - only id and title
            items = [{"id": task[0], "title": task[1]} for task in tasks]
            
            return {
                "items": items,
                "total": total,
                "user_id": user_id
            }
            
        except Exception as e:
            raise Exception(f"Error getting assigned tasks: {str(e)}") 