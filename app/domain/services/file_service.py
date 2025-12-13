from typing import List, Dict, Any, Optional, TypeVar, Generic, Type
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import ARRAY, select, and_, or_, text, Table, insert, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.types import Integer
from datetime import datetime
from dateutil import parser as date_parser
from app.domain.models import Task, User, Role, File, TaskWork
from app.utils.tree_builder import make_tree

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
    include_children: Optional[bool] = Field(False)  # New field to include child users' files

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

class FileQueryService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_hierarchy_ids(self, current_user_id: int) -> List[int]:
        """Get all user IDs including current user and all children users based on role hierarchy"""
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

    def _build_base_query(self, table: Table, query_input: QueryInput, current_user_id: Optional[int] = None) -> Select:
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

        # Add user hierarchy filter if include_children is True and current_user_id is provided
        if query_input.include_children and current_user_id is not None:
            # This will be handled in the main query method after getting user hierarchy
            pass

        # Add custom conditions using the centralized _build_conditions method
        if query_input.condition:
            conditions = self._build_conditions(table, query_input.condition)
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
                    # Convert datetime strings for date fields
                    if key in ['start_date', 'end_date', 'created_at', 'updated_at'] and isinstance(op_value, str):
                        try:
                            print(f"Converting date string: {op_value} for field: {key} with operator: {op}")
                            # Use dateutil parser for more robust parsing
                            dt = date_parser.parse(op_value)
                            
                            # Convert to timezone-naive datetime
                            if dt.tzinfo is not None:
                                op_value = dt.replace(tzinfo=None)
                            else:
                                op_value = dt
                            
                            print(f"Converted to datetime: {op_value} (type: {type(op_value)})")
                            
                            # Validate that we have a proper datetime object
                            if not isinstance(op_value, datetime):
                                print(f"WARNING: op_value is not a datetime object after conversion: {type(op_value)}")
                                # Try to create a datetime object from the string
                                try:
                                    op_value = datetime.fromisoformat(str(op_value))
                                except:
                                    print(f"Failed to create datetime from {op_value}")
                            
                        except Exception as e:
                            print(f"Date conversion failed for {op_value}: {e}")
                            # If parsing fails, keep the original value
                            pass
                    
                    # Debug: Print the operator and value before creating condition
                    print(f"Creating condition: {key} {op} {op_value} (type: {type(op_value)})")
                    
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
        query_input: QueryInput,
        current_user_id: Optional[int] = None
    ) -> CursorPaginationResult:
        """Execute query with cursor-based pagination"""
        # Build base query
        query = self._build_base_query(table, query_input, current_user_id)

        # Add user hierarchy filter if include_children is True and current_user_id is provided
        if current_user_id is not None:
            user_ids = await self.get_user_hierarchy_ids(current_user_id)
            print(f"User IDs: {user_ids}")
            if user_ids:
                query = query.where(table.c.created_by.in_(user_ids))
        print(f"Query: {query}")
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

    async def query_user_files_with_children(
        self,
        table: Table,
        query_input: QueryInput,
        current_user_id: int
    ) -> CursorPaginationResult:
        """Query files from current user and all their child users"""
        # Set include_children to True to get files from all users in hierarchy
        query_input.include_children = True
        
        # Execute the query with user hierarchy
        return await self.query_with_cursor(table, query_input, current_user_id)
