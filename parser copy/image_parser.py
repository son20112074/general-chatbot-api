"""
Image Parser Module

This module contains the ImageParser class for parsing image files.
- Uses PaddleOCR-VL via vLLM server for VLM; layout model (PP-DocLayoutV3) still loads locally once.
- Optional env PADDLEOCR_VL_SERVER_URL; default: https://6780-118-70-233-92.ngrok-free.app/v1
- Install: pip install "paddleocr[doc-parser]"
"""

import logging
import os
import warnings
from pathlib import Path
from typing import Dict, Any, Union, Optional, List

DEFAULT_VL_SERVER_URL = "https://6780-118-70-233-92.ngrok-free.app"


def _get_vl_server_url() -> str:
    raw = os.environ.get("PADDLEOCR_VL_SERVER_URL", "").strip()
    if not raw:
        try:
            from app.core.config import settings
            raw = (getattr(settings, "PADDLEOCR_VL_SERVER_URL", None) or "").strip()
        except Exception:
            pass
    return raw or DEFAULT_VL_SERVER_URL


_raw = _get_vl_server_url()
_vl_server_url = _raw.rstrip("/")
if not _vl_server_url.endswith("/v1"):
    _vl_server_url = f"{_vl_server_url}/v1"

try:
    from paddleocr import PaddleOCRVL
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PaddleOCRVL = None  # type: ignore
    PADDLEOCR_AVAILABLE = False

logger = logging.getLogger(__name__)

# Pipeline singleton: loaded once and reused
_pipeline: Optional[Any] = None
_pipeline_load_failed: bool = False


def _get_pipeline():
    """Connect to PaddleOCR-VL vLLM server (singleton)."""
    global _pipeline, _pipeline_load_failed

    if _pipeline_load_failed:
        raise RuntimeError(
            "PaddleOCR-VL (vLLM server) previously failed. Check PADDLEOCR_VL_SERVER_URL and server."
        )

    if _pipeline is not None:
        return _pipeline

    if not PADDLEOCR_AVAILABLE:
        raise ImportError(
            "paddleocr is required. Install: pip install -U \"paddleocr[doc-parser]\"."
        )

    try:
        logger.info("Connecting to PaddleOCR-VL vLLM server: %s ...", _vl_server_url)
        _pipeline = PaddleOCRVL(
            vl_rec_backend="vllm-server",
            vl_rec_server_url=_vl_server_url,
        )
        logger.info("PaddleOCR-VL vLLM server connected.")
        return _pipeline
    except Exception as e:
        _pipeline_load_failed = True
        _pipeline = None
        logger.error("Failed to connect to PaddleOCR-VL vLLM server: %s", e)
        raise


def _collect_text_from_results(output: List[Any]) -> str:
    """Collect markdown text from predict() results (from res.markdown or res.json)."""
    parts: List[str] = []
    for res in output:
        md = getattr(res, "markdown", None)
        if md and isinstance(md, dict):
            texts = md.get("markdown_texts")
            if isinstance(texts, list):
                parts.extend(str(t) for t in texts if t)
            elif isinstance(texts, str):
                parts.append(texts)
        if not parts:
            j = getattr(res, "json", None)
            if j and isinstance(j, dict):
                for key in ("markdown_texts", "text", "content", "result"):
                    if key in j and j[key]:
                        v = j[key]
                        if isinstance(v, list):
                            parts.extend(str(x) for x in v if x)
                        elif isinstance(v, str):
                            parts.append(v)
                        break
    return "\n".join(parts).strip() if parts else ""


class ImageParser:
    """Parser for image files using PaddleOCR-VL (official paddleocr package)."""

    SUPPORTED_EXTENSIONS = [
        '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.webp', '.gif', '.bmp'
    ]

    def _extract_text_from_image(self, file_path: Union[str, Path]) -> str:
        """
        Extract text from an image using PaddleOCR-VL pipeline.
        Uses predict(path_or_url) then iterates output and res.print(); text is collected from res.markdown/res.json.
        """
        pipeline = _get_pipeline()
        # predict() accepts local path or URL (e.g. "https://...")
        input_path = str(file_path)
        output = pipeline.predict(input_path)

        for res in output:
            res.print()

        return _collect_text_from_results(output)

    def parse_image(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse image files (.png, .jpg, .jpeg, .tiff, .webp, .gif, .bmp).
        Uses PaddleOCR-VL to perform OCR and extract text from images.

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

            file_extension = file_path.suffix.lower()
            if file_extension not in self.SUPPORTED_EXTENSIONS:
                return {
                    "success": False,
                    "error": (
                        f"Unsupported file type: {file_extension}. "
                        f"Supported formats: {', '.join(self.SUPPORTED_EXTENSIONS)}"
                    ),
                    "content": "",
                    "summary": ""
                }

            if not PADDLEOCR_AVAILABLE:
                return {
                    "success": False,
                    "error": "paddleocr is required. Install: pip install -U \"paddleocr[doc-parser]\".",
                    "content": "",
                    "summary": ""
                }

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
                "summary": "",
                "file_type": file_extension,
                "file_size": len(combined_content),
                "parsed_with": "paddleocr-vl"
            }

            logger.info(
                "Successfully parsed image: %s (parser: paddleocr-vl, text length: %d)",
                file_path,
                len(combined_content),
            )
            return result

        except Exception as e:
            logger.error("Error parsing image %s: %s", file_path, e)
            return {
                "success": False,
                "error": str(e),
                "content": "",
                "summary": ""
            }
