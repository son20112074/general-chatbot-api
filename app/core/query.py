from typing import List, Dict, Any, Optional, TypeVar, Generic, Type
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import ARRAY, select, and_, or_, text, Table, insert, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.types import Integer
from datetime import datetime
from app.domain.models import Task, User, Role, File, TaskWork, PersonalTaskStatus
from app.utils.tree_builder import make_tree
from sqlalchemy.orm import selectinload

class QueryInput(BaseModel):
    table_name: str = Field(None)
    ids: List[int] = Field([])
    fields: List[str] = Field([])
    condition: Dict[str, Any] = Field({})
    page: int = Field(1)
    page_size: int = Field(10)
    cursor: Optional[str] = Field(None)
    sort_by: Optional[str] = Field(None)
    sort_order: str = Field("asc")
    search_text: Optional[str] = Field(None)
    search_fields: List[str] = Field([])
    start_date: Optional[str] = Field(None)
    end_date: Optional[str] = Field(None)
    include_children: bool = Field(False)

class InsertInput(BaseModel):
    table_name: str = Field(...)
    data: Dict[str, Any] = Field(...)

class UpsertInput(BaseModel):
    table_name: str = Field(...)
    data: Dict[str, Any] = Field(...)
    condition: Dict[str, Any] = Field(...)

class CursorPaginationResult(BaseModel):
    items: List[Dict[str, Any]]
    next_cursor: Optional[str]
    has_more: bool
    total: int

    model_config = ConfigDict(arbitrary_types_allowed=True)

class InsertResult(BaseModel):
    id: Any
    success: bool
    message: str

class UpsertResult(BaseModel):
    id: Any
    success: bool
    message: str
    operation: str  # "insert" or "update"

class DeleteInput(BaseModel):
    table_name: str = Field(...)
    ids: List[str] = Field([])
    condition: Dict[str, Any] = Field({})

class DeleteResult(BaseModel):
    success: bool
    message: str
    deleted_count: int

class TimeRange(BaseModel):
    field: str
    from_time: datetime
    to_time: datetime

class TreeQueryInput(BaseModel):
    table_name: str = Field(None)
    ids: List[str] = Field([])
    fields: List[str] = Field([])
    condition: Dict[str, Any] = Field({})
    search_text: Optional[str] = Field(None)
    search_fields: List[str] = Field([])
    page: int = Field(1)
    page_size: int = Field(10)
    time_range: Optional[TimeRange] = Field(None)

class TreeQueryResult(BaseModel):
    data: List[Dict[str, Any]]
    total: int

