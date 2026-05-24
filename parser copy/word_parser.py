"""
Word Parser Module

This module contains the WordParser class for parsing Word documents (.docx, .doc).
- .docx files: Uses langchain_community.document_loaders.Docx2txtLoader
- .doc files: Uses pyantiword (wrapper for antiword, lightweight)
"""

import logging
from pathlib import Path
from typing import Dict, Any, Union
from langchain_community.document_loaders import Docx2txtLoader
from pyantiword.antiword_wrapper import extract_text_with_antiword

logger = logging.getLogger(__name__)


class WordParser:
    """Parser for Word documents supporting both .docx and .doc formats."""
    
    def __init__(self):
        """Initialize the Word parser."""
        pass
    
    def parse_word(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse Word documents (.docx, .doc).
        - .docx files: Uses Docx2txtLoader (langchain)
        - .doc files: Uses pyantiword (wrapper for antiword)
        
        Args:
            file_path: Path to the Word document file
            
        Returns:
            Dictionary containing the parsed Word document information
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
            
            # Check file extension
            file_extension = file_path.suffix.lower()
            if file_extension not in ['.docx', '.doc']:
                return {
                    "success": False,
                    "error": f"Unsupported file type: {file_extension}. Only .docx and .doc files are supported.",
                    "content": "",
                    "summary": ""
                }
            
            # Handle .docx files (ZIP/XML format) using langchain
            if file_extension == '.docx':
                loader = Docx2txtLoader(str(file_path))
                documents = loader.load()
                
                if not documents:
                    return {
                        "success": False,
                        "error": "No content found in Word document",
                        "content": "",
                        "summary": ""
                    }
                
                # Extract content from documents
                content_parts = []
                for doc in documents:
                    if doc.page_content:
                        content_parts.append(doc.page_content)
                
                # Combine all content
                combined_content = '\n\n'.join(content_parts)
                parsed_with = "langchain_community_docx2txt"
                documents_count = len(documents)
            
            # Handle .doc files (binary format) using pyantiword
            else:  # file_extension == '.doc'
                content = extract_text_with_antiword(str(file_path))
                
                if not content or not content.strip():
                    return {
                        "success": False,
                        "error": "No content found in Word document",
                        "content": "",
                        "summary": ""
                    }
                
                combined_content = content.strip()
                parsed_with = "pyantiword"
                documents_count = 1

            result = {
                "success": True,
                "content": combined_content,
                "summary": '',  # This will be replaced by AI summary
                "file_type": file_extension,
                "file_size": len(combined_content),
                "documents_count": documents_count,
                "parsed_with": parsed_with
            }
            
            logger.info(f"Successfully parsed Word document: {file_path} (format: {file_extension}, parser: {parsed_with})")
            return result
            
        except Exception as e:
            logger.error(f"Error parsing Word document {file_path}: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": "",
                "summary": ""
            }
