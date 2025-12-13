from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from app.core.query import CommonQuery
from app.domain.schemas.task_work import TaskWorkCreate, TaskWorkUpdate, TaskWorkResponse, TaskWorkFilter, TaskWorkListResponse
from app.domain.services.export_issues_service import WorkIssuesDocxCreator
from app.domain.services.export_work_service import TaskWorkDocxCreator, TaskWorkDocxCreatorGroup
from app.presentation.api.dependencies import get_current_user, get_common_query, get_task_service
from app.presentation.api.v1.schemas.auth import TokenData
from sqlalchemy import select, distinct, func
from app.domain.models.task_work import TaskWork
from app.domain.models.task import Task
from datetime import datetime
from app.domain.services.task_service import TaskService
from app.domain.services.task_work_service import TaskWorkService
from app.presentation.api.v1.endpoints.internal.dashboard import DashboardService
from app.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models.user import User

router = APIRouter()

@router.post("", response_model=TaskWorkResponse)
async def create_task_work(
    task_work: TaskWorkCreate,
    current_user: TokenData = Depends(get_current_user),
    common_query: CommonQuery = Depends(get_common_query)
):
    
    """Create a new task work"""
    try:
        result = await common_query.create_task_work(task_work.model_dump(), current_user.user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{task_work_id}", response_model=TaskWorkResponse)
async def get_task_work(
    task_work_id: int,
    common_query: CommonQuery = Depends(get_common_query)
):
    """Get a task work by ID"""
    try:
        result = await common_query.get_task_work(task_work_id)
        if not result:
            raise HTTPException(status_code=404, detail="Task work not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{task_work_id}", response_model=TaskWorkResponse)
async def update_task_work(
    task_work_id: int,
    task_work: TaskWorkUpdate,
    common_query: CommonQuery = Depends(get_common_query)
):
    """Update a task work"""
    try:
        result = await common_query.update_task_work(task_work_id, task_work.model_dump(exclude_unset=True))
        if not result:
            raise HTTPException(status_code=404, detail="Task work not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{task_work_id}")
async def delete_task_work(
    task_work_id: int,
    current_user: TokenData = Depends(get_current_user),
    common_query: CommonQuery = Depends(get_common_query)
):
    """Delete a task work"""
    try:
        # First get the task work to check ownership
        task_work = await common_query.get_task_work(task_work_id)
        if not task_work:
            raise HTTPException(status_code=404, detail="Task work not found")
            
        # Check if the current user is the creator of the task work
        if task_work["created_by"] != current_user.user_id:
            raise HTTPException(status_code=403, detail="You can only delete your own task works")
            
        # Delete the task work
        success = await common_query.delete_task_work(task_work_id)
        if not success:
            raise HTTPException(status_code=404, detail="Task work not found")
            
        return {"message": "Task work deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=dict)
async def list_task_works(
    task_id: Optional[int] = Query(None, description="Filter by task ID"),
    from_date: Optional[datetime] = Query(None, description="Filter by created_at from date"),
    to_date: Optional[datetime] = Query(None, description="Filter by created_at to date"),
    search: Optional[str] = Query(None, description="Search in title, description and content"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    current_user: TokenData = Depends(get_current_user),
    common_query: CommonQuery = Depends(get_common_query)
):
    """List task works with optional filters"""
    try:
        result = await common_query.list_task_works(
            task_id=task_id,
            user_id=current_user.user_id,  # Get user_id from token
            from_date=from_date,
            to_date=to_date,
            search=search,
            page=page,
            page_size=page_size
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export/", response_model=dict)
async def list_task_works(
    task_id: Optional[int] = Query(None, description="Filter by task ID"),
    from_date: Optional[datetime] = Query(None, description="Filter by created_at from date"),
    to_date: Optional[datetime] = Query(None, description="Filter by created_at to date"),
    search: Optional[str] = Query(None, description="Search in title, description and content"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=10000, description="Items per page"),
    ids: Optional[str] = Query(None, description="Filter by task work IDs (comma-separated)"),
    current_user: TokenData = Depends(get_current_user),
    common_query: CommonQuery = Depends(get_common_query)
):
    """List task works with optional filters"""
    try:
        # Parse ids string to list of integers
        parsed_ids = None
        if ids:
            try:
                parsed_ids = [int(id_str.strip()) for id_str in ids.split(',') if id_str.strip()]
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid ID format: {str(e)}")
        
        result = await common_query.list_task_works(
            task_id=task_id,
            ids=parsed_ids,
            user_id=current_user.user_id,  # Get user_id from token
            from_date=from_date,
            to_date=to_date,
            search=search,
            page=1,
            page_size=10000
        )
        export_service = TaskWorkDocxCreator(common_query.session)
        return {'download_url': await export_service.create_docx(result["items"])}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/task/{task_id}", response_model=dict)
async def get_task_works_by_task(
    task_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    common_query: CommonQuery = Depends(get_common_query)
):
    """Get all task works for a specific task"""
    try:
        result = await common_query.list_task_works(
            task_id=task_id,
            page=page,
            page_size=page_size
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/my-tasks/", response_model=List[dict])
async def get_my_works_tasks(
    current_user: TokenData = Depends(get_current_user),
    common_query: CommonQuery = Depends(get_common_query)
):
    """Get a list of unique tasks from all works created by the current user"""
    try:
        # Get all task works created by the user
        result = await common_query.list_task_works(
            user_id=current_user.user_id,
            page=1,
            page_size=1000  # Large number to get all works
        )
        
        # Extract unique task IDs and ensure they are integers
        task_ids = set()
        for work in result["items"]:
            task_id = work.get("task_id")
            if task_id is not None:
                try:
                    # Convert to integer if it's a string
                    if isinstance(task_id, str):
                        task_id = int(task_id)
                    task_ids.add(task_id)
                except (ValueError, TypeError):
                    continue  # Skip invalid task IDs
        
        # Get task details for each unique task ID
        tasks = []
        for task_id in task_ids:
            task = await common_query.get_task(task_id)
            if task:
                tasks.append(task)
        
        return tasks
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/count-by-tasks", response_model=dict)
async def count_task_works_by_tasks(
    task_ids: List[int],
    common_query: CommonQuery = Depends(get_common_query)
):
    """Count task works for a list of task IDs"""
    try:
        result = await common_query.count_task_works_by_tasks(task_ids)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/task/{task_id}/all-works", response_model=dict)
async def get_all_task_works_with_children(
    task_id: int,
    task_service: TaskService = Depends(get_task_service)
):
    """Get all task works for a task and its child tasks"""
    try:
        result = await task_service.get_all_task_works_with_children(task_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/difficult-from-children/", response_model=dict)
async def get_difficult_task_works_from_children(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    task_id: Optional[int] = Query(None, description="Filter by specific task ID"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date (created_at >= start_date)"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date (created_at <= end_date)"),
    search: Optional[str] = Query(None, description="Search text in title and description"),
    current_user: TokenData = Depends(get_current_user),
    task_service: TaskService = Depends(get_task_service)
):
    """Get difficult task works (is_difficult = true) from the current user and all children users with optional filters"""
    try:
        result = await task_service.get_difficult_task_works_from_children(
            current_user_id=current_user.user_id,
            page=page,
            page_size=page_size,
            task_id=task_id,
            start_date=start_date,
            end_date=end_date,
            search_text=search
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/difficult-from-children/export/", response_model=dict)
async def get_difficult_task_works_from_children(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=10000, description="Items per page"),
    task_id: Optional[int] = Query(None, description="Filter by specific task ID"),
    ids: Optional[str] = Query(None, description="Filter by task work IDs (comma-separated)"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date (created_at >= start_date)"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date (created_at <= end_date)"),
    search: Optional[str] = Query(None, description="Search text in title and description"),
    current_user: TokenData = Depends(get_current_user),
    task_service: TaskService = Depends(get_task_service),
    common_query: CommonQuery = Depends(get_common_query)
):
    """Get difficult task works (is_difficult = true) from the current user and all children users with optional filters"""
    try:
        parsed_ids = None
        if ids:
            try:
                parsed_ids = [int(id_str.strip()) for id_str in ids.split(',') if id_str.strip()]
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid ID format: {str(e)}")
        

        result = await task_service.get_difficult_task_works_from_children(
            current_user_id=current_user.user_id,
            page=1,
            page_size=10000,
            task_id=task_id,
            ids=parsed_ids,
            start_date=start_date,
            end_date=end_date,
            search_text=search
        )
        export_service = WorkIssuesDocxCreator(common_query.session)
        return {'download_url': await export_service.create_docx(result["items"])}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/common-works/", response_model=dict)
async def get_no_task_works_of_children(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Lấy danh sách TaskWork của current user và tất cả các con mà có task_id = null, kèm thông tin creator"""
    try:
        dashboard_service = DashboardService(db)
        user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)
        # Join với User để lấy thông tin creator
        query = select(TaskWork, User).join(User, TaskWork.created_by == User.id).where(
            TaskWork.created_by.in_(user_ids),
            TaskWork.task_id == None
        ).order_by(TaskWork.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        rows = result.all()
        items = []
        for work, creator in rows:
            work_dict = work.to_dict()
            work_dict["creator"] = creator.to_dict() if creator else None
            items.append(work_dict)
        # Đếm tổng số
        count_query = select(func.count()).select_from(TaskWork).where(
            TaskWork.created_by.in_(user_ids),
            TaskWork.task_id == None
        )
        total = await db.scalar(count_query)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/by-user-hierarchy/", response_model=dict)
async def get_task_works_by_user_hierarchy(
    user_id: Optional[int] = Query(None, description="Lọc theo user_id cụ thể (nếu không truyền sẽ lấy tất cả user hiện tại và các con)"),
    task_id: Optional[int] = Query(None, description="Lọc theo task_id cụ thể"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    from_date: Optional[datetime] = Query(None, description="Lọc theo ngày tạo từ (YYYY-MM-DD hoặc ISO format)"),
    to_date: Optional[datetime] = Query(None, description="Lọc theo ngày tạo đến (YYYY-MM-DD hoặc ISO format)"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tiêu đề, mô tả, nội dung"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Lấy danh sách TaskWork của user hiện tại và các user cấp con, cho phép lọc theo user_id, ngày tạo, tìm kiếm và phân trang. Trả về cả thông tin task nếu có."""
    try:
        from app.domain.models.user import User
        from app.domain.models.task import Task
        from app.presentation.api.v1.endpoints.internal.dashboard import DashboardService
        dashboard_service = DashboardService(db)
        # Lấy danh sách user_id: nếu có user_id truyền vào thì chỉ lấy user đó, không thì lấy current + các con
        if user_id is not None:
            user_ids = [user_id]
        else:
            user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)
        # Join với User và Task để lấy thông tin creator và task
        conditions = [TaskWork.created_by.in_(user_ids)]
        if task_id is not None:
            conditions.append(TaskWork.task_id == task_id)
        if from_date is not None:
            if from_date.tzinfo is not None:
                from_date = from_date.replace(tzinfo=None)
            conditions.append(TaskWork.created_at >= from_date)
        if to_date is not None:
            if to_date.tzinfo is not None:
                to_date = to_date.replace(tzinfo=None)
            if to_date.hour == 0 and to_date.minute == 0 and to_date.second == 0:
                to_date = to_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            conditions.append(TaskWork.created_at <= to_date)
        if search:
            from sqlalchemy import or_
            like_pattern = f"%{search}%"
            conditions.append(or_(
                TaskWork.title.ilike(like_pattern),
                TaskWork.description.ilike(like_pattern),
                TaskWork.content.ilike(like_pattern)
            ))
        from sqlalchemy.orm import aliased
        WorkCreator = aliased(User)
        TaskCreator = aliased(User)
        query = select(TaskWork, WorkCreator, Task, TaskCreator).join(WorkCreator, TaskWork.created_by == WorkCreator.id).join(Task, TaskWork.task_id == Task.id, isouter=True).join(TaskCreator, Task.created_by == TaskCreator.id, isouter=True).where(
            *conditions
        ).order_by(TaskWork.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        rows = result.all()
        items = []
        for work, work_creator, task, task_creator in rows:
            work_dict = work.to_dict()
            work_dict["creator"] = work_creator.to_dict() if work_creator else None
            if task:
                task_dict = task.to_dict()
                task_dict["creator"] = task_creator.to_dict() if task_creator else None
                work_dict["task"] = task_dict
            else:
                work_dict["task"] = None
            items.append(work_dict)
        # Đếm tổng số
        count_query = select(func.count()).select_from(TaskWork).where(*conditions)
        total = await db.scalar(count_query)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export-v2/", response_model=dict)
async def export_task_works_v2(
    user_id: Optional[int] = Query(None, description="Lọc theo user_id cụ thể (nếu không truyền sẽ lấy tất cả user hiện tại và các con)"),
    from_date: Optional[datetime] = Query(None, description="Lọc theo ngày tạo từ (YYYY-MM-DD hoặc ISO format)"),
    to_date: Optional[datetime] = Query(None, description="Lọc theo ngày tạo đến (YYYY-MM-DD hoặc ISO format)"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tiêu đề, mô tả, nội dung"),
    ids: Optional[str] = Query(None, description="Lọc theo task work IDs (comma-separated)"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    common_query: CommonQuery = Depends(get_common_query)
):
    """Export task works theo logic by-user-hierarchy và ids, cho phép lọc theo user, ngày, search, ids. Mỗi item có creator và task."""
    try:
        from app.presentation.api.v1.endpoints.internal.dashboard import DashboardService
        dashboard_service = DashboardService(db)
        # Lấy danh sách user_id: nếu có user_id truyền vào thì chỉ lấy user đó, không thì lấy current + các con
        if user_id is not None:
            user_ids = [user_id]
        else:
            user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)
        # Parse ids nếu có
        parsed_ids = None
        if ids:
            try:
                parsed_ids = [int(id_str.strip()) for id_str in ids.split(',') if id_str.strip()]
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid ID format: {str(e)}")
        # Xây dựng điều kiện lọc
        from sqlalchemy import or_
        conditions = [TaskWork.created_by.in_(user_ids)]
        if parsed_ids:
            conditions.append(TaskWork.id.in_(parsed_ids))
        if from_date is not None:
            # Chuyển về naive datetime nếu có timezone
            if from_date.tzinfo is not None:
                from_date = from_date.replace(tzinfo=None)
            conditions.append(TaskWork.created_at >= from_date)
        if to_date is not None:
            # Chuyển về naive datetime nếu có timezone
            if to_date.tzinfo is not None:
                to_date = to_date.replace(tzinfo=None)
            # Đặt to_date về cuối ngày nếu chỉ truyền ngày
            if to_date.hour == 0 and to_date.minute == 0 and to_date.second == 0:
                to_date = to_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            conditions.append(TaskWork.created_at <= to_date)
        if search:
            like_pattern = f"%{search}%"
            conditions.append(or_(
                TaskWork.title.ilike(like_pattern),
                TaskWork.description.ilike(like_pattern),
                TaskWork.content.ilike(like_pattern)
            ))
        # Lấy tất cả work thỏa mãn, join với User và Task
        query = select(TaskWork, User, Task).join(User, TaskWork.created_by == User.id).join(Task, TaskWork.task_id == Task.id, isouter=True).where(*conditions).order_by(TaskWork.created_at.desc())
        result = await db.execute(query)
        rows = result.all()
        items = []
        for work, creator, task in rows:
            work_dict = work.to_dict()
            work_dict["creator"] = creator.to_dict() if creator else None
            work_dict["task"] = task.to_dict() if task else None
            items.append(work_dict)
        # Export using the new grouped export service
        export_service = TaskWorkDocxCreatorGroup(common_query.session)
        return {'download_url': await export_service.create_docx(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/user-works", response_model=TaskWorkListResponse, summary="Lấy danh sách work của user theo thời gian")
async def get_user_works_by_period(
    filter_data: TaskWorkFilter,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Lấy danh sách work của một user trong khoảng thời gian
    - Lọc theo user_id, from_time, to_time
    - Sắp xếp theo thời gian tạo giảm dần (mới nhất trước)
    - Trả về tổng số work và danh sách chi tiết
    """
    try:
        task_work_service = TaskWorkService(db)
        result = await task_work_service.get_user_works_by_period(filter_data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
