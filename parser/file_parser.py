"""
File Parser Module

This module contains the FileParser class that combines all parsing capabilities
and automatically detects file types for parsing.
"""

import requests
from pathlib import Path
from typing import Dict, Any, Union
import logging

from .config import get_base_url, get_timeout
from .document_parser import DocumentParser
from .media_parser import MediaParser
from .website_parser import WebsiteParser
from .excel_parser import ExcelParser
from .word_parser import WordParser
from .pdf_parser import PDFParser
from .image_parser import ImageParser
from .summary_service import SummaryService
from app.core.config import settings

logger = logging.getLogger(__name__)


class FileParser:
    """Main parser class that combines all parsing capabilities."""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or get_base_url()
        self.session = requests.Session()
        self.document_parser = DocumentParser(base_url)
        self.media_parser = MediaParser(base_url)
        self.website_parser = WebsiteParser(base_url)
        self.excel_parser = ExcelParser()
        self.word_parser = WordParser()
        self.pdf_parser = PDFParser()
        self.image_parser = ImageParser()
        self.summary_service = SummaryService(api_url=settings.LLM_API)
    
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
    
    def _parse_text_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse text files (.txt, .dat, .csv) using simple UTF-8 file opening.
        
        Args:
            file_path: Path to the text file
            
        Returns:
            Dictionary containing the parsed text information
        """
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {file_path}",
                    "content": "",
                    "summary": ""
                }
            
            # Try different encodings
            encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
            content = None
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as file:
                        content = file.read()
                    logger.info(f"Successfully read file {file_path} with encoding: {encoding}")
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                return {
                    "success": False,
                    "error": f"Could not decode file with any of the attempted encodings: {encodings}",
                    "content": "",
                    "summary": ""
                }
                        
            result = {
                "success": True,
                "content": content,
                "summary": '',  # This will be replaced by AI summary
                "file_type": file_path.suffix.lower(),
                "file_size": len(content),
                "parsed_with": "utf8_file_reader"
            }
            return result
        except Exception as e:
            logger.error(f"Error parsing text file {file_path}: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": "",
                "summary": ""
            }

    def parse_file(self, file_path: Union[str, Path], extension: str = None) -> Dict[str, Any]:
        """
        Automatically detect file type and parse accordingly.
        
        Args:
            file_path: Path to the file to parse
            
        Returns:
            Dictionary containing the parsed file information
        """
        file_path = Path(file_path)
        file_extension = extension if extension else file_path.suffix.lower()
        
        # Text file types (simple UTF-8 reading)
        if file_extension in ['.txt', '.dat', '.csv']:
            return self._parse_text_file(file_path)
        elif file_extension in ['.pdf']:
            return self.pdf_parser.parse_pdf(file_path)
        # elif file_extension in ['.ppt', '.pptx']:
        #     result = self.document_parser.parse_powerpoint(file_path)
        elif file_extension in ['.doc', '.docx']:
            return self.word_parser.parse_word(file_path)
        elif file_extension in ['.xlsx', '.xls', '.xlsm', '.xlsb']:
            return self._parse_excel_with_langchain(file_path)
        elif file_extension in ['.png', '.jpg', '.jpeg', '.tiff', '.tif', '.webp', '.gif', '.bmp']:
            return self.image_parser.parse_image(file_path)
        else:
            return {
                "success": False,
                "error": f"Unsupported file type: {file_extension}",
                "content": "",
                "summary": ""
            }
    
    def _parse_excel_with_langchain(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse Excel files using the new langchain-based Excel parser.
        
        Args:
            file_path: Path to the Excel file
            
        Returns:
            Dictionary containing the parsed Excel information
        """
        try:
            # Use the new Excel parser with langchain
            parsed_elements = self.excel_parser.parse_excel_elements(file_path)
            
            # Convert to the expected format for consistency with other parsers
            if not parsed_elements:
                return {
                    "success": False,
                    "error": "No content found in Excel file",
                    "content": "",
                    "summary": ""
                }
            
            # Combine all elements into a single content string
            all_content = []
            for element in parsed_elements:
                if element.get('content'):
                    all_content.append(element['content'])
            
            combined_content = '\n\n'.join(all_content)
            
            
            return {
                "success": True,
                "content": combined_content,
                "summary": '',
                "elements_count": len(parsed_elements),
                "elements": parsed_elements,
                "file_type": "excel",
                "parsed_with": "langchain_community"
            }
            
        except Exception as e:
            logger.error(f"Error parsing Excel file {file_path} with langchain: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": "",
                "summary": ""
            }
