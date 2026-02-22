"""
PDF Parser Module

This module contains the PDFParser class for parsing PDF documents.
- Text-based PDFs: Uses pypdf to extract text directly
- Image-based PDFs: Uses Tesseract OCR to perform OCR on PDF pages
"""

import logging
from pathlib import Path
from typing import Dict, Any, Union
import os

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    import pytesseract
    TesseractOCR = True
except ImportError as e:
    TesseractOCR = False
    import logging
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning(f"pytesseract import failed: {e}. Please install it: pip install pytesseract")

try:
    import pdf2image
except ImportError:
    pdf2image = None

logger = logging.getLogger(__name__)


class PDFParser:
    """Parser for PDF documents supporting both text-based and image-based PDFs."""
    
    def __init__(self):
        """Initialize the PDF parser."""
        self._ocr_initialized = False
    
    def _init_ocr(self):
        """Initialize Tesseract OCR for image-based PDF processing (lazy initialization)."""
        if self._ocr_initialized:
            return
        
        if TesseractOCR:
            try:
                # Try to find Tesseract executable if not in PATH
                try:
                    pytesseract.get_tesseract_version()
                    logger.info("Tesseract OCR initialized successfully")
                except Exception:
                    # Try common Windows installation paths
                    common_paths = [
                        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                        r'C:\Users\{}\AppData\Local\Tesseract-OCR\tesseract.exe'.format(os.getenv('USERNAME', '')),
                    ]
                    for path in common_paths:
                        if os.path.exists(path):
                            pytesseract.pytesseract.tesseract_cmd = path
                            pytesseract.get_tesseract_version()  # Verify it works
                            logger.info(f"Found and initialized Tesseract at: {path}")
                            break
                    else:
                        raise Exception("Tesseract not found in PATH or common installation locations")
                self._ocr_initialized = True
            except Exception as e:
                logger.warning(
                    f"Failed to initialize Tesseract OCR: {e}. "
                    "Please ensure Tesseract OCR is installed on your system. "
                    "For Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki "
                    "For Linux: sudo apt-get install tesseract-ocr tesseract-ocr-vie"
                )
                self._ocr_initialized = True  # Mark as initialized even if failed to avoid retrying
        else:
            logger.warning("pytesseract not installed. OCR functionality will be limited.")
            self._ocr_initialized = True  # Mark as initialized even if failed to avoid retrying
    
    def _is_image_based_pdf(self, file_path: Union[str, Path]) -> bool:
        """
        Check if PDF is image-based (scanned) or text-based.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            True if PDF is image-based, False if text-based
        """
        if PdfReader is None:
            logger.warning("pypdf not available, assuming image-based PDF")
            return True
        
        try:
            file_path = Path(file_path)
            reader = PdfReader(str(file_path))
            
            # Check first few pages for text content
            text_content = ""
            pages_to_check = min(3, len(reader.pages))
            
            for i in range(pages_to_check):
                try:
                    page = reader.pages[i]
                    text = page.extract_text()
                    if text:
                        text_content += text.strip()
                except Exception as e:
                    logger.debug(f"Error extracting text from page {i}: {e}")
                    continue
            
            # If we have substantial text content, it's likely text-based
            # Threshold: if we have more than 50 characters, consider it text-based
            if len(text_content) > 50:
                logger.info(f"PDF appears to be text-based (found {len(text_content)} characters)")
                return False
            else:
                logger.info("PDF appears to be image-based (little or no text found)")
                return True
                
        except Exception as e:
            logger.warning(f"Error checking PDF type: {e}. Assuming image-based PDF.")
            return True
    
    def _extract_text_from_pdf(self, file_path: Union[str, Path]) -> str:
        """
        Extract text from text-based PDF using pypdf.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Extracted text content
        """
        if PdfReader is None:
            raise ImportError("pypdf is required for text-based PDF extraction")
        
        file_path = Path(file_path)
        reader = PdfReader(str(file_path))
        
        text_parts = []
        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text()
                if text:
                    text_parts.append(text.strip())
            except Exception as e:
                logger.warning(f"Error extracting text from page {i+1}: {e}")
                continue
        
        return '\n\n'.join(text_parts)
    
    def _extract_text_from_image_pdf(self, file_path: Union[str, Path]) -> str:
        """
        Extract text from image-based PDF using OCR.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Extracted text content from OCR
        """
        if pdf2image is None:
            raise ImportError("pdf2image is required for image-based PDF extraction")
        
        if not TesseractOCR:
            raise ImportError("pytesseract is required for OCR functionality. Install it: pip install pytesseract")
        
        file_path = Path(file_path)
        
        # Convert PDF pages to images
        try:
            images = pdf2image.convert_from_path(str(file_path))
        except Exception as e:
            raise Exception(f"Failed to convert PDF to images: {e}")
        
        text_parts = []
        
        for i, image in enumerate(images):
            try:
                # Try to set Tesseract path if not already set
                try:
                    pytesseract.get_tesseract_version()
                except Exception:
                    # Try common Windows installation paths
                    common_paths = [
                        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                        r'C:\Users\{}\AppData\Local\Tesseract-OCR\tesseract.exe'.format(os.getenv('USERNAME', '')),
                    ]
                    for path in common_paths:
                        if os.path.exists(path):
                            pytesseract.pytesseract.tesseract_cmd = path
                            break
                    else:
                        raise Exception(
                            "Tesseract OCR is not installed or not in PATH. "
                            "Please install Tesseract OCR from https://github.com/UB-Mannheim/tesseract/wiki"
                        )
                
                # Convert to RGB if necessary (Tesseract works best with RGB)
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Perform OCR on each page using Tesseract with Vietnamese language support
                # lang='vie' for Vietnamese, 'eng' for English, 'vie+eng' for both
                result = pytesseract.image_to_string(image, lang='vie+eng')
                
                if result and result.strip():
                    text_parts.append(result.strip())
                    
            except Exception as e:
                logger.warning(f"Error performing OCR on page {i+1}: {e}")
                continue
        
        return '\n\n'.join(text_parts)
    
    def parse_pdf(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse PDF documents (.pdf).
        - Text-based PDFs: Uses pypdf to extract text
        - Image-based PDFs: Uses Tesseract OCR to perform OCR
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary containing the parsed PDF information
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
            if file_extension != '.pdf':
                return {
                    "success": False,
                    "error": f"Unsupported file type: {file_extension}. Only .pdf files are supported.",
                    "content": "",
                    "summary": ""
                }
            
            # Determine if PDF is image-based or text-based
            is_image_based = self._is_image_based_pdf(file_path)
            
            # Extract text based on PDF type
            if is_image_based:
                if pdf2image is None:
                    return {
                        "success": False,
                        "error": "pdf2image library is required for image-based PDF processing. Please install it: pip install pdf2image",
                        "content": "",
                        "summary": ""
                    }
                
                # Lazy initialization of OCR - only initialize when needed
                if not self._ocr_initialized:
                    self._init_ocr()
                
                if not TesseractOCR:
                    return {
                        "success": False,
                        "error": "Tesseract OCR is required for image-based PDF processing. Please install: pip install pytesseract and install Tesseract OCR engine from https://github.com/tesseract-ocr/tesseract",
                        "content": "",
                        "summary": ""
                    }
                
                combined_content = self._extract_text_from_image_pdf(file_path)
                parsed_with = "tesseract"
            else:
                if PdfReader is None:
                    return {
                        "success": False,
                        "error": "pypdf library is required for text-based PDF processing. Please install it: pip install pypdf",
                        "content": "",
                        "summary": ""
                    }
                
                combined_content = self._extract_text_from_pdf(file_path)
                parsed_with = "pypdf"
            
            if not combined_content or not combined_content.strip():
                return {
                    "success": False,
                    "error": "No content found in PDF document",
                    "content": "",
                    "summary": ""
                }
            
            result = {
                "success": True,
                "content": combined_content.strip(),
                "summary": '',  # This will be replaced by AI summary
                "file_type": file_extension,
                "file_size": len(combined_content),
                "is_image_based": is_image_based,
                "parsed_with": parsed_with
            }
            
            logger.info(f"Successfully parsed PDF document: {file_path} (type: {'image-based' if is_image_based else 'text-based'}, parser: {parsed_with})")
            return result
            
        except Exception as e:
            logger.error(f"Error parsing PDF document {file_path}: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": "",
                "summary": ""
            }

