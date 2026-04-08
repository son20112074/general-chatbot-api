
from fastapi import Request
from typing import Dict, Any, Type, TypeVar, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.domain.models.role import Role
from app.domain.models.folder import Folder
from app.domain.services.folder_service import compute_node_path


T = TypeVar('T')

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


async def compute_and_set_node_path(session: AsyncSession, file_obj):
    """Compute node_path from file's type, role, folder and set it on the object."""
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
    file_obj.node_path = compute_node_path(
        file_obj.type, file_obj.role_id, role_parent_path, file_obj.folder_id, folder_parent_path
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
    }