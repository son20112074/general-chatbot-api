from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from app.core.database import get_db
from app.domain.models.task import Task
from app.domain.models.task_work import TaskWork
from app.domain.models.user import User
from app.domain.models.role import Role
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from sqlalchemy.sql import text
from app.domain.services.export_employee_performance_service import EmployeePerformanceExcelCreator

router = APIRouter(prefix="", tags=["Dashboard"])

class DashboardService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_hierarchy_ids(self, current_user_id: int) -> list[int]:
        """Get all user IDs including current user and all children users"""
        # Get current user's role
        user_query = select(User).where(User.id == current_user_id)
        user_result = await self.session.execute(user_query)
        current_user = user_result.scalar_one_or_none()
        
        if not current_user:
            return [current_user_id]
        
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
        
        # Get all users who have these child roles and are not deleted (status = true)
        child_users_query = select(User.id).where(
            and_(
                User.role_id.in_(child_role_ids),
                User.status == True  # Only include active users (not deleted)
            )
        )
        child_users_result = await self.session.execute(child_users_query)
        child_user_ids = [row[0] for row in child_users_result]
        
        # Include current user in the list (only if current user is also active)
        all_user_ids = child_user_ids
        if current_user.status == True:  # Only include current user if active
            all_user_ids = [current_user_id] + child_user_ids
        
        return all_user_ids

    async def get_task_statistics(self, user_ids: list[int], from_time: datetime, to_time: datetime) -> Dict[str, int]:
        """Get task statistics for a given time period"""
        # Build base query for tasks created by users in the hierarchy
        base_condition = Task.created_by.in_(user_ids)
        
        # Add time range condition
        time_condition = and_(
            Task.created_at >= from_time,
            Task.created_at <= to_time
        )
        
        # Total tasks
        total_query = select(func.count(Task.id)).where(
            and_(base_condition, time_condition)
        )
        total_result = await self.session.execute(total_query)
        total_tasks = total_result.scalar() or 0
        
        # Completed tasks
        completed_query = select(func.count(Task.id)).where(
            and_(
                base_condition,
                time_condition,
                Task.status == 'completed'
            )
        )
        completed_result = await self.session.execute(completed_query)
        completed_tasks = completed_result.scalar() or 0
        
        # Pending tasks (new status)
        pending_query = select(func.count(Task.id)).where(
            and_(
                base_condition,
                time_condition,
                Task.status == 'new'
            )
        )
        pending_result = await self.session.execute(pending_query)
        pending_tasks = pending_result.scalar() or 0
        
        # In-progress tasks
        in_progress_query = select(func.count(Task.id)).where(
            and_(
                base_condition,
                time_condition,
                Task.status == 'in_progress'
            )
        )
        in_progress_result = await self.session.execute(in_progress_query)
        in_progress_tasks = in_progress_result.scalar() or 0
        
        return {
            'total': total_tasks,
            'completed': completed_tasks,
            'pending': pending_tasks,
            'in_progress': in_progress_tasks
        }

    async def get_task_work_statistics(self, user_ids: list[int], from_time: datetime, to_time: datetime) -> Dict[str, int]:
        """Get task work statistics for a given time period"""
        # Build base query for task works created by users in the hierarchy
        base_condition = TaskWork.created_by.in_(user_ids)
        
        # Add time range condition
        time_condition = and_(
            TaskWork.created_at >= from_time,
            TaskWork.created_at <= to_time
        )
        
        # Total task works
        total_query = select(func.count(TaskWork.id)).where(
            and_(base_condition, time_condition)
        )
        total_result = await self.session.execute(total_query)
        total_task_works = total_result.scalar() or 0
        
        # Difficult task works (issues)
        difficult_query = select(func.count(TaskWork.id)).where(
            and_(
                base_condition,
                time_condition,
                TaskWork.is_difficult == True
            )
        )
        difficult_result = await self.session.execute(difficult_query)
        difficult_task_works = difficult_result.scalar() or 0
        
        return {
            'total': total_task_works,
            'difficult': difficult_task_works
        }

    async def get_top_employee_performance(self, user_ids: list[int], from_time: datetime, to_time: datetime, limit: int = 5) -> list[Dict[str, Any]]:
        """Get top performing employees based on task completion rate"""
        try:
            # Query to get task statistics per user
            performance_query = text("""
                SELECT 
                    u.id as user_id,
                    u.full_name,
                    u.email,
                    COUNT(t.id) as total_tasks,
                    COUNT(CASE WHEN t.status = 'completed' THEN 1 END) as completed_tasks,
                    CASE 
                        WHEN COUNT(t.id) > 0 THEN 
                            ROUND((COUNT(CASE WHEN t.status = 'completed' THEN 1 END) * 100.0 / COUNT(t.id)), 1)
                        ELSE 0 
                    END as completion_rate
                FROM users u
                LEFT JOIN tasks t ON u.id = ANY(t.assigned_to)
                    AND t.created_at >= :from_time 
                    AND t.created_at <= :to_time
                WHERE u.id = ANY(:user_ids)
                    AND u.status = true  -- Only include active users (not deleted)
                GROUP BY u.id, u.full_name, u.email
                HAVING COUNT(t.id) > 0
                ORDER BY completion_rate DESC, completed_tasks DESC
                LIMIT :limit
            """)
            
            result = await self.session.execute(
                performance_query,
                {
                    "user_ids": user_ids,
                    "from_time": from_time,
                    "to_time": to_time,
                    "limit": limit
                }
            )

            employees = []
            for row in result:
                employees.append({
                    'user_id': row[0],
                    'full_name': row[1] or 'Unknown',
                    'email': row[2],
                    'total_tasks': row[3],
                    'completed_tasks': row[4],
                    'completion_rate': float(row[5]) if row[5] else 0.0
                })
            
            return employees
            
        except Exception as e:
            raise Exception(f"Error getting employee performance: {str(e)}")

    async def get_task_work_chart_data(self, user_ids: list[int], from_date: datetime, to_date: datetime, period: str = 'weekly', timezone: str = 'Asia/Bangkok') -> list[Dict[str, Any]]:
        """Get task work chart data grouped by time periods"""
        try:
            # Define period format and interval based on period type
            if period == 'weekly':
                # Group by week (Monday to Sunday)
                date_format = "YYYY-'W'WW"
                date_trunc = "week"
            elif period == 'monthly':
                # Group by month
                date_format = "YYYY-MM"
                date_trunc = "month"
            elif period == 'quarterly':
                # Group by quarter
                date_format = "YYYY-'Q'Q"
                date_trunc = "quarter"
            else:
                raise ValueError("Period must be 'weekly', 'monthly', or 'quarterly'")
            
            # Query to get task work counts grouped by time period with timezone support
            chart_query = text("""
                SELECT 
                    DATE_TRUNC(:date_trunc, (tw.created_at AT TIME ZONE 'UTC' AT TIME ZONE :timezone)::date) as period_start,
                    COUNT(tw.id) as total_works,
                    COUNT(CASE WHEN tw.is_difficult = true THEN 1 END) as difficult_works
                FROM task_works tw
                INNER JOIN users u ON tw.created_by = u.id
                WHERE tw.created_by = ANY(:user_ids)
                    AND u.status = true  -- Only include active users (not deleted)
                    AND tw.created_at >= :from_date
                    AND tw.created_at <= :to_date
                GROUP BY DATE_TRUNC(:date_trunc, (tw.created_at AT TIME ZONE 'UTC' AT TIME ZONE :timezone)::date)
                ORDER BY period_start
            """)
            
            result = await self.session.execute(
                chart_query,
                {
                    "user_ids": user_ids,
                    "from_date": from_date,
                    "to_date": to_date,
                    "date_trunc": date_trunc,
                    "timezone": timezone
                }
            )
            
            chart_data = []
            for row in result:
                period_start = row[0]
                
                # Create readable period labels
                if period == 'weekly':
                    # Format: "Tuần 1 (01/01 - 07/01)"
                    try:
                        week_start = period_start
                        week_end = period_start + timedelta(days=6)
                        week_number = period_start.isocalendar()[1]
                        start_str = week_start.strftime('%d/%m')
                        end_str = week_end.strftime('%d/%m')
                        period_label = f"Tuần {week_number}"
                    except Exception as e:
                        period_label = f"Tuần {period_start.strftime('%d/%m/%Y')}"
                elif period == 'monthly':
                    # Format: "Tháng 1/2025"
                    try:
                        period_label = f"Tháng {period_start.month}/{period_start.year}"
                    except Exception as e:
                        period_label = f"Tháng {period_start.strftime('%m/%Y')}"
                elif period == 'quarterly':
                    # Format: "Quý 1/2025"
                    try:
                        quarter = (period_start.month - 1) // 3 + 1
                        period_label = f"Quý {quarter}/{period_start.year}"
                    except Exception as e:
                        period_label = f"Quý {period_start.strftime('%m/%Y')}"
                
                chart_data.append({
                    'period_label': period_label,
                    'period_start': period_start.isoformat() if period_start else None,
                    'total_works': row[1],
                    'difficult_works': row[2],
                    'regular_works': row[1] - row[2]  # Calculate regular works
                })
            
            return chart_data
            
        except Exception as e:
            raise Exception(f"Error getting task work chart data: {str(e)}")

    async def get_recent_task_work_activities(self, user_ids: list[int], limit: int = 10) -> list[Dict[str, Any]]:
        """Get recent task work activities from current user and children users"""
        try:
            # Query to get recent task works with task and user information
            recent_query = text("""
                SELECT 
                    tw.id,
                    tw.title,
                    tw.description,
                    tw.content,
                    tw.is_difficult,
                    tw.created_at,
                    tw.created_by,
                    u.full_name as creator_name,
                    u.email as creator_email,
                    u.account_name as creator_username,
                    u.avatar as creator_avatar,
                    t.id as task_id,
                    t.title as task_title,
                    t.status as task_status
                FROM task_works tw
                LEFT JOIN users u ON tw.created_by = u.id
                LEFT JOIN tasks t ON tw.task_id = t.id
                WHERE tw.created_by = ANY(:user_ids)
                    AND u.status = true  -- Only include active users (not deleted)
                ORDER BY tw.created_at DESC
                LIMIT :limit
            """)
            
            result = await self.session.execute(
                recent_query,
                {
                    "user_ids": user_ids,
                    "limit": limit
                }
            )
            
            activities = []
            for row in result:
                # Convert content from HTML to plain text if needed
                content = row[3] or ""
                if content and "<" in content and ">" in content:
                    # Simple HTML to text conversion
                    import re
                    content = re.sub(r'<[^>]+>', '', content)
                    content = content.replace('&nbsp;', ' ').strip()
                
                # Truncate content if too long
                if len(content) > 200:
                    content = content[:200] + "..."
                
                # Create creator object
                creator = {
                    'id': row[6],
                    'full_name': row[7] or "Unknown",
                    'email': row[8] or "",
                    'account_name': row[9] or "",
                    'avatar': row[10] or ""
                }
                
                # Create task object
                task = {
                    'id': row[11],
                    'title': row[12] or "Không có nhiệm vụ",
                    'status': row[13] or "unknown"
                }
                
                activities.append({
                    'id': row[0],
                    'title': row[1] or "Không có tiêu đề",
                    'description': row[2] or "",
                    'content': content,
                    'is_difficult': row[4],
                    'created_at': row[5].isoformat() if row[5] else None,
                    'creator': creator,
                    'task': task,
                    'activity_type': 'difficult_work' if row[4] else 'regular_work'
                })
            
            return activities
            
        except Exception as e:
            raise Exception(f"Error getting recent task work activities: {str(e)}")

    def calculate_percentage_change(self, current: int, previous: int) -> float:
        """Calculate percentage change between current and previous values"""
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100, 1)

    async def get_dashboard_data(self, current_user_id: int, from_time: datetime, to_time: datetime) -> Dict[str, Any]:
        """Get comprehensive dashboard data with period comparison"""
        # Get all user IDs in hierarchy
        user_ids = await self.get_user_hierarchy_ids(current_user_id)
        
        # Calculate time period duration
        period_duration = to_time - from_time
        
        # Calculate previous period
        previous_from_time = from_time - period_duration
        previous_to_time = from_time
        
        # Get current period statistics
        current_task_stats = await self.get_task_statistics(user_ids, from_time, to_time)
        current_task_work_stats = await self.get_task_work_statistics(user_ids, from_time, to_time)
        
        # Get previous period statistics
        previous_task_stats = await self.get_task_statistics(user_ids, previous_from_time, previous_to_time)
        previous_task_work_stats = await self.get_task_work_statistics(user_ids, previous_from_time, previous_to_time)
        
        # Calculate percentage changes for tasks
        total_change = self.calculate_percentage_change(current_task_stats['total'], previous_task_stats['total'])
        completed_change = self.calculate_percentage_change(current_task_stats['completed'], previous_task_stats['completed'])
        pending_change = self.calculate_percentage_change(current_task_stats['pending'], previous_task_stats['pending'])
        in_progress_change = self.calculate_percentage_change(current_task_stats['in_progress'], previous_task_stats['in_progress'])
        
        # Calculate percentage changes for task works
        total_task_works_change = self.calculate_percentage_change(current_task_work_stats['total'], previous_task_work_stats['total'])
        difficult_task_works_change = self.calculate_percentage_change(current_task_work_stats['difficult'], previous_task_work_stats['difficult'])
        
        return {
            'total_tasks': {
                'count': current_task_stats['total'],
                'change_percentage': total_change,
                'change_direction': 'up' if total_change > 0 else 'down' if total_change < 0 else 'neutral'
            },
            'completed_tasks': {
                'count': current_task_stats['completed'],
                'change_percentage': completed_change,
                'change_direction': 'up' if completed_change > 0 else 'down' if completed_change < 0 else 'neutral'
            },
            'pending_tasks': {
                'count': current_task_stats['pending'],
                'change_percentage': pending_change,
                'change_direction': 'up' if pending_change > 0 else 'down' if pending_change < 0 else 'neutral'
            },
            'in_progress_tasks': {
                'count': current_task_stats['in_progress'],
                'change_percentage': in_progress_change,
                'change_direction': 'up' if in_progress_change > 0 else 'down' if in_progress_change < 0 else 'neutral'
            },
            'total_task_works': {
                'count': current_task_work_stats['total'],
                'change_percentage': total_task_works_change,
                'change_direction': 'up' if total_task_works_change > 0 else 'down' if total_task_works_change < 0 else 'neutral'
            },
            'difficult_task_works': {
                'count': current_task_work_stats['difficult'],
                'change_percentage': difficult_task_works_change,
                'change_direction': 'up' if difficult_task_works_change > 0 else 'down' if difficult_task_works_change < 0 else 'neutral'
            },
            'period_info': {
                'current_from': from_time.isoformat(),
                'current_to': to_time.isoformat(),
                'previous_from': previous_from_time.isoformat(),
                'previous_to': previous_to_time.isoformat(),
                'user_count': len(user_ids)
            }
        }

    async def get_user_period_statistics(self, user_ids: list[int], from_date: datetime, to_date: datetime, period: str = 'daily', timezone: str = 'Asia/Bangkok') -> list[Dict[str, Any]]:
        """Get task work statistics grouped by user and time period with UTC+7 timezone support"""
        try:
            # Define period format and interval based on period type
            if period == 'daily':
                date_format = "YYYY-MM-DD"
                date_trunc = "day"
            elif period == 'monthly':
                date_format = "YYYY-MM"
                date_trunc = "month"
            elif period == 'quarterly':
                date_format = "YYYY-'Q'Q"
                date_trunc = "quarter"
            else:
                raise ValueError("Period must be 'daily', 'monthly', or 'quarterly'")
            
            # Query to get task work counts grouped by user and time period with timezone support
            chart_query = text("""
                SELECT 
                    u.id as user_id,
                    u.full_name as user_name,
                    u.email as user_email,
                    u.account_name as user_account,
                    DATE_TRUNC(:date_trunc, (tw.created_at AT TIME ZONE 'UTC' AT TIME ZONE :timezone)::date) as period_start,
                    COUNT(tw.id) as total_works,
                    COUNT(CASE WHEN tw.is_difficult = true THEN 1 END) as difficult_works,
                    COUNT(CASE WHEN tw.is_difficult = false THEN 1 END) as regular_works
                FROM task_works tw
                INNER JOIN users u ON tw.created_by = u.id
                WHERE tw.created_by = ANY(:user_ids)
                    AND u.status = true  -- Only include active users (not deleted)
                    AND tw.created_at >= :from_date
                    AND tw.created_at <= :to_date
                GROUP BY u.id, u.full_name, u.email, u.account_name, DATE_TRUNC(:date_trunc, (tw.created_at AT TIME ZONE 'UTC' AT TIME ZONE :timezone)::date)
                ORDER BY u.full_name, period_start
            """)
            
            result = await self.session.execute(
                chart_query,
                {
                    "user_ids": user_ids,
                    "from_date": from_date,
                    "to_date": to_date,
                    "date_trunc": date_trunc,
                    "timezone": timezone
                }
            )
            
            # Group results by user
            user_stats = {}
            for row in result:
                user_id = row[0]
                if user_id not in user_stats:
                    user_stats[user_id] = {
                        'user_id': user_id,
                        'user_name': row[1] or 'Unknown',
                        'user_email': row[2],
                        'user_account': row[3],
                        'periods': [],
                        'total_works': 0,
                        'total_difficult_works': 0,
                        'total_regular_works': 0
                    }
                
                period_data = {
                    'period_start': row[4].isoformat() if row[4] else None,
                    'total_works': row[5],
                    'difficult_works': row[6],
                    'regular_works': row[7]
                }
                
                user_stats[user_id]['periods'].append(period_data)
                user_stats[user_id]['total_works'] += row[5]
                user_stats[user_id]['total_difficult_works'] += row[6]
                user_stats[user_id]['total_regular_works'] += row[7]
            
            # Convert to list and calculate percentages
            result_list = []
            for user_data in user_stats.values():
                if user_data['total_works'] > 0:
                    user_data['difficult_percentage'] = round((user_data['total_difficult_works'] / user_data['total_works'] * 100), 1)
                    user_data['regular_percentage'] = round((user_data['total_regular_works'] / user_data['total_works'] * 100), 1)
                else:
                    user_data['difficult_percentage'] = 0
                    user_data['regular_percentage'] = 0
                
                result_list.append(user_data)
            
            return result_list
            
        except Exception as e:
            raise Exception(f"Error getting user period statistics: {str(e)}")

    async def get_user_daily_statistics(self, user_ids: list[int], from_date: datetime, to_date: datetime, timezone: str = 'Asia/Bangkok') -> list[Dict[str, Any]]:
        """Get daily task work statistics for each user"""
        return await self.get_user_period_statistics(user_ids, from_date, to_date, 'daily', timezone)

    async def get_user_monthly_statistics(self, user_ids: list[int], from_date: datetime, to_date: datetime, timezone: str = 'Asia/Bangkok') -> list[Dict[str, Any]]:
        """Get monthly task work statistics for each user"""
        return await self.get_user_period_statistics(user_ids, from_date, to_date, 'monthly', timezone)

    async def get_user_quarterly_statistics(self, user_ids: list[int], from_date: datetime, to_date: datetime, timezone: str = 'Asia/Bangkok') -> list[Dict[str, Any]]:
        """Get quarterly task work statistics for each user"""
        return await self.get_user_period_statistics(user_ids, from_date, to_date, 'quarterly', timezone)

