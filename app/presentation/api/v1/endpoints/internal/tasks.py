from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from app.core.query import CommonQuery, QueryInput, CursorPaginationResult
from app.domain.services.task_service import TaskService
from app.presentation.api.dependencies import get_common_query, get_current_user, get_task_service
from app.presentation.api.v1.schemas.auth import TokenData
from app.domain.schemas.task import TaskCreate, TaskUpdate, TaskResponse
from app.domain.services.export_task_service import TaskDocxCreator
router = APIRouter(prefix="", tags=["Tasks"])

@router.post("/my-tasks")
async def query_user_tasks(
    query_input: QueryInput,
    common_query: CommonQuery = Depends(get_common_query),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Query tasks that are either created by the user, assigned to the user, or are children of those tasks.
    
    Parameters:
    - query_input: Query parameters including:
        - fields: List of fields to select
        - page_size: Number of items per page
        - cursor: Cursor for pagination
        - sort_by: Field to sort by
        - sort_order: Sort order ("asc" or "desc")
        - search_text: Text to search for
        - search_fields: List of fields to search in
        - condition: Additional conditions to filter by
    """
    try:
        # Execute user tasks query
        result = await common_query.query_user_tasks(current_user.user_id, query_input, current_user.role_id)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error querying user tasks: {str(e)}"
        )
        

@router.post("/my-tasks/export")
async def query_user_tasks(
    query_input: QueryInput,
    common_query: CommonQuery = Depends(get_common_query),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Query tasks that are either created by the user, assigned to the user, or are children of those tasks.
    
    Parameters:
    - query_input: Query parameters including:
        - fields: List of fields to select
        - page_size: Number of items per page
        - cursor: Cursor for pagination
        - sort_by: Field to sort by
        - sort_order: Sort order ("asc" or "desc")
        - search_text: Text to search for
        - search_fields: List of fields to search in
        - condition: Additional conditions to filter by
    """
    try:
        query_input.page = 1
        query_input.page_size = 10000
        
        # Execute user tasks query
        result = await common_query.query_user_tasks(current_user.user_id, query_input, current_user.role_id)
        
        export_service = TaskDocxCreator(common_query.session)
        
        download_url = await export_service.create_docx(result['data'])
        
        return {'download_url': download_url}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error querying user tasks: {str(e)}"
        )

