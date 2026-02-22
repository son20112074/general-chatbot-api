"""
Image Parser Module

This module contains the ImageParser class for parsing image files.
- Uses Tesseract OCR to perform OCR on images for text extraction
- Tesseract supports Vietnamese language recognition
"""

import logging
from pathlib import Path
from typing import Dict, Any, Union
import os

try:
    import pytesseract
    TesseractOCR = True
except ImportError as e:
    TesseractOCR = False
    import logging
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning(f"pytesseract import failed: {e}. Please install it: pip install pytesseract")

try:
    from PIL import Image
except ImportError:
    Image = None

logger = logging.getLogger(__name__)


class ImageParser:
    """Parser for image files using OCR to extract text."""
    
    def __init__(self):
        """Initialize the image parser."""
        self._ocr_initialized = False
    
    def _init_ocr(self):
        """Initialize Tesseract OCR for image processing (lazy initialization)."""
        if self._ocr_initialized:
            return
        
        if TesseractOCR:
            try:
                # Try to find Tesseract executable if not in PATH
                try:
                    pytesseract.get_tesseract_version()
                    logger.info("Tesseract OCR initialized successfully for image parsing")
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
    
    def _extract_text_from_image(self, file_path: Union[str, Path]) -> str:
        """
        Extract text from image using Tesseract OCR.
        
        Args:
            file_path: Path to the image file
            
        Returns:
            Extracted text content from OCR
        """
        if Image is None:
            raise ImportError("PIL/Pillow is required for image processing")
        
        if not TesseractOCR:
            raise ImportError("pytesseract is required for OCR functionality. Install it: pip install pytesseract")
        
        file_path = Path(file_path)
        
        try:
            # Try to set Tesseract path if not in PATH (common on Windows)
            # You can set this manually: pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
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
                        logger.info(f"Found Tesseract at: {path}")
                        break
                else:
                    raise Exception(
                        "Tesseract OCR is not installed or not in PATH. "
                        "Please install Tesseract OCR from https://github.com/UB-Mannheim/tesseract/wiki "
                        "or set pytesseract.pytesseract.tesseract_cmd to the Tesseract executable path."
                    )
            
            # Load image using PIL
            image = Image.open(str(file_path))
            
            # Convert to RGB if necessary (Tesseract works best with RGB)
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Perform OCR using Tesseract with Vietnamese language support
            # lang='vie' for Vietnamese, 'eng' for English, 'vie+eng' for both
            result = pytesseract.image_to_string(image, lang='vie+eng')
            
            return result if result else ""
                    
        except Exception as e:
            logger.error(f"Error performing OCR on image: {e}")
            raise
    
    def parse_image(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse image files (.png, .jpg, .jpeg, .tiff, .webp, .gif, .bmp).
        Uses Tesseract OCR to perform OCR and extract text from images.
        
        Args:
            file_path: Path to the image file
            
        Returns:
            Dictionary containing the parsed image information
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
            supported_extensions = ['.png', '.jpg', '.jpeg', '.tiff', '.tif', '.webp', '.gif', '.bmp']
            if file_extension not in supported_extensions:
                return {
                    "success": False,
                    "error": f"Unsupported file type: {file_extension}. Supported formats: {', '.join(supported_extensions)}",
                    "content": "",
                    "summary": ""
                }
            
            # Check if required libraries are available
            if Image is None:
                return {
                    "success": False,
                    "error": "PIL/Pillow library is required for image processing. Please install it: pip install Pillow",
                    "content": "",
                    "summary": ""
                }
            
            # Lazy initialization of OCR - only initialize when needed
            if not self._ocr_initialized:
                self._init_ocr()
            
            if not TesseractOCR:
                return {
                    "success": False,
                    "error": "Tesseract OCR is required for image OCR processing. Please install: pip install pytesseract and install Tesseract OCR engine from https://github.com/tesseract-ocr/tesseract",
                    "content": "",
                    "summary": ""
                }
            
            # Extract text using OCR
            combined_content = self._extract_text_from_image(file_path)
            
            if not combined_content or not combined_content.strip():
                return {
                    "success": False,
                    "error": "No text found in image (OCR did not detect any text)",
                    "content": "",
                    "summary": ""
                }
            
            result = {
                "success": True,
                "content": combined_content.strip(),
                "summary": '',  # This will be replaced by AI summary
                "file_type": file_extension,
                "file_size": len(combined_content),
                "parsed_with": "tesseract"
            }
            
            logger.info(f"Successfully parsed image: {file_path} (parser: tesseract, text length: {len(combined_content)})")
            return result
            
        except Exception as e:
            logger.error(f"Error parsing image {file_path}: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": "",
                "summary": ""
            }

