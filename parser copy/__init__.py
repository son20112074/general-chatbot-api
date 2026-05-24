"""
File Parser Package

A comprehensive Python package for parsing various file types using API endpoints.
This package provides parsers for documents, media, and websites.
"""

from .file_parser import FileParser
from .document_parser import DocumentParser
from .media_parser import MediaParser
from .website_parser import WebsiteParser
from .excel_parser import ExcelParser
from .config import get_base_url, get_timeout, get_supported_extensions

__version__ = "1.0.0"
__author__ = "File Parser Team"

__all__ = [
    'FileParser',
    'DocumentParser', 
    'MediaParser',
    'WebsiteParser',
    'ExcelParser',
    'get_base_url',
    'get_timeout',
    'get_supported_extensions',
    'get_image_tasks',
    'get_endpoints'
]
