from datetime import datetime
from dateutil import parser as date_parser
from typing import Dict, Any, Type, TypeVar, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.domain.models.role import Role
from app.domain.models.folder import Folder
from app.domain.services.folder_service import compute_node_path


T = TypeVar('T')

def parse_datetime_safe(datetime_str: str) -> datetime:
    """
    Parse datetime string and convert to timezone-naive datetime.
    
    Args:
        datetime_str: Datetime string to parse
        
    Returns:
        timezone-naive datetime object
        
    Raises:
        ValueError: If datetime string is invalid
    """
    try:
        parsed_time = date_parser.parse(datetime_str)
        # Convert to timezone-naive datetime if it has timezone info
        if parsed_time.tzinfo is not None:
            return parsed_time.replace(tzinfo=None)
        else:
            return parsed_time
    except Exception as e:
        raise ValueError(f"Invalid datetime format: {str(e)}")

def dict_to_model(model_class: Type[T], data: Dict[str, Any]) -> T:
    """
    Convert a dictionary to a SQLAlchemy model instance.
    Only uses keys that correspond to columns in the model.
    """
    # Create model instance without data first
    model_instance = model_class()
    
    # Get list of column names in the model
    column_names = model_class.__table__.columns.keys()
    
    # Apply only the keys that exist in both the dict and as columns
    for key, value in data.items():
        if key in column_names:
            setattr(model_instance, key, value)
    
    return model_instance

def get_query_params(query_string: str) -> dict:
    """
    Parse a query string into a dictionary of parameters.
    
    Args:
        query_string (str): The query string to parse.
        
    Returns:
        dict: A dictionary of query parameters.
    """
    from urllib.parse import parse_qs

    return {k: v[0] for k, v in parse_qs(query_string).items()}


def validate_json_payload(payload: dict, required_fields: list) -> bool:
    """
    Validate that the JSON payload contains the required fields.
    
    Args:
        payload (dict): The JSON payload to validate.
        required_fields (list): A list of required field names.
        
    Returns:
        bool: True if all required fields are present, False otherwise.
    """
    return all(field in payload for field in required_fields)


def format_response(data: dict, status_code: int = 200) -> dict:
    """
    Format the response data for the API.
    
    Args:
        data (dict): The data to include in the response.
        status_code (int): The HTTP status code for the response.
        
    Returns:
        dict: A formatted response dictionary.
    """
    return {
        "status": "success" if status_code < 400 else "error",
        "data": data,
        "status_code": status_code,
    }


# ── File helpers ─────────────────────────────────────────────

def check_file_permission(file_obj, user_id: int, role_id: Optional[int]):
    """Check if user is file creator or admin. Raises PermissionError otherwise."""
    if file_obj.created_by != user_id and role_id != settings.ADMIN_ROLE_ID:
        raise PermissionError("Only the creator or admin can perform this action")


def _parse_store_id_from_node_path(node_path: Optional[str]) -> Optional[int]:
    """Extract `<id>` from a `store_<id>` segment in an existing node_path.

    Files of type='store' carry their store binding in node_path because there
    is no `files.store_id` column (file ↔ store is M-N via `store_files`).
    When recomputing node_path on a move/rename, we preserve the original
    store segment by parsing it back from the previous node_path.

    Returns None if no `store_<digits>` segment is found.
    """
    if not node_path:
        return None
    for seg in node_path.split('/'):
        if seg.startswith('store_'):
            try:
                return int(seg[len('store_'):])
            except ValueError:
                return None
    return None


async def compute_and_set_node_path(session: AsyncSession, file_obj):
    """Compute node_path from file's type, role, user, folder, store and set it.

    For type='store', the store_id is preserved by parsing the existing
    node_path (since there is no `files.store_id` column). Callers that
    create a brand-new store-type file must set node_path themselves before
    calling this helper, or the resulting path will lack the store segment.
    """
    role_parent_path = None
    folder_parent_path = None
    if file_obj.role_id:
        r = await session.execute(select(Role.parent_path).where(Role.id == file_obj.role_id))
        row = r.first()
        if row:
            role_parent_path = row[0]
    if file_obj.folder_id:
        r = await session.execute(select(Folder.parent_path).where(Folder.id == file_obj.folder_id))
        row = r.first()
        if row:
            folder_parent_path = row[0]

    store_id = None
    if file_obj.type == "store":
        store_id = _parse_store_id_from_node_path(file_obj.node_path)

    file_obj.node_path = compute_node_path(
        file_type=file_obj.type,
        role_id=file_obj.role_id,
        role_parent_path=role_parent_path,
        user_id=file_obj.created_by,
        folder_id=file_obj.folder_id,
        folder_parent_path=folder_parent_path,
        store_id=store_id,
    )


def build_file_item(f, u_id, u_name) -> dict:
    """Build a file list item dict from a File ORM object and owner info."""
    return {
        "id": f.id, "name": f.name, "size": f.size,
        "hash": f.hash, "path": f.path,
        "url": f.url,
        "extension": f.extension, "mime_type": f.mime_type,
        "node_path": f.node_path,
        "owner": {"id": u_id, "full_name": u_name} if u_id else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        "is_processed": f.is_processed,
        "processing_duration": f.processing_duration,
        "content": f.content,
        "summary": f.summary,
        "responsible_departments": f.responsible_departments,
        "responsible_departments_reasons": f.responsible_departments_reasons,
    }