class CommonQuery:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _build_base_query(self, table: Table, query_input: QueryInput) -> Select:
        """Build the base query with conditions"""
        query = select(table)

        # Add field selection if specified
        if query_input.fields:
            query = select(*[table.c[field] for field in query_input.fields])

        # Add ID filter if specified
        if query_input.ids:
            query = query.where(table.c.id.in_(query_input.ids))

        # Add search condition
        if query_input.search_text and query_input.search_fields:
            search_conditions = []
            for field in query_input.search_fields:
                if field in table.c:
                    search_conditions.append(table.c[field].like(f"%{query_input.search_text}%"))
            if search_conditions:
                query = query.where(or_(*search_conditions))

        # Add custom conditions
        if query_input.condition:
            conditions = []
            for key, value in query_input.condition.items():
                if isinstance(value, list):
                    # Handle array conditions - check if array field contains any of the values
                    if key in table.c and hasattr(table.c[key], 'any'):
                        # For array fields, check if any of the values in the list are contained in the array
                        array_conditions = []
                        for item in value:
                            array_conditions.append(table.c[key].any(item))
                        if array_conditions:
                            conditions.append(or_(*array_conditions))
                    else:
                        # For non-array fields, use IN operator
                        conditions.append(table.c[key].in_(value))
                elif isinstance(value, dict):
                    # Handle operators like $gt, $lt, etc.
                    for op, op_value in value.items():
                        if op == "$gt":
                            conditions.append(table.c[key] > op_value)
                        elif op == "$lt":
                            conditions.append(table.c[key] < op_value)
                        elif op == "$gte":
                            conditions.append(table.c[key] >= op_value)
                        elif op == "$lte":
                            conditions.append(table.c[key] <= op_value)
                        elif op == "$in":
                            conditions.append(table.c[key].in_(op_value))
                        elif op == "$like":
                            conditions.append(table.c[key].like(f"%{op_value}%"))
                        elif op == "$contains":
                            # Handle array contains condition
                            if hasattr(table.c[key], 'any'):
                                # For array fields, check if the field contains the value
                                conditions.append(table.c[key].any(op_value))
                            else:
                                # For non-array fields, use LIKE
                                conditions.append(table.c[key].like(f"%{op_value}%"))
                        elif op == "$overlaps":
                            # Handle array overlap condition (PostgreSQL specific)
                            if hasattr(table.c[key], 'overlap'):
                                conditions.append(table.c[key].overlap(op_value))
                            else:
                                # Fallback for non-array fields
                                conditions.append(table.c[key].in_(op_value))
                else:
                    # Handle boolean values explicitly
                    if isinstance(value, bool):
                        conditions.append(table.c[key].is_(value))
                    else:
                        # Handle date fields - convert string dates to datetime objects
                        if key in ['start_date', 'end_date', 'created_at', 'updated_at'] and isinstance(value, str):
                            try:
                                print(f"Converting date string: {value} for field: {key}")
                                # Handle different date formats
                                if value.endswith('Z'):
                                    # ISO format with Z timezone
                                    dt = datetime.fromisoformat(value[:-1] + '+00:00')
                                elif '+' in value or '-' in value[-6:]:
                                    # ISO format with timezone
                                    dt = datetime.fromisoformat(value)
                                else:
                                    # Simple ISO format without timezone
                                    dt = datetime.fromisoformat(value)
                                
                                value = dt.replace(tzinfo=None)
                                print(f"Converted to datetime: {value}")
                                
                                # Validate that we have a proper datetime object
                                if not isinstance(value, datetime):
                                    print(f"Warning: Value is not a datetime object after conversion: {type(value)}")
                                    value = dt  # Use the original parsed datetime
                                    
                            except ValueError as e:
                                print(f"Date conversion failed: {e}")
                                # If parsing fails, keep the original value
                                pass
                        
                        # Cast string IDs to integers if the column is integer type
                        if key == 'id' and isinstance(table.c[key].type, Integer):
                            try:
                                value = int(value)
                            except (ValueError, TypeError):
                                pass
                        conditions.append(table.c[key] == value)
            
            if conditions:
                query = query.where(and_(*conditions))

        # Add sorting
        if query_input.sort_by:
            sort_column = table.c[query_input.sort_by]
            if query_input.sort_order.lower() == "desc":
                query = query.order_by(sort_column.desc())
            else:
                query = query.order_by(sort_column.asc())

        return query

    def _build_conditions(self, table: Table, condition: Dict[str, Any]) -> List[Any]:
        """Build SQLAlchemy conditions from dictionary"""
        conditions = []
        for key, value in condition.items():
            if isinstance(value, list):
                # Handle array conditions - check if array field contains any of the values
                if key in table.c and hasattr(table.c[key], 'any'):
                    # For array fields, check if any of the values in the list are contained in the array
                    array_conditions = []
                    for item in value:
                        array_conditions.append(table.c[key].any(item))
                    if array_conditions:
                        conditions.append(or_(*array_conditions))
                else:
                    # For non-array fields, use IN operator
                    conditions.append(table.c[key].in_(value))
            elif isinstance(value, dict):
                for op, op_value in value.items():
                    if op == "$gt":
                        conditions.append(table.c[key] > op_value)
                    elif op == "$lt":
                        conditions.append(table.c[key] < op_value)
                    elif op == "$gte":
                        conditions.append(table.c[key] >= op_value)
                    elif op == "$lte":
                        conditions.append(table.c[key] <= op_value)
                    elif op == "$in":
                        conditions.append(table.c[key].in_(op_value))
                    elif op == "$like":
                        conditions.append(table.c[key].like(f"%{op_value}%"))
                    elif op == "$contains":
                        # Handle array contains condition
                        if hasattr(table.c[key], 'any'):
                            # For array fields, check if the field contains the value
                            conditions.append(table.c[key].any(op_value))
                        else:
                            # For non-array fields, use LIKE
                            conditions.append(table.c[key].like(f"%{op_value}%"))
                    elif op == "$overlaps":
                        # Handle array overlap condition (PostgreSQL specific)
                        if hasattr(table.c[key], 'overlap'):
                            conditions.append(table.c[key].overlap(op_value))
                        else:
                            # Fallback for non-array fields
                            conditions.append(table.c[key].in_(op_value))
            else:
                # Handle boolean values explicitly
                if isinstance(value, bool):
                    conditions.append(table.c[key].is_(value))
                else:
                    # Handle date fields - convert string dates to datetime objects
                    if key in ['start_date', 'end_date', 'created_at', 'updated_at'] and isinstance(value, str):
                        try:
                            print(f"Converting date string: {value} for field: {key}")
                            # Handle different date formats
                            if value.endswith('Z'):
                                # ISO format with Z timezone
                                dt = datetime.fromisoformat(value[:-1] + '+00:00')
                            elif '+' in value or '-' in value[-6:]:
                                # ISO format with timezone
                                dt = datetime.fromisoformat(value)
                            else:
                                # Simple ISO format without timezone
                                dt = datetime.fromisoformat(value)
                            
                            value = dt.replace(tzinfo=None)
                            print(f"Converted to datetime: {value}")
                            
                            # Validate that we have a proper datetime object
                            if not isinstance(value, datetime):
                                print(f"Warning: Value is not a datetime object after conversion: {type(value)}")
                                value = dt  # Use the original parsed datetime
                                
                        except ValueError as e:
                            print(f"Date conversion failed: {e}")
                            # If parsing fails, keep the original value
                            pass
                    
                    # Cast string IDs to integers if the column is integer type
                    if key == 'id' and isinstance(table.c[key].type, Integer):
                        try:
                            value = int(value)
                        except (ValueError, TypeError):
                            pass
                    conditions.append(table.c[key] == value)
        return conditions

    def _row_to_dict(self, row: Any) -> Dict[str, Any]:
        """Convert SQLAlchemy Row to dictionary"""
        return dict(row._mapping)

    async def query_with_cursor(
        self,
        table: Table,
        query_input: QueryInput
    ) -> CursorPaginationResult:
        """Execute query with cursor-based pagination"""
        # Build base query
        query = self._build_base_query(table, query_input)

        # Get total count
        count_query = select(text("COUNT(*)")).select_from(query.subquery())
        total = await self.session.scalar(count_query)

        # Add cursor-based pagination
        if query_input.cursor:
            # Decode cursor (assuming it's base64 encoded)
            import base64
            cursor_data = base64.b64decode(query_input.cursor).decode()
            cursor_value = cursor_data.split("|")[0]
            
            # Add cursor condition
            if query_input.sort_order.lower() == "desc":
                query = query.where(table.c[query_input.sort_by or "id"] < cursor_value)
            else:
                query = query.where(table.c[query_input.sort_by or "id"] > cursor_value)

        # Add limit
        query = query.offset((query_input.page - 1) * query_input.page_size).limit(query_input.page_size) 

        # Execute query
        result = await self.session.execute(query)
        items = result.all()

        # Check if there are more results
        has_more = len(items) > query_input.page_size
        if has_more:
            items = items[:-1]  # Remove the extra item

        # Generate next cursor
        next_cursor = None
        if items and has_more:
            last_item = items[-1]
            cursor_value = last_item[query_input.sort_by or "id"]
            cursor_data = f"{cursor_value}|{query_input.sort_by or 'id'}"
            next_cursor = base64.b64encode(cursor_data.encode()).decode()
        # Convert rows to dictionaries
        items_dict = [self._row_to_dict(item) for item in items]

        return CursorPaginationResult(
            items=items_dict,
            next_cursor=next_cursor,
            has_more=has_more,
            total=total
        )

    async def insert(self, table: Table, insert_input: InsertInput) -> InsertResult:
        """Insert data into a table"""
        try:
            # Get the appropriate model class based on table name
            model_map = {
                'tasks': Task,
                'users': User,
                'roles': Role,
                'files': File
            }

            model_class = model_map.get(table.name)
            if not model_class:
                return InsertResult(
                    id=None,
                    success=False,
                    message=f"No model found for table {table.name}"
                )

            # Convert date strings to datetime objects
            data = insert_input.data.copy()
            for field in ['start_date', 'end_date', 'created_at', 'updated_at']:
                if field in data and isinstance(data[field], str):
                    try:
                        # Parse the ISO format string and convert to naive datetime
                        dt = datetime.fromisoformat(data[field].replace('Z', '+00:00'))
                        data[field] = dt.replace(tzinfo=None)
                    except ValueError:
                        data[field] = None

            # Create model instance
            model_instance = model_class(**data)
            try:
                # Add to session
                self.session.add(model_instance)
                
                # Commit the transaction
                await self.session.commit()
            except Exception as e:
                raise e
            return InsertResult(
                id=model_instance.id,
                success=True,
                message="Record inserted successfully"
            )
        except Exception as e:
            # Rollback in case of error
            await self.session.rollback()
            return InsertResult(
                id=None,
                success=False,
                message=f"Error inserting record: {str(e)}"
            )

    async def upsert(self, table: Table, upsert_input: UpsertInput) -> UpsertResult:
        """Insert or update data based on condition"""
        try:
            # Convert date strings to datetime objects
            data = upsert_input.data.copy()
            for field in ['start_date', 'end_date', 'created_at', 'updated_at']:
                if field in data and isinstance(data[field], str):
                    try:
                        # Parse the ISO format string and convert to naive datetime
                        dt = datetime.fromisoformat(data[field].replace('Z', '+00:00'))
                        data[field] = dt.replace(tzinfo=None)
                    except ValueError:
                        data[field] = None

            # Build conditions
            conditions = self._build_conditions(table, upsert_input.condition)
            
            # First try to update
            update_stmt = (
                update(table)
                .where(and_(*conditions))
                .values(**data)
                .returning(table.c.id)
            )
            
            result = await self.session.execute(update_stmt)
            updated_id = result.scalar()
            
            if updated_id:
                # Update successful
                await self.session.commit()
                return UpsertResult(
                    id=updated_id,
                    success=True,
                    message="Record updated successfully",
                    operation="update"
                )
            
            # If no update occurred, try insert
            insert_stmt = (
                insert(table)
                .values(**data)
                .returning(table.c.id)
            )
            
            result = await self.session.execute(insert_stmt)
            inserted_id = result.scalar()
            
            # Commit the transaction
            await self.session.commit()
            
            return UpsertResult(
                id=inserted_id,
                success=True,
                message="Record inserted successfully",
                operation="insert"
            )
        except Exception as e:
            # Rollback in case of error
            await self.session.rollback()
            return UpsertResult(
                id=None,
                success=False,
                message=f"Error in upsert operation: {str(e)}",
                operation="error"
            )

    async def delete(self, table: Table, delete_input: DeleteInput) -> DeleteResult:
        """Delete records from a table based on IDs and conditions"""
        try:
            # Build base query
            query = table.delete()

            # Add ID filter if specified
            if delete_input.ids:
                # Cast string IDs to integers if the id column is integer type
                if isinstance(table.c.id.type, Integer):
                    casted_ids = [int(id) for id in delete_input.ids]
                    query = query.where(table.c.id.in_(casted_ids))
                else:
                    query = query.where(table.c.id.in_(delete_input.ids))

            # Add custom conditions
            if delete_input.condition:
                conditions = self._build_conditions(table, delete_input.condition)
                if conditions:
                    query = query.where(and_(*conditions))

            # Execute delete
            result = await self.session.execute(query)
            deleted_count = result.rowcount
            
            # Commit the transaction
            await self.session.commit()
            
            return DeleteResult(
                success=True,
                message=f"Successfully deleted {deleted_count} records",
                deleted_count=deleted_count
            )
        except Exception as e:
            # Rollback in case of error
            await self.session.rollback()
            return DeleteResult(
                success=False,
                message=f"Error deleting records: {str(e)}",
                deleted_count=0
            )

    async def get_valid_users(self, role_id: int) -> List[int]:
        """Get list of valid user IDs based on role hierarchy"""
        query = """
            SELECT u.id 
            FROM users u 
            LEFT JOIN roles r ON u.role_id = r.id 
            WHERE r.parent_path ILIKE :path1 
            OR r.parent_path ILIKE :path2
        """
        path1 = f",{role_id},"
        path2 = f"%,{role_id},%"

        result = await self.session.execute(
            text(query),
            {"path1": path1, "path2": path2}
        )
        return [row[0] for row in result]

    async def query_tree(self, query_input: TreeQueryInput, user: Dict[str, Any]) -> any:
        """Query data with tree structure"""
        try:
            # Get the appropriate model class based on table name
            model_map = {
                'tasks': Task,
                'users': User,
                'roles': Role,
                'files': File
            }

            model_class = model_map.get(query_input.table_name)
            if not model_class:
                raise ValueError(f"No model found for table {query_input.table_name}")

            # Build base query
            query = select(model_class)

            # Add ID filter if specified
            if query_input.ids:
                query = query.where(model_class.id.in_(query_input.ids))

            # Add search condition
            if query_input.search_text and query_input.search_fields:
                search_conditions = []
                for field in query_input.search_fields:
                    if hasattr(model_class, field):
                        search_conditions.append(
                            getattr(model_class, field).ilike(f"%{query_input.search_text}%")
                        )
                if search_conditions:
                    query = query.where(or_(*search_conditions))

            # Add custom conditions
            if query_input.condition:
                conditions = []
                for key, value in query_input.condition.items():
                    if hasattr(model_class, key):
                        if isinstance(value, bool):
                            conditions.append(getattr(model_class, key).is_(value))
                        else:
                            conditions.append(getattr(model_class, key) == value)
                if conditions:
                    query = query.where(and_(*conditions))

            # Add time range condition
            if query_input.time_range:
                if hasattr(model_class, query_input.time_range.field):
                    field = getattr(model_class, query_input.time_range.field)
                    query = query.where(
                        and_(
                            field >= query_input.time_range.from_time,
                            field <= query_input.time_range.to_time
                        )
                    )

            # Add user access control
            if user.role_id != 1:  # Assuming 1 is admin role
                valid_users = await self.get_valid_users(user.role_id)
                valid_users.append(user.user_id)
                query = query.where(model_class.created_by.in_(valid_users))

            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total = await self.session.scalar(count_query)

            # Add pagination
            query = query.order_by(model_class.id.desc())
            query = query.offset((query_input.page - 1) * query_input.page_size)
            query = query.limit(query_input.page_size)

            # Execute query
            result = await self.session.execute(query)
            items = [row.to_dict() for row in result.scalars().all()]
            # Remove SQLAlchemy internal attributes
            # Convert to tree structure
            tree_data = make_tree(items)
            return {
                "data":tree_data,
                "total":total
            }

        except Exception as e:
            print(f"Error in query_tree: {str(e)}")
            raise e 

    async def query_user_tasks(self, user_id: int, query_input: QueryInput, role_id: int) -> CursorPaginationResult:
        """Query tasks that are either created by the user, assigned to the user, or are children of those tasks"""
        try:
            # Build base query using Task model with creator relationship
            query = select(Task).options(
                selectinload(Task.creator)
            )

            # Add field selection if specified
            if query_input.fields:
                # For field selection, we need to handle it differently with relationships
                # For now, we'll use the full model and filter fields later
                pass

            # Get subordinate user IDs (users under the current user in role hierarchy)
            subordinate_user_ids = await self.get_valid_users(role_id)
            
            # Build conditions for user's tasks
            user_conditions = [
                Task.created_by == user_id,  # Tasks created by user
                Task.assigned_to.any(user_id)   # Tasks assigned to user (check if user_id is in assigned_to array)
            ]
            
            # Add conditions for tasks created by subordinate users
            if subordinate_user_ids:
                user_conditions.extend([
                    Task.created_by.in_(subordinate_user_ids),  # Tasks created by subordinate users
                ])

            # Get IDs of tasks that match user conditions
            user_tasks_query = select(Task.id).where(or_(*user_conditions))
            result = await self.session.execute(user_tasks_query)
            user_task_ids = [row[0] for row in result]
            
            # Build parent path conditions for child tasks
            parent_path_conditions = []
            for task_id in user_task_ids:
                # Match tasks where parent_path contains the task_id
                # This will match both direct children and deeper descendants
                parent_path_conditions.append(Task.parent_path.like(f"%,{task_id},%"))

            # Get all tasks that are in the hierarchy of user's tasks
            hierarchy_task_ids = []
            if len(parent_path_conditions) > 0:
                hierarchy_query = select(Task.id).where(or_(*parent_path_conditions))
                result = await self.session.execute(hierarchy_query)
                hierarchy_task_ids = [row[0] for row in result]
                
            print(f"Hierarchy task IDs: {hierarchy_task_ids}")
            # Combine all task IDs
            all_task_ids = set(user_task_ids + hierarchy_task_ids)

            # Build final conditions
            conditions = [
                Task.id.in_(all_task_ids)  # All tasks in the hierarchy
            ]

            # Add search condition
            if query_input.search_text and query_input.search_fields:
                search_conditions = []
                for field in query_input.search_fields:
                    if hasattr(Task, field):
                        search_conditions.append(getattr(Task, field).like(f"%{query_input.search_text}%"))
                if search_conditions:
                    conditions.append(or_(*search_conditions))

            # Add custom conditions
            if query_input.condition:
                print(f"Processing custom conditions: {query_input.condition}")
                custom_conditions = []
                for key, value in query_input.condition.items():
                    if hasattr(Task, key):
                        if isinstance(value, bool):
                            custom_conditions.append(getattr(Task, key).is_(value))
                        else:
                            custom_conditions.append(getattr(Task, key) == value)
                print(f"Built custom conditions: {custom_conditions}")
                if custom_conditions:
                    conditions.extend(custom_conditions)

            # Apply all conditions
            if conditions:
                query = query.where(and_(*conditions))

            if query_input.start_date:
                # Convert string date to datetime object
                try:
                    start_date_str = query_input.start_date
                    if start_date_str.endswith('Z'):
                        start_date_dt = datetime.fromisoformat(start_date_str[:-1] + '+00:00')
                    elif '+' in start_date_str or '-' in start_date_str[-6:]:
                        start_date_dt = datetime.fromisoformat(start_date_str)
                    else:
                        start_date_dt = datetime.fromisoformat(start_date_str)
                    start_date_dt = start_date_dt.replace(tzinfo=None)
                    
                    query = query.where(
                        or_(
                            Task.start_date <= start_date_dt,
                            Task.start_date.is_(None)
                        )
                    )
                except ValueError as e:
                    print(f"Error converting start_date: {e}")
                    # Skip this filter if conversion fails
                    pass
                    
            if query_input.end_date:
                # Convert string date to datetime object
                try:
                    end_date_str = query_input.end_date
                    if end_date_str.endswith('Z'):
                        end_date_dt = datetime.fromisoformat(end_date_str[:-1] + '+00:00')
                    elif '+' in end_date_str or '-' in end_date_str[-6:]:
                        end_date_dt = datetime.fromisoformat(end_date_str)
                    else:
                        end_date_dt = datetime.fromisoformat(end_date_str)
                    end_date_dt = end_date_dt.replace(tzinfo=None)
                    
                    query = query.where(
                        or_(
                            Task.end_date >= end_date_dt,
                            Task.end_date.is_(None)
                        )
                    )
                except ValueError as e:
                    print(f"Error converting end_date: {e}")
                    # Skip this filter if conversion fails
                    pass

            # Add sorting
            if query_input.sort_by and hasattr(Task, query_input.sort_by):
                sort_column = getattr(Task, query_input.sort_by)
                if query_input.sort_order.lower() == "desc":
                    query = query.order_by(sort_column.desc())
                else:
                    query = query.order_by(sort_column.asc())

            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total = await self.session.scalar(count_query)

            # Add pagination
            query = query.offset((query_input.page - 1) * query_input.page_size)
            query = query.limit(query_input.page_size)

            # Execute query
            result = await self.session.execute(query)
            tasks = result.scalars().all()
            
            # Convert tasks to dictionaries with creator information
            items_dict = []
            for task in tasks:
                task_dict = task.to_dict()
                
                # Add creator information using relationship
                if task.creator:
                    task_dict['creator'] = {
                        'id': task.creator.id,
                        'full_name': task.creator.full_name,
                        'account_name': task.creator.account_name,
                        'email': task.creator.email,
                        'role_id': task.creator.role_id
                    }
                else:
                    task_dict['creator'] = None
                
                items_dict.append(task_dict)

            # Calculate if there are more results
            has_more = total > query_input.page * query_input.page_size

            return {
                "data": make_tree(items_dict),
                "total": total,
                "page": query_input.page,
                "page_size": query_input.page_size,
                "has_more": has_more
            }

        except Exception as e:
            # Rollback in case of error
            await self.session.rollback()
            raise e

    async def query_assigned_tasks_by_date(self, user_id: int, start_date: datetime, end_date: datetime, query_input: QueryInput) -> CursorPaginationResult:
        """Query tasks assigned to user within date range or with no end date"""
        try:
            # Get the tasks table
            table = Task.__table__

            # Build base query
            query = select(table)

            # Add field selection if specified
            if query_input.fields:
                query = select(*[table.c[field] for field in query_input.fields])

            # Build date range conditions
            date_conditions = [
                # Tasks that fall within the date range
                and_(
                    table.c.start_date >= start_date,
                    table.c.end_date <= end_date
                ),
                # Tasks that have no end date
                table.c.end_date.is_(None)
            ]

            # Build conditions for assigned tasks
            conditions = [
                table.c.assigned_to.any(user_id),  # Tasks assigned to user (check if user_id is in assigned_to array)
                or_(*date_conditions)  # Date range conditions
            ]

            # Add search condition
            if query_input.search_text and query_input.search_fields:
                search_conditions = []
                for field in query_input.search_fields:
                    if field in table.c:
                        search_conditions.append(table.c[field].like(f"%{query_input.search_text}%"))
                if search_conditions:
                    conditions.append(or_(*search_conditions))

            # Add custom conditions
            if query_input.condition:
                custom_conditions = self._build_conditions(table, query_input.condition)
                if custom_conditions:
                    conditions.extend(custom_conditions)

            # Apply all conditions
            if conditions:
                query = query.where(and_(*conditions))

            # Add sorting
            if query_input.sort_by:
                sort_column = table.c[query_input.sort_by]
                if query_input.sort_order.lower() == "desc":
                    query = query.order_by(sort_column.desc())
                else:
                    query = query.order_by(sort_column.asc())

            # Get total count
            count_query = select(text("COUNT(*)")).select_from(query.subquery())
            total = await self.session.scalar(count_query)

            # Add limit
            query = query.limit(query_input.page_size + 1)  # Get one extra to check if there are more results

            # Execute query
            result = await self.session.execute(query)
            items = result.all()
            
            # Convert rows to dictionaries
            items_dict = [dict(row._mapping) for row in items]

            return {
                "data": items_dict,
                "total": total
            }

        except Exception as e:
            # Rollback in case of error
            await self.session.rollback()
            raise e 

    async def query_tasks_by_date(
        self,
        user_id: int,
        date: datetime,
        query_input: QueryInput
    ) -> CursorPaginationResult:
        """
        Query tasks assigned to a user for a specific date, including both periodic and ad-hoc tasks that are not completed.
        
        Args:
            user_id: The ID of the user to query tasks for
            date: The specific date to query tasks for
            query_input: Query parameters for pagination, sorting, and filtering
            
        Returns:
            CursorPaginationResult containing the tasks and pagination info
        """
        try:
            print(f"Querying tasks for user_id: {user_id}, date: {date}")
            
            # Convert timezone-aware datetime to naive datetime
            if date.tzinfo is not None:
                date = date.replace(tzinfo=None)
            
            # Start with base query with creator information
            query = select(Task, User).join(
                User, Task.created_by == User.id
            )
            
            # Join with personal_task_status table
            query = query.outerjoin(
                PersonalTaskStatus, 
                and_(
                    Task.id == PersonalTaskStatus.task_id,
                    PersonalTaskStatus.user_id == user_id
                )
            )
            
            if 'status' in query_input.condition:
                user_condition = and_(
                    Task.assigned_to.any(user_id),  # Check if user_id is in assigned_to array
                    or_(
                        PersonalTaskStatus.status == query_input.condition['status'],
                        and_(
                            PersonalTaskStatus.status.is_(None),
                            query_input.condition['status'] == 'new'
                        )
                    )
                )
            else:
                # Add conditions for tasks assigned to user
                user_condition = and_(
                    Task.assigned_to.any(user_id),  # Check if user_id is in assigned_to array
                    or_(
                        PersonalTaskStatus.status != "completed",
                        PersonalTaskStatus.status.is_(None)
                    )
                )
                
            query = query.where(user_condition)
            # print(f"User condition: {user_condition}")
            
            # Add date conditions for both periodic and ad-hoc tasks
            date_condition = or_(
                # For periodic tasks: check if the date falls within the task's schedule
                and_(
                    Task.type == 'periodic',
                    or_(
                        # Case 1: Both start_date and end_date are set
                        and_(
                            Task.start_date.isnot(None),
                            Task.end_date.isnot(None),
                            Task.start_date <= date.replace(hour=23, minute=59, second=59, microsecond=999999),
                            Task.end_date >= date.replace(hour=0, minute=0, second=0, microsecond=0)
                        ),
                        # Case 2: Only start_date is set (no end date)
                        and_(
                            Task.start_date.isnot(None),
                            Task.end_date.is_(None),
                            Task.start_date <= date.replace(hour=23, minute=59, second=59, microsecond=999999)
                        ),
                        # Case 3: Only end_date is set (no start date)
                        and_(
                            Task.start_date.is_(None),
                            Task.end_date.isnot(None),
                            Task.end_date >= date.replace(hour=0, minute=0, second=0, microsecond=0)
                        ),
                        # Case 4: Neither start_date nor end_date is set (always valid)
                        and_(
                            Task.start_date.is_(None),
                            Task.end_date.is_(None)
                        )
                    )
                ),
                # For ad-hoc tasks: check if the task is due on the specific date
                and_(
                    Task.type == 'sudden',
                    or_(
                        # Case 1: start_date is set
                        and_(
                            Task.start_date.isnot(None),
                            func.date(Task.start_date) == func.date(date.replace(hour=23, minute=59, second=59, microsecond=999999))
                        ),
                        # Case 2: start_date is null (always valid)
                        Task.start_date.is_(None)
                    )
                )
            )
            query = query.where(date_condition)
            # print(f"Date condition: {date_condition}")
            
            # Add search conditions if provided
            if query_input.search_text and query_input.search_fields:
                search_conditions = []
                for field in query_input.search_fields:
                    if hasattr(Task, field):
                        search_conditions.append(
                            getattr(Task, field).ilike(f"%{query_input.search_text}%")
                        )
                if search_conditions:
                    search_condition = or_(*search_conditions)
                    query = query.where(search_condition)
                    # print(f"Search condition: {search_condition}")
            
            # Add custom conditions if provided (excluding status as it's already handled above)
            if query_input.condition:
                for field, value in query_input.condition.items():
                    if field != 'status' and hasattr(Task, field):  # Skip status field
                        custom_condition = getattr(Task, field) == value
                        query = query.where(custom_condition)
                        # print(f"Custom condition for {field}: {custom_condition}")
            
            # Add sorting
            if query_input.sort_by and hasattr(Task, query_input.sort_by):
                sort_column = getattr(Task, query_input.sort_by)
                if query_input.sort_order == "desc":
                    sort_column = sort_column.desc()
                query = query.order_by(sort_column)
                # print(f"Sorting by: {sort_column}")
            
            # Execute query
            # print(f"Final SQL query: {query}")
            result = await self.session.execute(query)
            rows = result.all()
            print(f"Found {len(rows)} tasks")
            print(f"Query condition: {query_input.condition}")
            print(f"User condition: {user_condition}")
            print(f"Final SQL: {query.compile(compile_kwargs={'literal_binds': True})}")
            
            # Convert to dictionaries with creator information
            task_dicts = []
            for row in rows:
                task_dict = row[0].to_dict()
                creator_dict = row[1].to_dict()
                task_dict['creator'] = creator_dict
                task_dicts.append(task_dict)
            
            # Apply pagination
            total = len(task_dicts)
            has_more = total > query_input.page * query_input.page_size
            
            if query_input.page_size:
                start = (query_input.page - 1) * query_input.page_size
                end = start + query_input.page_size
                task_dicts = task_dicts[start:end]
            
            # Generate next cursor if there are more results
            next_cursor = None
            if has_more and task_dicts:
                last_item = task_dicts[-1]
                cursor_value = str(last_item.get('id', ''))
                next_cursor = cursor_value
            
            return CursorPaginationResult(
                items=task_dicts,
                total=total,
                page=query_input.page,
                page_size=query_input.page_size,
                next_cursor=next_cursor,
                has_more=has_more
            )
            
        except Exception as e:
            print(f"Error in query_tasks_by_date: {str(e)}")
            raise Exception(f"Error querying tasks by date: {str(e)}") 

    async def create_task_work(self, data: dict, user_id: int) -> dict:
        """Create a new task work"""
        try:
            # Add created_by
            data['created_by'] = user_id
            
            # Create model instance
            task_work = TaskWork(**data)
            self.session.add(task_work)
            await self.session.commit()
            await self.session.refresh(task_work)
            
            return task_work.to_dict()
        except Exception as e:
            await self.session.rollback()
            raise Exception(f"Error creating task work: {str(e)}")

    async def get_task_work(self, task_work_id: int) -> Optional[dict]:
        """Get a task work by ID"""
        try:
            result = await self.session.execute(
                select(TaskWork).where(TaskWork.id == task_work_id)
            )
            task_work = result.scalar_one_or_none()
            return task_work.to_dict() if task_work else None
        except Exception as e:
            raise Exception(f"Error getting task work: {str(e)}")

    async def update_task_work(self, task_work_id: int, data: dict) -> Optional[dict]:
        """Update a task work"""
        try:
            # Get the task work
            result = await self.session.execute(
                select(TaskWork).where(TaskWork.id == task_work_id)
            )
            task_work = result.scalar_one_or_none()
            
            if not task_work:
                return None
                
            # Update fields
            for key, value in data.items():
                setattr(task_work, key, value)
            
            await self.session.commit()
            await self.session.refresh(task_work)
            
            return task_work.to_dict()
        except Exception as e:
            await self.session.rollback()
            raise Exception(f"Error updating task work: {str(e)}")

    async def delete_task_work(self, task_work_id: int) -> bool:
        """Delete a task work"""
        try:
            result = await self.session.execute(
                select(TaskWork).where(TaskWork.id == task_work_id)
            )
            task_work = result.scalar_one_or_none()
            
            if not task_work:
                return False
                
            await self.session.delete(task_work)
            await self.session.commit()
            
            return True
        except Exception as e:
            await self.session.rollback()
            raise Exception(f"Error deleting task work: {str(e)}")

    async def list_task_works(
        self,
        task_id: Optional[int] = None,
        user_id: Optional[int] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        search: Optional[str] = None,
        ids: Optional[List[int]] = None,
        page: int = 1,
        page_size: int = 10
    ) -> dict:
        """List task works with optional filters"""
        try:
            # Import User model
            from app.domain.models.user import User
            
            # Build base query with join to Task and User
            query = select(TaskWork, Task, User).join(
                Task, TaskWork.task_id == Task.id, isouter=True
            ).join(
                User, TaskWork.created_by == User.id, isouter=True
            )
            
            # Add filters
            conditions = []
            if task_id is not None:
                conditions.append(TaskWork.task_id == task_id)
            if user_id is not None:
                conditions.append(TaskWork.created_by == user_id)
            
            # Add IDs filter
            if ids is not None and len(ids) > 0:
                conditions.append(TaskWork.id.in_(ids))
            
            # Add date range filters
            if from_date is not None:
                # Convert to naive datetime if timezone-aware
                if from_date.tzinfo is not None:
                    from_date = from_date.replace(tzinfo=None)
                conditions.append(TaskWork.created_at >= from_date)
            
            if to_date is not None:
                # Convert to naive datetime if timezone-aware
                if to_date.tzinfo is not None:
                    to_date = to_date.replace(tzinfo=None)
                # Set time to end of day for to_date
                to_date = to_date.replace(hour=23, minute=59, second=59, microsecond=999999)
                conditions.append(TaskWork.created_at <= to_date)
            
            # Add search condition
            if search:
                search_conditions = [
                    TaskWork.title.ilike(f"%{search}%"),
                    TaskWork.description.ilike(f"%{search}%"),
                    TaskWork.content.ilike(f"%{search}%")
                ]
                conditions.append(or_(*search_conditions))
                
            if conditions:
                query = query.where(and_(*conditions))
            
            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total = await self.session.scalar(count_query)
            
            # Add pagination
            query = query.order_by(TaskWork.created_at.desc())
            query = query.offset((page - 1) * page_size)
            query = query.limit(page_size)
            
            # Execute query
            result = await self.session.execute(query)
            rows = result.all()
            
            # Process results to include task work, task, and creator information
            items = []
            for row in rows:
                task_work_dict = row[0].to_dict()
                if row[1]:  # If task exists
                    task_work_dict['task'] = row[1].to_dict()
                else:
                    task_work_dict['task'] = None
                
                if row[2]:  # If creator exists
                    task_work_dict['creator'] = {
                        'id': row[2].id,
                        'full_name': row[2].full_name,
                        'account_name': row[2].account_name,
                        'email': row[2].email
                    }
                else:
                    task_work_dict['creator'] = None
                    
                items.append(task_work_dict)
            
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size
            }
        except Exception as e:
            raise Exception(f"Error listing task works: {str(e)}")

    async def create_task(self, data: dict, user_id: int) -> dict:
        """Create a new task"""
        try:
            # Add created_by
            data['created_by'] = user_id
            
            # Ensure assigned_to is a list
            if 'assigned_to' not in data or data['assigned_to'] is None:
                data['assigned_to'] = []
            
            # Ensure file_list is a list
            if 'file_list' not in data or data['file_list'] is None:
                data['file_list'] = []
            
            # Ensure file_name_list is a list
            if 'file_name_list' not in data or data['file_name_list'] is None:
                data['file_name_list'] = []
            
            # Create model instance
            task = Task(**data)
            self.session.add(task)
            await self.session.commit()
            await self.session.refresh(task)
            
            return task.to_dict()
        except Exception as e:
            await self.session.rollback()
            raise Exception(f"Error creating task: {str(e)}")

    async def get_task(self, task_id: int) -> Optional[dict]:
        """Get a task by ID"""
        try:
            result = await self.session.execute(
                select(Task).where(Task.id == task_id)
            )
            task = result.scalar_one_or_none()
            return task.to_dict() if task else None
        except Exception as e:
            raise Exception(f"Error getting task: {str(e)}")

    async def update_task(self, task_id: int, data: dict) -> Optional[dict]:
        """Update a task"""
        try:
            # Get the task
            result = await self.session.execute(
                select(Task).where(Task.id == task_id)
            )
            task = result.scalar_one_or_none()
            
            if not task:
                return None
            
            # Ensure assigned_to is a list if provided
            if 'assigned_to' in data and data['assigned_to'] is None:
                data['assigned_to'] = []
            
            # Ensure file_list is a list if provided
            if 'file_list' in data and data['file_list'] is None:
                data['file_list'] = []
            
            # Ensure file_name_list is a list if provided
            if 'file_name_list' in data and data['file_name_list'] is None:
                data['file_name_list'] = []
                
            # Update fields
            for key, value in data.items():
                setattr(task, key, value)
            
            await self.session.commit()
            await self.session.refresh(task)
            
            return task.to_dict()
        except Exception as e:
            await self.session.rollback()
            raise Exception(f"Error updating task: {str(e)}")

    async def count_task_works_by_tasks(self, task_ids: List[int]) -> dict:
        """Count task works for a list of task IDs"""
        try:
            # Build query to count task works for each task ID
            query = select(
                TaskWork.task_id,
                func.count(TaskWork.id).label('work_count')
            ).where(
                TaskWork.task_id.in_(task_ids)
            ).group_by(
                TaskWork.task_id
            )
            
            # Execute query
            result = await self.session.execute(query)
            rows = result.all()
            
            # Convert results to dictionary
            counts = {row[0]: row[1] for row in rows}
            
            # Add zero counts for tasks with no works
            for task_id in task_ids:
                if task_id not in counts:
                    counts[task_id] = 0
            
            return {
                "counts": counts,
                "total_tasks": len(task_ids),
                "total_works": sum(counts.values())
            }
        except Exception as e:
            raise Exception(f"Error counting task works: {str(e)}")

    async def insert_personal_task_status(self, task_id: int, user_id: int, status: str = "new") -> Optional[dict]:
        """Insert or update personal task status for a user"""
        try:
            # Check if record already exists
            result = await self.session.execute(
                select(PersonalTaskStatus).where(
                    and_(
                        PersonalTaskStatus.task_id == task_id,
                        PersonalTaskStatus.user_id == user_id
                    )
                )
            )
            existing_record = result.scalar_one_or_none()
            
            if existing_record:
                # Update existing record
                existing_record.status = status
                existing_record.updated_at = datetime.utcnow()
                await self.session.commit()
                await self.session.refresh(existing_record)
                return existing_record.to_dict()
            else:
                # Create new record
                personal_status = PersonalTaskStatus(
                    task_id=task_id,
                    user_id=user_id,
                    status=status,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                self.session.add(personal_status)
                await self.session.commit()
                await self.session.refresh(personal_status)
                return personal_status.to_dict()
                
        except Exception as e:
            await self.session.rollback()
            raise Exception(f"Error inserting personal task status: {str(e)}")

    async def get_personal_task_statuses(self, task_id: int) -> List[dict]:
        """Get all personal task statuses for a specific task"""
        try:
            result = await self.session.execute(
                select(PersonalTaskStatus).where(
                    PersonalTaskStatus.task_id == task_id
                )
            )
            records = result.scalars().all()
            return [record.to_dict() for record in records]
        except Exception as e:
            raise Exception(f"Error getting personal task statuses: {str(e)}")

    async def should_update_task_status(self, task_id: int, target_status: str) -> bool:
        """Check if task status should be updated based on all assigned users' personal statuses"""
        try:
            # Get the task to see all assigned users
            task = await self.get_task(task_id)
            if not task:
                return False
            
            assigned_user_ids = task.get("assigned_to", [])
            if not assigned_user_ids:
                return False
            
            # Get all personal task statuses for this task
            personal_statuses = await self.get_personal_task_statuses(task_id)
            
            # Create a map of user_id to status
            user_status_map = {ps["user_id"]: ps["status"] for ps in personal_statuses}
            
            # Check if all assigned users have the target status
            for user_id in assigned_user_ids:
                user_status = user_status_map.get(user_id, "new")  # Default to "new" if no record exists
                if user_status != target_status:
                    return False
            
            return True
        except Exception as e:
            raise Exception(f"Error checking task status update condition: {str(e)}")

    async def debug_personal_task_status(self, task_id: int, user_id: int) -> dict:
        """Debug method to check personal task status data"""
        try:
            # Get task info
            task = await self.get_task(task_id)
            
            # Get all personal statuses for this task
            personal_statuses = await self.get_personal_task_statuses(task_id)
            
            # Get specific user status
            user_status = None
            for status in personal_statuses:
                if status["user_id"] == user_id:
                    user_status = status
                    break
            
            return {
                "task": task,
                "all_personal_statuses": personal_statuses,
                "user_personal_status": user_status,
                "user_id": user_id,
                "task_id": task_id
            }
        except Exception as e:
            raise Exception(f"Error in debug: {str(e)}") 