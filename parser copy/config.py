"""
Configuration file for the FileParser client.
"""

import os
from typing import Dict, List, Optional

# Configuration settings for the parser
# Base URL for the API server
BASE_URL = os.getenv('PARSER_BASE_URL', 'https://4c1eb148e436.ngrok-free.app')

# Timeout settings
REQUEST_TIMEOUT = 30

# File paths
EXAMPLE_DATA_PATH = '../tests/'
TEST_DOCX = EXAMPLE_DATA_PATH + "omniparse/data/test.docx"
TEST_PDF = EXAMPLE_DATA_PATH + "omniparse/data/test.pdf"
TEST_VIDEO = EXAMPLE_DATA_PATH + "omniparse/data/test.mp4"
TEST_IMAGE = EXAMPLE_DATA_PATH + "omniparse/data/test.png"
TEST_EXCEL = EXAMPLE_DATA_PATH + "omniparse/data/test.xlsx"

# File type mappings
SUPPORTED_EXTENSIONS = {
    'documents': {
        'pdf': ['.pdf'],
        'word': ['.doc', '.docx'],
        'powerpoint': ['.ppt', '.pptx'],
        'excel': ['.xlsx', '.xls']
    },
    'images': {
        'image': ['.png', '.jpg', '.jpeg', '.tiff', '.webp']
    },
    'videos': {
        'video': ['.mp4', '.avi', '.mov', '.mkv']
    },
    'audio': {
        'audio': ['.mp3', '.wav', '.flac']
    }
}

# Image processing tasks
IMAGE_PROCESSING_TASKS = [
    'OCR',
    'Caption',
    'Object Detection',
    'Detailed Caption',
    'More Detailed Caption',
    'OCR with Region',
    'Dense Region Caption',
    'Region Proposal'
]

# API Endpoints
ENDPOINTS = {
    'documents': {
        'parse_document': '/parse_document',
        'parse_pdf': '/parse_document/pdf',
        'parse_powerpoint': '/parse_document/ppt',
        'parse_word': '/parse_document/docs',
        'parse_excel': '/parse_document/excel'
    },
    'image': {
        'parse_image': '/parse_image/image',
        'process_image': '/parse_image/process_image'
    },
    'video': {
        'parse_video': '/parse_video/video'
    },
    'audio': {
        'parse_audio': '/parse_audio/audio'
    },
    'website': {
        'parse_website': '/parse_website'
    }
}

# Logging configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Error messages
ERROR_MESSAGES = {
    'file_not_found': 'File not found: {file_path}',
    'connection_error': 'Cannot connect to API server: {base_url}',
    'http_error': 'HTTP error {status_code}: {message}',
    'timeout_error': 'Request timed out after {timeout} seconds',
    'invalid_file_type': 'Unsupported file type: {file_extension}',
    'invalid_task': 'Invalid image processing task: {task}'
}

# Retry configuration
RETRY_CONFIG = {
    'max_retries': 3,
    'retry_delay': 1,  # seconds
    'backoff_factor': 2
}

def get_base_url() -> str:
    """Get the base URL for API requests."""
    return BASE_URL

def get_timeout() -> int:
    """Get the request timeout in seconds."""
    return REQUEST_TIMEOUT

def get_supported_extensions() -> Dict[str, Dict[str, List[str]]]:
    """Get supported file extensions."""
    return SUPPORTED_EXTENSIONS

def get_image_tasks() -> List[str]:
    """Get available image processing tasks."""
    return IMAGE_PROCESSING_TASKS

def get_endpoints() -> Dict[str, Dict[str, str]]:
    """Get API endpoints."""
    return ENDPOINTS

def get_error_message(key: str, **kwargs) -> str:
    """Get formatted error message."""
    return ERROR_MESSAGES.get(key, 'Unknown error').format(**kwargs)

def get_retry_config() -> Dict[str, int]:
    """Get retry configuration."""
    return RETRY_CONFIG.copy() 