@router.get("/task-statistics")
async def get_task_statistics(
    from_time: datetime = Query(..., description="Start time for the period"),
    to_time: datetime = Query(..., description="End time for the period"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get task statistics for the current user and their children users
    
    Parameters:
    - from_time: Start time for the period
    - to_time: End time for the period
    
    Returns:
    - Task statistics with comparison to previous period
    """
    try:
        dashboard_service = DashboardService(session)
        result = await dashboard_service.get_dashboard_data(
            current_user_id=current_user.user_id,
            from_time=from_time,
            to_time=to_time
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting dashboard data: {str(e)}"
        )

@router.get("/task-statistics/weekly")
async def get_weekly_task_statistics(
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get task statistics for the current week with comparison to last week
    """
    try:
        # Calculate current week (Monday to Sunday)
        today = datetime.now()
        days_since_monday = today.weekday()
        current_week_start = today - timedelta(days=days_since_monday)
        current_week_start = current_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        current_week_end = current_week_start + timedelta(days=7) - timedelta(microseconds=1)
        
        dashboard_service = DashboardService(session)
        result = await dashboard_service.get_dashboard_data(
            current_user_id=current_user.user_id,
            from_time=current_week_start,
            to_time=current_week_end
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting weekly dashboard data: {str(e)}"
        )

@router.get("/task-statistics/monthly")
async def get_monthly_task_statistics(
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get task statistics for the current month with comparison to last month
    """
    try:
        # Calculate current month
        today = datetime.now()
        current_month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate next month start
        if today.month == 12:
            next_month_start = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month_start = today.replace(month=today.month + 1, day=1)
        
        current_month_end = next_month_start - timedelta(microseconds=1)
        
        dashboard_service = DashboardService(session)
        result = await dashboard_service.get_dashboard_data(
            current_user_id=current_user.user_id,
            from_time=current_month_start,
            to_time=current_month_end
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting monthly dashboard data: {str(e)}"
        )

@router.get("/task-work-statistics")
async def get_task_work_statistics(
    from_time: datetime = Query(..., description="Start time for the period"),
    to_time: datetime = Query(..., description="End time for the period"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get task work statistics for the current user and their children users
    
    Parameters:
    - from_time: Start time for the period
    - to_time: End time for the period
    
    Returns:
    - Task work statistics with comparison to previous period
    """
    try:
        dashboard_service = DashboardService(session)
        result = await dashboard_service.get_dashboard_data(
            current_user_id=current_user.user_id,
            from_time=from_time,
            to_time=to_time
        )
        
        # Return only task work related statistics
        return {
            'total_task_works': result['total_task_works'],
            'difficult_task_works': result['difficult_task_works'],
            'period_info': result['period_info']
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting task work dashboard data: {str(e)}"
        )

@router.get("/task-work-statistics/weekly")
async def get_weekly_task_work_statistics(
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get task work statistics for the current week with comparison to last week
    """
    try:
        # Calculate current week (Monday to Sunday)
        today = datetime.now()
        days_since_monday = today.weekday()
        current_week_start = today - timedelta(days=days_since_monday)
        current_week_start = current_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        current_week_end = current_week_start + timedelta(days=7) - timedelta(microseconds=1)
        
        dashboard_service = DashboardService(session)
        result = await dashboard_service.get_dashboard_data(
            current_user_id=current_user.user_id,
            from_time=current_week_start,
            to_time=current_week_end
        )
        
        # Return only task work related statistics
        return {
            'total_task_works': result['total_task_works'],
            'difficult_task_works': result['difficult_task_works'],
            'period_info': result['period_info']
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting weekly task work dashboard data: {str(e)}"
        )

@router.get("/task-work-statistics/monthly")
async def get_monthly_task_work_statistics(
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get task work statistics for the current month with comparison to last month
    """
    try:
        # Calculate current month
        today = datetime.now()
        current_month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate next month start
        if today.month == 12:
            next_month_start = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month_start = today.replace(month=today.month + 1, day=1)
        
        current_month_end = next_month_start - timedelta(microseconds=1)
        
        dashboard_service = DashboardService(session)
        result = await dashboard_service.get_dashboard_data(
            current_user_id=current_user.user_id,
            from_time=current_month_start,
            to_time=current_month_end
        )
        
        # Return only task work related statistics
        return {
            'total_task_works': result['total_task_works'],
            'difficult_task_works': result['difficult_task_works'],
            'period_info': result['period_info']
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting monthly task work dashboard data: {str(e)}"
        )

@router.get("/employee-performance")
async def get_employee_performance(
    from_time: datetime = Query(..., description="Start time for the period"),
    to_time: datetime = Query(..., description="End time for the period"),
    limit: int = Query(5, ge=1, le=20, description="Number of top employees to return"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get top performing employees based on task completion rate
    
    Parameters:
    - from_time: Start time for the period
    - to_time: End time for the period
    - limit: Number of top employees to return (default: 5, max: 20)
    
    Returns:
    - Top performing employees with completion rates
    """
    try:
        dashboard_service = DashboardService(session)
        user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)

        employees = await dashboard_service.get_top_employee_performance(
            user_ids=user_ids,
            from_time=from_time,
            to_time=to_time,
            limit=limit
        )
        
        return {
            'employees': employees,
            'period_info': {
                'from_time': from_time.isoformat(),
                'to_time': to_time.isoformat(),
                'total_users_analyzed': len(user_ids)
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting employee performance: {str(e)}"
        )

@router.get("/employee-performance/weekly")
async def get_weekly_employee_performance(
    limit: int = Query(5, ge=1, le=20, description="Number of top employees to return"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get top performing employees for the current week
    """
    try:
        # Calculate current week (Monday to Sunday)
        today = datetime.now()
        days_since_monday = today.weekday()
        current_week_start = today - timedelta(days=days_since_monday)
        current_week_start = current_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        current_week_end = current_week_start + timedelta(days=7) - timedelta(microseconds=1)
        
        dashboard_service = DashboardService(session)
        user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)
        
        employees = await dashboard_service.get_top_employee_performance(
            user_ids=user_ids,
            from_time=current_week_start,
            to_time=current_week_end,
            limit=limit
        )
        
        return {
            'employees': employees,
            'period_info': {
                'from_time': current_week_start.isoformat(),
                'to_time': current_week_end.isoformat(),
                'total_users_analyzed': len(user_ids),
                'period_type': 'weekly'
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting weekly employee performance: {str(e)}"
        )

@router.get("/employee-performance/monthly")
async def get_monthly_employee_performance(
    limit: int = Query(5, ge=1, le=20, description="Number of top employees to return"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get top performing employees for the current month
    """
    try:
        # Calculate current month
        today = datetime.now()
        current_month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate next month start
        if today.month == 12:
            next_month_start = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month_start = today.replace(month=today.month + 1, day=1)
        
        current_month_end = next_month_start - timedelta(microseconds=1)
        
        dashboard_service = DashboardService(session)
        user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)
        
        employees = await dashboard_service.get_top_employee_performance(
            user_ids=user_ids,
            from_time=current_month_start,
            to_time=current_month_end,
            limit=limit
        )
        
        return {
            'employees': employees,
            'period_info': {
                'from_time': current_month_start.isoformat(),
                'to_time': current_month_end.isoformat(),
                'total_users_analyzed': len(user_ids),
                'period_type': 'monthly'
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting monthly employee performance: {str(e)}"
        )

@router.get("/task-work-chart")
async def get_task_work_chart(
    from_date: datetime = Query(..., description="Start date for the chart"),
    to_date: datetime = Query(..., description="End date for the chart"),
    period: str = Query('weekly', description="Time period grouping: weekly, monthly, quarterly"),
    timezone: str = Query('Asia/Bangkok', description="Timezone for date grouping (default: Asia/Bangkok for UTC+7)"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get task work chart data grouped by time periods
    
    Parameters:
    - from_date: Start date for the chart
    - to_date: End date for the chart
    - period: Time period grouping ('weekly', 'monthly', 'quarterly')
    
    Returns:
    - Task work chart data with counts by time period
    """
    try:
        if period not in ['weekly', 'monthly', 'quarterly']:
            raise HTTPException(
                status_code=400,
                detail="Period must be 'weekly', 'monthly', or 'quarterly'"
            )
        
        dashboard_service = DashboardService(session)
        user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)
        
        chart_data = await dashboard_service.get_task_work_chart_data(
            user_ids=user_ids,
            from_date=from_date,
            to_date=to_date,
            period=period,
            timezone=timezone
        )
        
        # Calculate summary statistics
        total_works = sum(item['total_works'] for item in chart_data)
        total_difficult = sum(item['difficult_works'] for item in chart_data)
        total_regular = sum(item['regular_works'] for item in chart_data)
        
        return {
            'chart_data': chart_data,
            'summary': {
                'total_works': total_works,
                'total_difficult_works': total_difficult,
                'total_regular_works': total_regular,
                'difficult_percentage': round((total_difficult / total_works * 100), 1) if total_works > 0 else 0
            },
            'period_info': {
                'from_date': from_date.isoformat(),
                'to_date': to_date.isoformat(),
                'period': period,
                'total_users': len(user_ids),
                'data_points': len(chart_data)
            }
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting task work chart data: {str(e)}"
        )

@router.get("/task-work-chart/weekly")
async def get_weekly_task_work_chart(
    weeks: int = Query(12, ge=1, le=52, description="Number of weeks to analyze (default: 12)"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get weekly task work chart data for the last N weeks
    """
    try:
        # Calculate date range for the last N weeks
        to_date = datetime.now()
        from_date = to_date - timedelta(weeks=weeks)
        
        dashboard_service = DashboardService(session)
        user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)
        
        chart_data = await dashboard_service.get_task_work_chart_data(
            user_ids=user_ids,
            from_date=from_date,
            to_date=to_date,
            period='weekly'
        )
        
        # Calculate summary statistics
        total_works = sum(item['total_works'] for item in chart_data)
        total_difficult = sum(item['difficult_works'] for item in chart_data)
        total_regular = sum(item['regular_works'] for item in chart_data)
        
        return {
            'chart_data': chart_data,
            'summary': {
                'total_works': total_works,
                'total_difficult_works': total_difficult,
                'total_regular_works': total_regular,
                'difficult_percentage': round((total_difficult / total_works * 100), 1) if total_works > 0 else 0,
                'average_works_per_week': round(total_works / len(chart_data), 1) if chart_data else 0
            },
            'period_info': {
                'from_date': from_date.isoformat(),
                'to_date': to_date.isoformat(),
                'period': 'weekly',
                'weeks_analyzed': weeks,
                'total_users': len(user_ids),
                'data_points': len(chart_data)
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting weekly task work chart data: {str(e)}"
        )

@router.get("/task-work-chart/monthly")
async def get_monthly_task_work_chart(
    months: int = Query(12, ge=1, le=24, description="Number of months to analyze (default: 12)"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get monthly task work chart data for the last N months
    """
    try:
        # Calculate date range for the last N months
        to_date = datetime.now()
        from_date = to_date - timedelta(days=months * 30)  # Approximate months
        
        dashboard_service = DashboardService(session)
        user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)
        
        chart_data = await dashboard_service.get_task_work_chart_data(
            user_ids=user_ids,
            from_date=from_date,
            to_date=to_date,
            period='monthly'
        )
        
        # Calculate summary statistics
        total_works = sum(item['total_works'] for item in chart_data)
        total_difficult = sum(item['difficult_works'] for item in chart_data)
        total_regular = sum(item['regular_works'] for item in chart_data)
        
        return {
            'chart_data': chart_data,
            'summary': {
                'total_works': total_works,
                'total_difficult_works': total_difficult,
                'total_regular_works': total_regular,
                'difficult_percentage': round((total_difficult / total_works * 100), 1) if total_works > 0 else 0,
                'average_works_per_month': round(total_works / len(chart_data), 1) if chart_data else 0
            },
            'period_info': {
                'from_date': from_date.isoformat(),
                'to_date': to_date.isoformat(),
                'period': 'monthly',
                'months_analyzed': months,
                'total_users': len(user_ids),
                'data_points': len(chart_data)
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting monthly task work chart data: {str(e)}"
        )

@router.get("/task-work-chart/quarterly")
async def get_quarterly_task_work_chart(
    quarters: int = Query(8, ge=1, le=16, description="Number of quarters to analyze (default: 8)"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get quarterly task work chart data for the last N quarters
    """
    try:
        # Calculate date range for the last N quarters
        to_date = datetime.now()
        from_date = to_date - timedelta(days=quarters * 90)  # Approximate quarters
        
        dashboard_service = DashboardService(session)
        user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)
        
        chart_data = await dashboard_service.get_task_work_chart_data(
            user_ids=user_ids,
            from_date=from_date,
            to_date=to_date,
            period='quarterly'
        )
        
        # Calculate summary statistics
        total_works = sum(item['total_works'] for item in chart_data)
        total_difficult = sum(item['difficult_works'] for item in chart_data)
        total_regular = sum(item['regular_works'] for item in chart_data)
        
        return {
            'chart_data': chart_data,
            'summary': {
                'total_works': total_works,
                'total_difficult_works': total_difficult,
                'total_regular_works': total_regular,
                'difficult_percentage': round((total_difficult / total_works * 100), 1) if total_works > 0 else 0,
                'average_works_per_quarter': round(total_works / len(chart_data), 1) if chart_data else 0
            },
            'period_info': {
                'from_date': from_date.isoformat(),
                'to_date': to_date.isoformat(),
                'period': 'quarterly',
                'quarters_analyzed': quarters,
                'total_users': len(user_ids),
                'data_points': len(chart_data)
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting quarterly task work chart data: {str(e)}"
        )

@router.get("/user-period-statistics")
async def get_user_period_statistics(
    from_date: datetime = Query(..., description="Start date for the statistics"),
    to_date: datetime = Query(..., description="End date for the statistics"),
    period: str = Query('daily', description="Time period grouping: daily, monthly, quarterly"),
    timezone: str = Query('Asia/Bangkok', description="Timezone for date grouping (default: Asia/Bangkok for UTC+7)"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get task work statistics grouped by user and time period
    
    Parameters:
    - from_date: Start date for the statistics
    - to_date: End date for the statistics
    - period: Time period grouping ('daily', 'monthly', 'quarterly')
    
    Returns:
    - Task work statistics grouped by user and time period
    """
    try:
        if period not in ['daily', 'monthly', 'quarterly']:
            raise HTTPException(
                status_code=400,
                detail="Period must be 'daily', 'monthly', or 'quarterly'"
            )
        
        dashboard_service = DashboardService(session)
        user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)
        
        user_stats = await dashboard_service.get_user_period_statistics(
            user_ids=user_ids,
            from_date=from_date,
            to_date=to_date,
            period=period,
            timezone=timezone
        )
        
        # Calculate overall summary statistics
        total_users = len(user_stats)
        total_works = sum(user['total_works'] for user in user_stats)
        total_difficult = sum(user['total_difficult_works'] for user in user_stats)
        total_regular = sum(user['total_regular_works'] for user in user_stats)
        
        return {
            'user_statistics': user_stats,
            'summary': {
                'total_users': total_users,
                'total_works': total_works,
                'total_difficult_works': total_difficult,
                'total_regular_works': total_regular,
                'difficult_percentage': round((total_difficult / total_works * 100), 1) if total_works > 0 else 0,
                'average_works_per_user': round(total_works / total_users, 1) if total_users > 0 else 0
            },
            'period_info': {
                'from_date': from_date.isoformat(),
                'to_date': to_date.isoformat(),
                'period': period,
                'total_users_analyzed': len(user_ids)
            }
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting user period statistics: {str(e)}"
        )

@router.get("/user-daily-statistics")
async def get_user_daily_statistics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze (default: 30)"),
    timezone: str = Query('Asia/Bangkok', description="Timezone for date grouping (default: Asia/Bangkok for UTC+7)"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get daily task work statistics for each user for the last N days
    """
    try:
        # Calculate date range for the last N days
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)
        
        dashboard_service = DashboardService(session)
        user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)
        
        user_stats = await dashboard_service.get_user_daily_statistics(
            user_ids=user_ids,
            from_date=from_date,
            to_date=to_date,
            timezone=timezone
        )
        
        # Calculate overall summary statistics
        total_users = len(user_stats)
        total_works = sum(user['total_works'] for user in user_stats)
        total_difficult = sum(user['total_difficult_works'] for user in user_stats)
        total_regular = sum(user['total_regular_works'] for user in user_stats)
        
        return {
            'user_statistics': user_stats,
            'summary': {
                'total_users': total_users,
                'total_works': total_works,
                'total_difficult_works': total_difficult,
                'total_regular_works': total_regular,
                'difficult_percentage': round((total_difficult / total_works * 100), 1) if total_works > 0 else 0,
                'average_works_per_user': round(total_works / total_users, 1) if total_users > 0 else 0,
                'average_works_per_day': round(total_works / days, 1) if days > 0 else 0
            },
            'period_info': {
                'from_date': from_date.isoformat(),
                'to_date': to_date.isoformat(),
                'period': 'daily',
                'days_analyzed': days,
                'total_users_analyzed': len(user_ids)
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting user daily statistics: {str(e)}"
        )

@router.get("/user-monthly-statistics")
async def get_user_monthly_statistics(
    months: int = Query(12, ge=1, le=24, description="Number of months to analyze (default: 12)"),
    timezone: str = Query('Asia/Bangkok', description="Timezone for date grouping (default: Asia/Bangkok for UTC+7)"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get monthly task work statistics for each user for the last N months
    """
    try:
        # Calculate date range for the last N months
        to_date = datetime.now()
        from_date = to_date - timedelta(days=months * 30)  # Approximate months
        
        dashboard_service = DashboardService(session)
        user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)
        
        user_stats = await dashboard_service.get_user_monthly_statistics(
            user_ids=user_ids,
            from_date=from_date,
            to_date=to_date,
            timezone=timezone
        )
        
        # Calculate overall summary statistics
        total_users = len(user_stats)
        total_works = sum(user['total_works'] for user in user_stats)
        total_difficult = sum(user['total_difficult_works'] for user in user_stats)
        total_regular = sum(user['total_regular_works'] for user in user_stats)
        
        return {
            'user_statistics': user_stats,
            'summary': {
                'total_users': total_users,
                'total_works': total_works,
                'total_difficult_works': total_difficult,
                'total_regular_works': total_regular,
                'difficult_percentage': round((total_difficult / total_works * 100), 1) if total_works > 0 else 0,
                'average_works_per_user': round(total_works / total_users, 1) if total_users > 0 else 0,
                'average_works_per_month': round(total_works / months, 1) if months > 0 else 0
            },
            'period_info': {
                'from_date': from_date.isoformat(),
                'to_date': to_date.isoformat(),
                'period': 'monthly',
                'months_analyzed': months,
                'total_users_analyzed': len(user_ids)
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting user monthly statistics: {str(e)}"
        )

@router.get("/user-quarterly-statistics")
async def get_user_quarterly_statistics(
    quarters: int = Query(8, ge=1, le=16, description="Number of quarters to analyze (default: 8)"),
    timezone: str = Query('Asia/Bangkok', description="Timezone for date grouping (default: Asia/Bangkok for UTC+7)"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get quarterly task work statistics for each user for the last N quarters
    """
    try:
        # Calculate date range for the last N quarters
        to_date = datetime.now()
        from_date = to_date - timedelta(days=quarters * 90)  # Approximate quarters
        
        dashboard_service = DashboardService(session)
        user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)
        
        user_stats = await dashboard_service.get_user_quarterly_statistics(
            user_ids=user_ids,
            from_date=from_date,
            to_date=to_date,
            timezone=timezone
        )
        
        # Calculate overall summary statistics
        total_users = len(user_stats)
        total_works = sum(user['total_works'] for user in user_stats)
        total_difficult = sum(user['total_difficult_works'] for user in user_stats)
        total_regular = sum(user['total_regular_works'] for user in user_stats)
        
        return {
            'user_statistics': user_stats,
            'summary': {
                'total_users': total_users,
                'total_works': total_works,
                'total_difficult_works': total_difficult,
                'total_regular_works': total_regular,
                'difficult_percentage': round((total_difficult / total_works * 100), 1) if total_works > 0 else 0,
                'average_works_per_user': round(total_works / total_users, 1) if total_users > 0 else 0,
                'average_works_per_quarter': round(total_works / quarters, 1) if quarters > 0 else 0
            },
            'period_info': {
                'from_date': from_date.isoformat(),
                'to_date': to_date.isoformat(),
                'period': 'quarterly',
                'quarters_analyzed': quarters,
                'total_users_analyzed': len(user_ids)
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting user quarterly statistics: {str(e)}"
        )

@router.get("/recent-task-work-activities")
async def get_recent_task_work_activities(
    limit: int = Query(10, ge=1, le=100, description="Number of recent task work activities to return"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get recent task work activities from current user and children users
    
    Parameters:
    - limit: Number of recent task work activities to return (default: 10, max: 100)
    
    Returns:
    - Recent task work activities
    """
    try:
        dashboard_service = DashboardService(session)
        user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)
        
        activities = await dashboard_service.get_recent_task_work_activities(
            user_ids=user_ids,
            limit=limit
        )
        
        return {
            'activities': activities,
            'period_info': {
                'total_users_analyzed': len(user_ids)
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting recent task work activities: {str(e)}"
        )

@router.get("/employee-performance/export")
async def export_employee_performance(
    from_time: datetime = Query(..., description="Start time for the period"),
    to_time: datetime = Query(..., description="End time for the period"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Export employee performance data to Excel file (no limit on number of users)
    
    Parameters:
    - from_time: Start time for the period
    - to_time: End time for the period
    
    Returns:
    - Excel file download URL with comprehensive employee performance data
    """
    try:
        dashboard_service = DashboardService(session)
        user_ids = await dashboard_service.get_user_hierarchy_ids(current_user.user_id)

        # Get all employee performance data without limit
        export_service = EmployeePerformanceExcelCreator(session)
        employees = await export_service.get_all_employee_performance(
            user_ids=user_ids,
            from_time=from_time,
            to_time=to_time
        )
        
        # Create period info for Excel
        period_info = {
            'from_time': from_time.isoformat(),
            'to_time': to_time.isoformat(),
            'total_users_analyzed': len(user_ids)
        }
        
        # Create Excel file
        download_url = await export_service.create_excel(employees, period_info)
        
        return {
            'download_url': download_url,
            'period_info': period_info,
            'total_employees_exported': len(employees)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting employee performance: {str(e)}"
        )
