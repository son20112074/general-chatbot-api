from typing import List, Dict, Any, Optional, TypeVar, Generic, Type
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import ARRAY, select, and_, or_, text, Table, insert, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.types import Integer
from datetime import datetime
from dateutil import parser as date_parser
from app.domain.models import User, Role as RoleModel, File as FileModel, Folder as FolderModel
from app.domain.models.file_topic import FileTopic
from app.domain.models.store_file import StoreFile
from app.utils.tree_builder import make_tree
from app.utils.helpers import build_file_item
from app.presentation.api.v1.schemas.file import FileListAllSchema
from app.core.config import settings

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
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_hierarchy_ids(self, current_user_id: int) -> List[int]:
        """Get all user IDs including current user and all children users based on role hierarchy"""
        # Get current user's role
        user_query = select(User).where(User.id == current_user_id)
        user_result = await self.db.execute(user_query)
        current_user = user_result.scalar_one_or_none()
        
        if not current_user:
            return [current_user_id]
        
        # Get all child role IDs based on the current user's role hierarchy
        child_roles_query = text("""
            SELECT r.id
            FROM roles r
            WHERE (r.parent_path ILIKE :exact_path
            OR r.parent_path ILIKE :anywhere_path)
            AND r.is_deleted = false
        """)
        
        child_roles_result = await self.db.execute(
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
        child_users_result = await self.db.execute(child_users_query)
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

        if "is_deleted" in table.c:
            query = query.where(or_(table.c.is_deleted == False, table.c.is_deleted == None))

        # Add user hierarchy filter if include_children is True and current_user_id is provided
        if current_user_id is not None:
            user_ids = await self.get_user_hierarchy_ids(current_user_id)
            print(f"User IDs: {user_ids}")
            if user_ids:
                query = query.where(table.c.created_by.in_(user_ids))
        print(f"Query: {query}")
        # Get total count
        count_query = select(text("COUNT(*)")).select_from(query.subquery())
        total = await self.db.scalar(count_query)

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
        result = await self.db.execute(query)
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

    async def _build_file_visibility_filter(
        self,
        user_id: int,
        user_role_id: int,
        effective_type: Optional[str] = None,
    ) -> List[Any]:
        """RBAC visibility conditions for file queries (mirrors list-all rules)."""
        if user_role_id == settings.ADMIN_ROLE_ID and effective_type != "private":
            return []

        child_roles_result = await self.db.execute(text("""
            SELECT id FROM roles
            WHERE (parent_path ILIKE :exact_path
            OR parent_path ILIKE :anywhere_path)
            AND is_deleted = false
        """), {
            "exact_path": f",{user_role_id},",
            "anywhere_path": f"%,{user_role_id},%",
        })
        child_role_ids = [row[0] for row in child_roles_result.fetchall()]

        return [
            or_(
                FileModel.type == "general",
                and_(
                    FileModel.type == "private",
                    FileModel.created_by == user_id,
                ),
                and_(
                    FileModel.type == "store",
                    FileModel.created_by == user_id,
                ),
                and_(
                    FileModel.type == "organization",
                    FileModel.role_id == user_role_id,
                    FileModel.created_by == user_id,
                ),
                and_(
                    FileModel.type == "organization",
                    FileModel.role_id.in_(child_role_ids),
                ) if child_role_ids else and_(False),
            )
        ]

    async def list_distinct_responsible_departments(
        self,
        user_id: int,
        user_role_id: int,
    ) -> List[str]:
        """Distinct department names from responsible_departments on visible files."""
        visibility_filter = await self._build_file_visibility_filter(user_id, user_role_id)
        base_cond = and_(
            or_(FileModel.is_deleted == False, FileModel.is_deleted == None),
            *visibility_filter,
        )
        dept_expr = func.unnest(FileModel.responsible_departments).label("department")
        query = (
            select(dept_expr)
            .select_from(FileModel)
            .where(base_cond)
            .where(FileModel.responsible_departments.isnot(None))
            .where(func.coalesce(func.array_length(FileModel.responsible_departments, 1), 0) > 0)
        )
        rows = (await self.db.execute(query)).all()

        seen: set[str] = set()
        departments: List[str] = []
        for row in rows:
            name = (row.department or "").strip()
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            departments.append(name)

        departments.sort(key=lambda x: x.casefold())
        return departments
    
    async def query_files(
        self,
        query_params: FileListAllSchema,
        user_id: int,
        user_role_id: int
    ):
        try:
            # ── Force type='store' when store_id is provided ─────────
            # When `store_id` is set, this is a "files-not-yet-in-this-store"
            # picker query: the type is implied by the resource being filtered.
            # Override any client-supplied `type`.
            effective_type = "store" if query_params.store_id is not None else query_params.type

            visibility_filter = await self._build_file_visibility_filter(
                user_id, user_role_id, effective_type
            )

            base_cond = and_(
                or_(FileModel.is_deleted == False, FileModel.is_deleted == None),
                *visibility_filter,
            )

            # Single query builder joined with User/Folder/Role so we can
            # filter and search across all of them in one pass. Reused for
            # both the page query and the count query to keep filters in sync.
            def _base():
                return (
                    select(FileModel, User.id.label("u_id"), User.full_name.label("u_name"))
                    .outerjoin(User, FileModel.created_by == User.id)
                    .outerjoin(FolderModel, FileModel.folder_id == FolderModel.id)
                    .outerjoin(RoleModel, FileModel.role_id == RoleModel.id)
                    .where(base_cond)
                )

            def _count_base():
                return (
                    select(func.count(FileModel.id))
                    .select_from(FileModel)
                    .outerjoin(User, FileModel.created_by == User.id)
                    .outerjoin(FolderModel, FileModel.folder_id == FolderModel.id)
                    .outerjoin(RoleModel, FileModel.role_id == RoleModel.id)
                    .where(base_cond)
                )

            query = _base()
            count_query = _count_base()

            # ── Subtree filter via node_path ─────────────────────────
            # node_path format: "type_<type>/role_<id>/.../user_<id>/folder_<id>/..."
            # To match a segment like `folder_4`, append "/" to node_path and
            # look for "/folder_4/" — this catches both tail and middle cases.
            if query_params.started_node is not None and query_params.type_node:
                segment = f"{query_params.type_node}_{query_params.started_node}"
                pattern = f"%/{segment}/%"
                node_match = func.concat(FileModel.node_path, "/").ilike(pattern)
                query = query.where(node_match)
                count_query = count_query.where(node_match)

            # ── type filter ──────────────────────────────────────────
            # `effective_type` is the client `type` unless `store_id` forced it
            # to "store" above.
            if effective_type:
                query = query.where(FileModel.type == effective_type)
                count_query = count_query.where(FileModel.type == effective_type)

            # ── ids filter ───────────────────────────────────────────
            # Restrict to a specific set of file IDs. Empty list returns
            # nothing (caller asked for an empty subset, not "no filter").
            if query_params.ids is not None:
                ids_cond = FileModel.id.in_(query_params.ids) if query_params.ids else FileModel.id.in_([-1])
                query = query.where(ids_cond)
                count_query = count_query.where(ids_cond)

            # ── departments filter (case-insensitive OR over array) ──
            # Matches files whose `responsible_departments` array contains
            # AT LEAST ONE element equal (case-insensitive) to any value in
            # the provided list. Empty list → no rows.
            if query_params.departments is not None:
                if not query_params.departments:
                    dep_cond = text("FALSE")
                else:
                    # Lowercase both sides; compare via array overlap on the
                    # lower(unnest) result.
                    lowered = [d.lower() for d in query_params.departments]
                    dep_cond = text(
                        "EXISTS (SELECT 1 FROM unnest(files.responsible_departments) AS d "
                        "WHERE lower(d) = ANY(:dept_lowered))"
                    ).bindparams(dept_lowered=lowered)
                query = query.where(dep_cond)
                count_query = count_query.where(dep_cond)

            # ── owner_name filter ────────────────────────────────────
            if query_params.owner_name:
                owner_cond = User.full_name.ilike(f"%{query_params.owner_name}%")
                query = query.where(owner_cond)
                count_query = count_query.where(owner_cond)

            # ── Free-text search across file/folder/owner/role names ──
            if query_params.search_text:
                like = f"%{query_params.search_text}%"
                search_cond = or_(
                    FileModel.name.ilike(like),
                    FolderModel.name.ilike(like),
                    FileModel.summary.ilike(like),
                    FileModel.content.ilike(like),
                    User.full_name.ilike(like),
                    RoleModel.name.ilike(like),
                )
                query = query.where(search_cond)
                count_query = count_query.where(search_cond)

            # ── is_processed filter ──────────────────────────────────
            if query_params.is_processed is not None:
                proc_cond = FileModel.is_processed == query_params.is_processed
                query = query.where(proc_cond)
                count_query = count_query.where(proc_cond)

            # ── topic_id exclude filter ──────────────────────────────
            # When topic_id is provided, exclude files already matched
            # (file_topics.is_matched = TRUE) into that topic. Used by
            # UI pickers to show only un-matched candidates.
            if query_params.topic_id is not None:
                matched_subq = (
                    select(FileTopic.file_id)
                    .where(
                        FileTopic.topic_id == query_params.topic_id,
                        FileTopic.is_matched == True,
                    )
                )
                topic_excl = FileModel.id.notin_(matched_subq)
                query = query.where(topic_excl)
                count_query = count_query.where(topic_excl)

            # ── store_id exclude filter ──────────────────────────────
            # When store_id is provided, exclude files already in that store
            # (store_files.is_deleted = FALSE). Used by UI pickers that add
            # files to a store. type='store' is forced above; non-admin
            # visibility further constrains to `created_by = current user`.
            if query_params.store_id is not None:
                in_store_subq = (
                    select(StoreFile.file_id)
                    .where(
                        StoreFile.store_id == query_params.store_id,
                        StoreFile.is_deleted == False,
                    )
                )
                store_excl = FileModel.id.notin_(in_store_subq)
                query = query.where(store_excl)
                count_query = count_query.where(store_excl)

            # ── Sort (supports multiple fields: "size,created_at") ──
            sort_field_map = {
                "created_at": FileModel.created_at,
                "size": FileModel.size,
            }
            sort_fields = [s.strip() for s in (query_params.sort_by or "created_at").split(",")]
            sort_orders = [s.strip() for s in (query_params.sort_order or "desc").split(",")]
            order_clauses = []
            for i, field_name in enumerate(sort_fields):
                col = sort_field_map.get(field_name, FileModel.created_at)
                direction = sort_orders[i] if i < len(sort_orders) else sort_orders[-1]
                order_clauses.append(col.asc() if direction == "asc" else col.desc())

            total = (await self.db.execute(count_query)).scalar_one()
            offset = (query_params.page - 1) * query_params.page_size
            query = query.order_by(*order_clauses).offset(offset).limit(query_params.page_size)

            items = [
                build_file_item(row[0], row.u_id, row.u_name)
                for row in (await self.db.execute(query)).all()
            ]
            return {"data": items, "total": total, "message": "succeeded"}
        except Exception as e:
            raise e
        
