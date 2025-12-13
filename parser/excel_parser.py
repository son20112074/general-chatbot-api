"""
Excel Parser Module

This module contains the ExcelParser class for parsing Excel files (.xlsx, .xls)
using langchain_community.document_loaders.UnstructuredExcelLoader.
"""

from langchain_community.document_loaders import UnstructuredExcelLoader
from pathlib import Path
from typing import Dict, Any, Union, List
import logging

logger = logging.getLogger(__name__)


class ExcelParser:
    """Parser for Excel files using langchain_community UnstructuredExcelLoader."""
    
    def __init__(self):
        """Initialize the Excel parser."""
        pass
    
    def _check_dependencies(self):
        """Check if all required dependencies are available."""
        required_modules = [
            'langchain_community',
            'networkx',
            'pandas',
            'openpyxl',
            'unstructured'
        ]
        
        missing_modules = []
        for module in required_modules:
            try:
                __import__(module)
            except ImportError:
                missing_modules.append(module)
        
        if missing_modules:
            raise ImportError(f"Missing required modules: {', '.join(missing_modules)}. "
                            f"Please install dependencies using: pip install -r requirements.txt")
    
    def parse_excel(self, file_path: Union[str, Path], mode: str = "elements") -> List[Dict[str, Any]]:
        """
        Parse Excel files (.xlsx, .xls) using UnstructuredExcelLoader.
        
        Args:
            file_path: Path to the Excel file
            mode: Mode for parsing ("elements" or "single")
                  - "elements": Parse each sheet/element separately
                  - "single": Parse as a single document
                  
        Returns:
            List of dictionaries containing the parsed Excel information
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if not self._is_excel_file(file_path):
            raise ValueError(f"File is not a valid Excel file: {file_path}")
        
        try:
            logger.info(f"Parsing Excel file: {file_path}")
            
            # Check if required dependencies are available
            self._check_dependencies()
            
            # Use UnstructuredExcelLoader with specified mode
            loader = UnstructuredExcelLoader(str(file_path), mode=mode)
            docs = loader.load()
            
            # Convert documents to dictionary format
            parsed_data = []
            for i, doc in enumerate(docs):
                doc_data = {
                    "index": i,
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "source": str(file_path)
                }
                parsed_data.append(doc_data)
            
            logger.info(f"Successfully parsed Excel file: {file_path} - {len(parsed_data)} elements found")
            return parsed_data
            
        except ImportError as e:
            error_msg = f"Missing required dependency: {e}. Please install dependencies using: pip install -r requirements.txt"
            logger.error(error_msg)
            raise ImportError(error_msg)
        except Exception as e:
            logger.error(f"Error parsing Excel file {file_path}: {e}")
            raise
    
    def parse_excel_elements(self, file_path: Union[str, Path]) -> List[Dict[str, Any]]:
        """
        Parse Excel file in elements mode (each sheet/element separately).
        
        Args:
            file_path: Path to the Excel file
            
        Returns:
            List of dictionaries containing the parsed Excel elements
        """
        return self.parse_excel(file_path, mode="elements")
    
    def parse_excel_single(self, file_path: Union[str, Path]) -> List[Dict[str, Any]]:
        """
        Parse Excel file as a single document.
        
        Args:
            file_path: Path to the Excel file
            
        Returns:
            List containing a single dictionary with the parsed Excel content
        """
        return self.parse_excel(file_path, mode="single")
    
    def _is_excel_file(self, file_path: Path) -> bool:
        """
        Check if the file is a valid Excel file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if the file is an Excel file, False otherwise
        """
        excel_extensions = {'.xlsx', '.xls', '.xlsm', '.xlsb'}
        return file_path.suffix.lower() in excel_extensions
    
    def get_excel_info(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Get basic information about the Excel file without parsing content.
        
        Args:
            file_path: Path to the Excel file
            
        Returns:
            Dictionary containing basic file information
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if not self._is_excel_file(file_path):
            raise ValueError(f"File is not a valid Excel file: {file_path}")
        
        try:
            # Load the file to get metadata
            loader = UnstructuredExcelLoader(str(file_path), mode="elements")
            docs = loader.load()
            
            info = {
                "file_path": str(file_path),
                "file_size": file_path.stat().st_size,
                "file_extension": file_path.suffix.lower(),
                "total_elements": len(docs),
                "elements_info": []
            }
            
            # Extract information about each element
            for i, doc in enumerate(docs):
                element_info = {
                    "index": i,
                    "metadata": doc.metadata,
                    "content_length": len(doc.page_content)
                }
                info["elements_info"].append(element_info)
            
            return info
            
        except Exception as e:
            logger.error(f"Error getting Excel file info {file_path}: {e}")
            raise


# Example usage function
def example_usage():
    """Example of how to use the ExcelParser class."""
    parser = ExcelParser()
    
    # Example file path (replace with actual path)
    excel_file = "sixnations.xlsx"
    
    try:
        # Parse in elements mode (like your example)
        docs = parser.parse_excel_elements(excel_file)
        print(f"Parsed {len(docs)} elements from {excel_file}")
        
        # Print first element content
        if docs:
            print(f"First element content: {docs[0]['content'][:200]}...")
            print(f"First element metadata: {docs[0]['metadata']}")
        
        # Get file information
        info = parser.get_excel_info(excel_file)
        print(f"File info: {info}")
        
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    example_usage()