@router.post("/assigned-tasks-by-date")
async def query_assigned_tasks_by_date(
    start_date: datetime,
    end_date: datetime,
    query_input: QueryInput,
    common_query: CommonQuery = Depends(get_common_query),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Query tasks assigned to the current user within a date range or with no end date.
    
    Parameters:
    - start_date: Start date of the range
    - end_date: End date of the range
    - query_input: Query parameters including:
        - fields: List of fields to select
        - page_size: Number of items per page
        - cursor: Cursor for pagination
        - sort_by: Field to sort by
        - sort_order: Sort order ("asc" or "desc")
        - search_text: Text to search for
        - search_fields: List of fields to search in
        - condition: Additional conditions to filter by
    """
    try:
        # Execute assigned tasks query
        result = await common_query.query_assigned_tasks_by_date(
            current_user.user_id,
            start_date,
            end_date,
            query_input
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error querying assigned tasks: {str(e)}"
        )

@router.post("/tasks-by-date")
async def query_tasks_by_date(
    date: datetime,
    query_input: QueryInput,
    common_query: CommonQuery = Depends(get_common_query),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Query tasks assigned to the current user for a specific date, including both periodic and ad-hoc tasks that are not completed.
    
    Parameters:
    - date: The specific date to query tasks for
    - query_input: Query parameters including:
        - fields: List of fields to select
        - page_size: Number of items per page
        - cursor: Cursor for pagination
        - sort_by: Field to sort by
        - sort_order: Sort order ("asc" or "desc")
        - search_text: Text to search for
        - search_fields: List of fields to search in
        - condition: Additional conditions to filter by
    """
    try:
        # Execute tasks by date query
        result = await common_query.query_tasks_by_date(
            current_user.user_id,
            date,
            query_input
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error querying tasks by date: {str(e)}"
        )

@router.post("/confirm/{task_id}")
async def confirm_task(
    task_id: int,
    current_user: TokenData = Depends(get_current_user),
    common_query: CommonQuery = Depends(get_common_query)
):
    """Confirm a task and update its status from 'new' to 'in_progress'"""
    try:
        # First check if task exists and is assigned to current user
        task = await common_query.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
            
        if current_user.user_id not in task["assigned_to"]:
            raise HTTPException(status_code=403, detail="You are not assigned to this task")
                        
        # Update personal task status for current user first
        personal_status = await common_query.insert_personal_task_status(
            task_id=task_id,
            user_id=current_user.user_id,
            status="in_progress"
        )
        
        # Check if all assigned users have "in_progress" status
        should_update_task = await common_query.should_update_task_status(task_id, "in_progress")
        
        result = task  # Keep original task data
        if should_update_task:
            # Update task status only if all users have "in_progress" status
            update_data = {
                "status": "in_progress"
            }
            result = await common_query.update_task(task_id, update_data)
            if not result:
                raise HTTPException(status_code=404, detail="Task not found")
            
        return {
            "message": "Task confirmed successfully",
            "task": result,
            "personal_status": personal_status,
            "task_status_updated": should_update_task
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cancel-confirm/{task_id}")
async def cancel_confirm_task(
    task_id: int,
    current_user: TokenData = Depends(get_current_user),
    common_query: CommonQuery = Depends(get_common_query)
):
    """Cancel task confirmation and update its status from 'in_progress' back to 'new'"""
    try:
        # First check if task exists and is assigned to current user
        task = await common_query.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
            
        if current_user.user_id not in task["assigned_to"]:
            raise HTTPException(status_code=403, detail="You are not assigned to this task")
                        
        # Update personal task status for current user first
        personal_status = await common_query.insert_personal_task_status(
            task_id=task_id,
            user_id=current_user.user_id,
            status="new"
        )
        
        # Check if all assigned users have "new" status
        should_update_task = await common_query.should_update_task_status(task_id, "new")
        
        result = task  # Keep original task data
        if should_update_task:
            # Update task status only if all users have "new" status
            update_data = {
                "status": "new"
            }
            result = await common_query.update_task(task_id, update_data)
            if not result:
                raise HTTPException(status_code=404, detail="Task not found")
            
        return {
            "message": "Task confirmation cancelled successfully",
            "task": result,
            "personal_status": personal_status,
            "task_status_updated": should_update_task
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/complete/{task_id}")
async def complete_task(
    task_id: int,
    current_user: TokenData = Depends(get_current_user),
    common_query: CommonQuery = Depends(get_common_query)
):
    """Mark a task as completed"""
    try:
        # First check if task exists and is assigned to current user
        task = await common_query.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
            
        if current_user.user_id not in task["assigned_to"] :
            raise HTTPException(status_code=403, detail="You are not assigned to this task")
                        
        # Update personal task status for current user first
        personal_status = await common_query.insert_personal_task_status(
            task_id=task_id,
            user_id=current_user.user_id,
            status="completed"
        )
        
        # Check if all assigned users have "completed" status
        should_update_task = await common_query.should_update_task_status(task_id, "completed")
        
        result = task  # Keep original task data
        if should_update_task:
            # Update task status and progress only if all users have "completed" status
            update_data = {
                "status": "completed",
                "progress": 100
            }
            result = await common_query.update_task(task_id, update_data)
            if not result:
                raise HTTPException(status_code=404, detail="Task not found")
            
        return {
            "message": "Task marked as completed successfully",
            "task": result,
            "personal_status": personal_status,
            "task_status_updated": should_update_task
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 
    

@router.get("/{task_id}/all-works", response_model=dict)
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

@router.get("/assigned-tasks", response_model=dict)
async def get_assigned_tasks(
    current_user: TokenData = Depends(get_current_user),
    task_service: TaskService = Depends(get_task_service)
):
    """Get all tasks assigned to the current user"""
    try:
        result = await task_service.get_assigned_tasks(current_user.user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", response_model=TaskResponse)
async def create_task(
    task: TaskCreate,
    current_user: TokenData = Depends(get_current_user),
    common_query: CommonQuery = Depends(get_common_query)
):
    """Create a new task"""
    try:
        result = await common_query.create_task(task.model_dump(), current_user.user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    task: TaskUpdate,
    current_user: TokenData = Depends(get_current_user),
    common_query: CommonQuery = Depends(get_common_query)
):
    """Update a task"""
    try:
        # Check if task exists and current user has permission
        existing_task = await common_query.get_task(task_id)
        if not existing_task:
            raise HTTPException(status_code=404, detail="Task not found")
            
        # Only task creator can update the task
        if existing_task["created_by"] != current_user.user_id:
            raise HTTPException(status_code=403, detail="Only task creator can update the task")
            
        result = await common_query.update_task(task_id, task.model_dump(exclude_unset=True))
        if not result:
            raise HTTPException(status_code=404, detail="Task not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    current_user: TokenData = Depends(get_current_user),
    task_service: TaskService = Depends(get_task_service)
):
    """Delete a task by ID"""
    try:
        result = await task_service.delete_task(task_id, current_user.user_id)
        return result
    except ValueError as e:
        if "Task not found" in str(e):
            raise HTTPException(status_code=404, detail="Task not found")
        elif "Only task creator can delete" in str(e):
            raise HTTPException(status_code=403, detail="Only task creator can delete the task")
        else:
            raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if "associated task works" in str(e) or "child tasks" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        else:
            raise HTTPException(status_code=500, detail=str(e)) 

@router.get("/{task_id}/personal-status")
async def get_task_personal_status(
    task_id: int,
    current_user: TokenData = Depends(get_current_user),
    common_query: CommonQuery = Depends(get_common_query)
):
    """Get personal task status for the current user"""
    try:
        # First check if task exists and is assigned to current user
        task = await common_query.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
            
        if current_user.user_id not in task["assigned_to"]:
            raise HTTPException(status_code=403, detail="You are not assigned to this task")
        
        # Get personal task status for current user
        personal_statuses = await common_query.get_personal_task_statuses(task_id)
        
        # Find the status for current user
        user_personal_status = None
        for status in personal_statuses:
            if status["user_id"] == current_user.user_id:
                user_personal_status = status
                break
        
        # If no personal status found, return default "new" status
        if not user_personal_status:
            user_personal_status = {
                "id": None,
                "task_id": task_id,
                "user_id": current_user.user_id,
                "status": "new",
                "created_at": None,
                "updated_at": None
            }
            
        return {
            "task_id": task_id,
            "user_id": current_user.user_id,
            "personal_status": user_personal_status,
            "task_status": task["status"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 

@router.get("/{task_id}/all-personal-statuses")
async def get_all_task_personal_statuses(
    task_id: int,
    current_user: TokenData = Depends(get_current_user),
    common_query: CommonQuery = Depends(get_common_query)
):
    """Get personal task statuses for all assigned users of a task"""
    try:
        # First check if task exists
        task = await common_query.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Check if current user is assigned to this task or is the creator
        if current_user.user_id not in task["assigned_to"] and current_user.user_id != task["created_by"]:
            raise HTTPException(status_code=403, detail="You don't have permission to view this task")
        
        # Get all personal task statuses for this task
        personal_statuses = await common_query.get_personal_task_statuses(task_id)
        
        # Create a map of user_id to personal status
        status_map = {ps["user_id"]: ps for ps in personal_statuses}
        
        # Get all assigned users and their statuses
        assigned_users_statuses = []
        for user_id in task["assigned_to"]:
            user_status = status_map.get(user_id, {
                "id": None,
                "task_id": task_id,
                "user_id": user_id,
                "status": "new",
                "created_at": None,
                "updated_at": None
            })
            assigned_users_statuses.append(user_status)
            
        return {
            "task_id": task_id,
            "task_status": task["status"],
            "assigned_users_count": len(task["assigned_to"]),
            "personal_statuses": assigned_users_statuses,
            "summary": {
                "new": len([s for s in assigned_users_statuses if s["status"] == "new"]),
                "in_progress": len([s for s in assigned_users_statuses if s["status"] == "in_progress"]),
                "completed": len([s for s in assigned_users_statuses if s["status"] == "completed"])
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 

@router.get("/{task_id}/debug-personal-status")
async def debug_task_personal_status(
    task_id: int,
    current_user: TokenData = Depends(get_current_user),
    common_query: CommonQuery = Depends(get_common_query)
):
    """Debug endpoint to check personal task status data"""
    try:
        debug_data = await common_query.debug_personal_task_status(task_id, current_user.user_id)
        return debug_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 