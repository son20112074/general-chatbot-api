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
        pipeline, collect_text = _get_paddle_pipeline()
        output = pipeline.predict(str(file_path))
        for res in output:
            res.print()
        return collect_text(output)

    def _extract_text_from_image_pdf_tesseract(self, file_path: Union[str, Path]) -> str:
        """Fallback OCR: render each PDF page to image at 300 DPI, then run pytesseract."""
        try:
            import pytesseract
        except ImportError as exc:
            raise ImportError(f"pytesseract is required for OCR fallback: {exc}")

        parts: list = []

        if fitz is not None:
            import io
            from PIL import Image
            doc = fitz.open(str(file_path))
            try:
                for page in doc:
                    pix = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    text = pytesseract.image_to_string(img, lang="vie+eng")
                    if text.strip():
                        parts.append(text.strip())
            finally:
                doc.close()
        else:
            # fitz not installed — use pdf2image (requires poppler)
            try:
                from pdf2image import convert_from_path
            except ImportError as exc:
                raise ImportError(f"pdf2image is required when PyMuPDF is not installed: {exc}")
            images = convert_from_path(str(file_path), dpi=300)
            for img in images:
                text = pytesseract.image_to_string(img, lang="vie+eng")
                if text.strip():
                    parts.append(text.strip())

        return "\n\n".join(parts)

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
                if _is_paddle_available():
                    combined_content = self._extract_text_from_image_pdf(file_path)
                    parsed_with = "paddleocr-vl"
                else:
                    logger.info("PaddleOCR not available, falling back to pytesseract for image-based PDF: %s", file_path)
                    combined_content = self._extract_text_from_image_pdf_tesseract(file_path)
                    parsed_with = "pytesseract"
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
