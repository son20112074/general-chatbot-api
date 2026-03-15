"""
PDF Parser Module

This module contains the PDFParser class for parsing PDF documents.
- Text-based PDFs: Uses PyMuPDF (fitz) to extract text directly
- Image-based PDFs: Uses PaddleOCR-VL vLLM server (same as image_parser)
"""

import logging
from pathlib import Path
from typing import Dict, Any, Union

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

logger = logging.getLogger(__name__)


def _get_paddle_pipeline():
    """Use PaddleOCR-VL pipeline from image_parser for image-based PDF/OCR."""
    from .image_parser import _get_pipeline, _collect_text_from_results
    return _get_pipeline(), _collect_text_from_results


def _is_paddle_available() -> bool:
    try:
        from .image_parser import PADDLEOCR_AVAILABLE
        return bool(PADDLEOCR_AVAILABLE)
    except Exception:
        return False


class PDFParser:
    """Parser for PDF documents supporting both text-based and image-based PDFs."""

    def _is_image_based_pdf(self, file_path: Union[str, Path]) -> bool:
        """
        Check if PDF is image-based (scanned) or text-based.

        Args:
            file_path: Path to the PDF file

        Returns:
            True if PDF is image-based, False if text-based
        """
        if fitz is None:
            logger.warning("PyMuPDF (fitz) not available, assuming image-based PDF")
            return True

        try:
            file_path = Path(file_path)
            doc = fitz.open(str(file_path))
            text_content = ""
            pages_to_check = min(3, len(doc))
            for i in range(pages_to_check):
                try:
                    page = doc.load_page(i)
                    text = page.get_text("text")
                    if text:
                        text_content += text.strip()
                except Exception as e:
                    logger.debug("Error extracting text from page %s: %s", i, e)
                    continue
            doc.close()

            if len(text_content) > 50:
                logger.info("PDF appears to be text-based (found %d characters)", len(text_content))
                return False
            logger.info("PDF appears to be image-based (little or no text found)")
            return True
        except Exception as e:
            logger.warning("Error checking PDF type with PyMuPDF: %s. Assuming image-based PDF.", e)
            return True

    def _extract_text_from_pdf(self, file_path: Union[str, Path]) -> str:
        """
        Extract text from text-based PDF using PyMuPDF (fitz).
        """
        if fitz is None:
            raise ImportError("PyMuPDF (fitz) is required for text-based PDF extraction. pip install pymupdf")

        file_path = Path(file_path)
        text_parts = []
        try:
            doc = fitz.open(str(file_path))
            try:
                for page in doc:
                    page_text = page.get_text("text")
                    if page_text:
                        text_parts.append(page_text.strip())
            finally:
                doc.close()
        except Exception as e:
            logger.error("Error extracting text from PDF with PyMuPDF: %s", e)
            raise
        return "\n\n".join(text_parts)

    def _extract_text_from_image_pdf(self, file_path: Union[str, Path]) -> str:
        """
        Extract text from image-based PDF using PaddleOCR-VL vLLM server (same as image_parser).
        PaddleOCRVL.predict() accepts PDF path and returns per-page results.
        """
        pipeline, collect_text = _get_paddle_pipeline()
        output = pipeline.predict(str(file_path))
        for res in output:
            res.print()
        return collect_text(output)

    def parse_pdf(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse PDF documents (.pdf).
        - Text-based PDFs: Uses PyMuPDF (fitz) to extract text
        - Image-based PDFs: Uses PaddleOCR-VL vLLM server (same pipeline as image_parser)
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

            file_extension = file_path.suffix.lower()
            if file_extension != ".pdf":
                return {
                    "success": False,
                    "error": f"Unsupported file type: {file_extension}. Only .pdf files are supported.",
                    "content": "",
                    "summary": ""
                }

            is_image_based = self._is_image_based_pdf(file_path)

            if is_image_based:
                if not _is_paddle_available():
                    return {
                        "success": False,
                        "error": (
                            "paddleocr is required for image-based PDF. "
                            "Install: pip install -U \"paddleocr[doc-parser]\" and set PADDLEOCR_VL_SERVER_URL."
                        ),
                        "content": "",
                        "summary": ""
                    }
                combined_content = self._extract_text_from_image_pdf(file_path)
                parsed_with = "paddleocr-vl"
            else:
                if fitz is None:
                    return {
                        "success": False,
                        "error": "PyMuPDF (fitz) is required for text-based PDF. pip install pymupdf",
                        "content": "",
                        "summary": ""
                    }
                combined_content = self._extract_text_from_pdf(file_path)
                parsed_with = "pymupdf"

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
                "summary": "",
                "file_type": file_extension,
                "file_size": len(combined_content),
                "is_image_based": is_image_based,
                "parsed_with": parsed_with
            }

            logger.info(
                "Successfully parsed PDF: %s (type: %s, parser: %s)",
                file_path,
                "image-based" if is_image_based else "text-based",
                parsed_with,
            )
            return result

        except Exception as e:
            logger.error("Error parsing PDF document %s: %s", file_path, e)
            return {
                "success": False,
                "error": str(e),
                "content": "",
                "summary": ""
            }
