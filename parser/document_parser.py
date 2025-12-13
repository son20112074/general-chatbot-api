"""
Document Parser Module

This module contains the DocumentParser class for parsing various document types
(PDF, Word, PowerPoint) using the API endpoints.
"""

import requests
from pathlib import Path
from typing import Dict, Any, Union
import logging
from .config import get_base_url, get_timeout

logger = logging.getLogger(__name__)


class DocumentParser:
    """Client for parsing various document types using the API endpoints."""
    
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or get_base_url()).rstrip('/')
        self.session = requests.Session()
    
    def _upload_file(self, endpoint: str, file_path: Union[str, Path], field_name: str) -> Dict[str, Any]:
        """Helper method to upload files to endpoints."""
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            with open(file_path, 'rb') as file:
                files = {field_name: file}
                response = self.session.post(endpoint, files=files, timeout=get_timeout())
                response.raise_for_status()
                return response.json()
        except KeyboardInterrupt:
            logger.info(f"Upload interrupted by user for file: {file_path}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Error uploading file {file_path}: {e}")
            raise
    
    def parse_document(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse any document (PDF, PowerPoint, or Word).
        
        Args:
            file_path: Path to the document file
            
        Returns:
            Dictionary containing the parsed document information
        """
        endpoint = f"{self.base_url}/parse_document"
        return self._upload_file(endpoint, file_path, "file")
    
    def parse_pdf(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse PDF documents specifically.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary containing the parsed PDF information
        """
        endpoint = f"{self.base_url}/parse_document/pdf"
        return self._upload_file(endpoint, file_path, "file")
    
    def parse_powerpoint(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse PowerPoint presentations.
        
        Args:
            file_path: Path to the PowerPoint file
            
        Returns:
            Dictionary containing the parsed PowerPoint information
        """
        endpoint = f"{self.base_url}/parse_document/ppt"
        return self._upload_file(endpoint, file_path, "file")
    
    def parse_word(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse Word documents.
        
        Args:
            file_path: Path to the Word document file
            
        Returns:
            Dictionary containing the parsed Word document information
        """
        endpoint = f"{self.base_url}/parse_document/docs"
        return self._upload_file(endpoint, file_path, "file")
    
    def parse_excel(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse Excel files (.xlsx, .xls).
        
        Args:
            file_path: Path to the Excel file
            
        Returns:
            Dictionary containing the parsed Excel information
        """
        endpoint = f"{self.base_url}/parse_document/excel"
        return self._upload_file(endpoint, file_path, "file")
