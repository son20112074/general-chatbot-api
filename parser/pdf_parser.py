"""
PDF Parser Module

This module contains the PDFParser class for parsing PDF documents.
- Text-based PDFs: Uses PyMuPDF (fitz) to extract text directly
- Image-based PDFs: PaddleOCR-VL vLLM server only (same pipeline as image_parser; no local Tesseract)
"""

import logging
import os
from pathlib import Path
from typing import Dict, Any, Union, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

logger = logging.getLogger(__name__)


def _get_pdf_ocr_limits() -> Tuple[int, int]:
    """Return (max_size_mb, max_pages) for image-based PDF OCR."""
    max_mb = 50
    max_pages = 20
    try:
        from app.core.config import settings
        max_mb = int(getattr(settings, "MAX_PDF_SIZE_MB", max_mb))
        max_pages = int(getattr(settings, "MAX_PDF_PAGES_FOR_OCR", max_pages))
    except Exception:
        pass
    env_mb = os.environ.get("MAX_PDF_SIZE_MB", "").strip()
    env_pages = os.environ.get("MAX_PDF_PAGES_FOR_OCR", "").strip()
    if env_mb.isdigit():
        max_mb = int(env_mb)
    if env_pages.isdigit():
        max_pages = int(env_pages)
    return max_mb, max_pages


def _count_pdf_pages(file_path: Path) -> int:
    if fitz is not None:
        try:
            doc = fitz.open(str(file_path))
            try:
                return len(doc)
            finally:
                doc.close()
        except Exception as e:
            logger.warning("PyMuPDF page count failed: %s", e)
    from pypdf import PdfReader
    return len(PdfReader(str(file_path)).pages)


def _validate_pdf_for_ocr(file_path: Path) -> None:
    """Raise ValueError if scanned PDF exceeds size or page limits."""
    max_mb, max_pages = _get_pdf_ocr_limits()
    size_bytes = file_path.stat().st_size
    max_bytes = max_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise ValueError(
            f"PDF vượt quá {max_mb} MB (kích thước {size_bytes / (1024 * 1024):.1f} MB). "
            "Giảm kích thước file hoặc tách thành nhiều phần nhỏ hơn."
        )
    page_count = _count_pdf_pages(file_path)
    if page_count > max_pages:
        raise ValueError(
            f"PDF có {page_count} trang, vượt giới hạn OCR {max_pages} trang. "
            "Tách file hoặc tăng MAX_PDF_PAGES_FOR_OCR."
        )
    logger.info(
        "PDF OCR validation OK: %s (%d pages, %.1f MB)",
        file_path,
        page_count,
        size_bytes / (1024 * 1024),
    )


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


def _paddle_missing_result() -> Dict[str, Any]:
    """Same stack as image parsing: client + PADDLEOCR_VL_SERVER_URL vLLM endpoint."""
    return {
        "success": False,
        "error": (
            "Image-based PDFs require PaddleOCR-VL (vLLM server), same as image parsing. "
            'Install: pip install -U "paddleocr[doc-parser]". '
            "Set PADDLEOCR_VL_SERVER_URL to your OpenAI-compatible vLLM base URL "
            "(see image_parser / app settings)."
        ),
        "content": "",
        "summary": "",
    }


class PDFParser:
    """Parser for PDF documents supporting both text-based and image-based PDFs."""

    def _is_image_based_pdf(self, file_path: Union[str, Path]) -> bool:
        """Check if PDF is image-based (scanned) by attempting text extraction."""
        file_path = Path(file_path)

        if fitz is not None:
            try:
                doc = fitz.open(str(file_path))
                text_content = ""
                pages_to_check = min(3, len(doc))
                for i in range(pages_to_check):
                    try:
                        text_content += doc.load_page(i).get_text("text").strip()
                    except Exception:
                        continue
                doc.close()
                is_image = len(text_content) <= 50
                logger.info("PDF type check via PyMuPDF: %s (%d chars)", "image-based" if is_image else "text-based", len(text_content))
                return is_image
            except Exception as e:
                logger.warning("PyMuPDF check failed: %s. Falling back to pypdf check.", e)

        # fitz unavailable or failed — use pypdf
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(file_path))
            text_content = ""
            for page in reader.pages[:3]:
                text_content += (page.extract_text() or "").strip()
            is_image = len(text_content) <= 50
            logger.info("PDF type check via pypdf: %s (%d chars)", "image-based" if is_image else "text-based", len(text_content))
            return is_image
        except Exception as e:
            logger.warning("pypdf check failed: %s. Assuming image-based PDF.", e)
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
        file_path = Path(file_path)
        _validate_pdf_for_ocr(file_path)
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
                    logger.error(
                        "Image-based PDF requires PaddleOCR-VL; not installed or import failed: %s",
                        file_path,
                    )
                    return _paddle_missing_result()
                combined_content = self._extract_text_from_image_pdf(file_path)
                parsed_with = "paddleocr-vl"
            else:
                if fitz is not None:
                    combined_content = self._extract_text_from_pdf(file_path)
                    parsed_with = "pymupdf"
                else:
                    from pypdf import PdfReader
                    reader = PdfReader(str(file_path))
                    combined_content = "\n".join([p.extract_text() or "" for p in reader.pages])
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
