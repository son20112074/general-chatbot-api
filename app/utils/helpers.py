
from fastapi import Request
from typing import Dict, Any, Type, TypeVar


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