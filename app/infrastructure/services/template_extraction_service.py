import asyncio
import json
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from pypdf import PdfReader

from app.core.config import settings
from app.infrastructure.services.oss_service import OpenRouterClient
from app.presentation.api.v1.endpoints.internal.files import (
    extract_csv_content,
    extract_doc_content,
    extract_docx_content,
    extract_text_content,
    extract_xlsx_content,
)

logger = logging.getLogger(__name__)

# ── Token budgeting ───────────────────────────────────────────────────────────
# Bound the INPUT length of every per-chunk LLM call so it stays under the model
# context window. We do NOT set a fixed output size on the server (see
# oss_service); it allocates the remaining context for output.
MODEL_MAX_TOKENS = getattr(settings, "LLM_MODEL_MAX_TOKENS", 32768)
OUTPUT_RESERVE_TOKENS = getattr(settings, "LLM_MAX_OUTPUT_TOKENS", 4096)
SAFETY_MARGIN_TOKENS = 1500
MAX_INPUT_TOKENS = max(
    1024, MODEL_MAX_TOKENS - OUTPUT_RESERVE_TOKENS - SAFETY_MARGIN_TOKENS
)
# Conservative chars-per-token (measured ~2.84 on this tokenizer for VI/EN; CJK is
# denser, so character-based chunking below stays safely under the token budget).
CHARS_PER_TOKEN = 2.5


@dataclass
class TextChunk:
    index: int
    text: str
    token_count: int


@dataclass
class ChunkExtractionResult:
    chunk_index: int
    attempts: int
    valid: bool
    data: Dict[str, Any]
    errors: List[str]


@dataclass
class ExtractionReport:
    source_file: str
    total_chunks: int
    processed_chunks: int
    failed_chunks: int
    elapsed_ms: int
    aggregated_data: Dict[str, Any]
    chunk_results: List[ChunkExtractionResult]
    warnings: List[str]


class TemplateExtractionService:
    def __init__(
        self,
        worker_count: int = 3,   
        max_concurrency: int = 3,
        target_chunk_tokens: int = 1500,
    ):
        self.worker_count = worker_count
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self.target_chunk_tokens = target_chunk_tokens
        self._llm_client = OpenRouterClient()

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return math.ceil((time.perf_counter() - started) * 1000)
 
    async def extract_document(self, file_path: str, extraction_prompt: str) -> ExtractionReport:
        started = time.perf_counter()

        text = self._load_document_text(file_path)
        report = await self.extract_text(text, file_path, extraction_prompt)

        return report

    async def extract_text(
        self,
        source_text: str,
        source_name: str,
        extraction_prompt: str,
    ) -> ExtractionReport:

        started = time.perf_counter()

        # Account for the fixed prompt wrapper + extraction_prompt so each chunk's
        # full prompt stays within the model input budget.
        prompt_overhead_tokens = self._estimate_tokens(self._build_prompt(extraction_prompt, ""))
        chunks = self._split_text(source_text, prompt_overhead_tokens)

        queue: asyncio.Queue = asyncio.Queue()
        results: List[Optional[ChunkExtractionResult]] = [None] * len(chunks)

        for chunk in chunks:
            queue.put_nowait(chunk)

        workers = [
            asyncio.create_task(self._worker(queue, extraction_prompt, results))
            for _ in range(self.worker_count)
        ]

        await queue.join()

        for _ in workers:
            queue.put_nowait(None)

        await asyncio.gather(*workers)

        finalized = [r for r in results if r]
        failed = [r for r in finalized if not r.valid]

        # fallback if everything fails
        if chunks and (not finalized or len(failed) == len(chunks)):
            fallback_markdown = "## Fallback\n- Không trích xuất được dữ liệu"
            fallback_json = self._split_markdown_to_json(fallback_markdown)

            return ExtractionReport(
                source_file=source_name,
                total_chunks=len(chunks),
                processed_chunks=len(finalized),
                failed_chunks=len(failed),
                elapsed_ms=self._elapsed_ms(started),
                aggregated_data={"markdown": fallback_markdown, "json": fallback_json},
                chunk_results=finalized,
                warnings=[f"Chunk {r.chunk_index} failed" for r in failed],
            )

        markdown_chunks = [
            r.data.get("markdown", "")
            for r in finalized
            if r.valid and isinstance(r.data, dict)
        ]

        aggregated = self._aggregate_markdown(markdown_chunks)

        if not aggregated.strip():
            aggregated = "## Fallback\n- Không trích xuất được dữ liệu"

        aggregated_json = self._split_markdown_to_json(aggregated)

        if not aggregated_json:
            aggregated_json = {"Fallback": "Không trích xuất được dữ liệu"}

        return ExtractionReport(
            source_file=source_name,
            total_chunks=len(chunks),
            processed_chunks=len(finalized),
            failed_chunks=len(failed),
            elapsed_ms=self._elapsed_ms(started),
            aggregated_data={"markdown": aggregated, "json": aggregated_json},
            chunk_results=finalized,
            warnings=[f"Chunk {r.chunk_index} failed" for r in failed],
        )

    # =========================
    # WORKER
    # =========================

    async def _worker(self, queue, extraction_prompt, results):
        while True:
            chunk = await queue.get()
            if chunk is None:
                queue.task_done()
                break

            try:
                result = await self._extract_chunk(chunk, extraction_prompt)
                results[chunk.index] = result
            except Exception as e:
                results[chunk.index] = ChunkExtractionResult(
                    chunk_index=chunk.index,
                    attempts=1,
                    valid=False,
                    data={},
                    errors=[str(e)],
                )
            finally:
                queue.task_done()

    async def _extract_chunk(self, chunk: TextChunk, extraction_prompt: str):
        prompt = self._build_prompt(extraction_prompt, chunk.text)

        output = ""
        for _ in range(2):
            candidate = await self._call_llm(prompt)
            if self._is_usable_markdown(candidate):
                output = candidate
                break

        if not self._is_usable_markdown(output):
            output = "## Fallback\n- Không trích xuất được dữ liệu"

        return ChunkExtractionResult(
            chunk_index=chunk.index,
            attempts=2,
            valid=True,
            data={"markdown": output},
            errors=[],
        )

    # =========================
    # LLM
    # =========================

    async def _call_llm(self, prompt: str) -> str:
        try:
            async with self._semaphore:
                message = await asyncio.wait_for(
                    self._llm_client.ainvoke(prompt),
                    timeout=25,
                )
        except:
            return ""

        content = getattr(message, "content", "")
        if not isinstance(content, str):
            content = str(content)

        return content.strip()

    # =========================
    # PROMPT
    # =========================

    def _build_prompt(self, extraction_prompt: str, text: str) -> str:
        return f"""
{extraction_prompt}

## OUTPUT FORMAT
- Use Markdown
- ALWAYS include heading sections using ##
- NEVER skip sections in TEMPLATE
- Each section: bullet points only

## ANTI-DUPLICATION
- Do not repeat same fact
- Merge similar information

## NULL RULE (CRITICAL)
- If no relevant information → output exactly: - null
- Do NOT write sentences like "không có thông tin"
- Do NOT explain absence

## RULES
- No JSON
- Vietnamese
- No hallucination

## INPUT
{text}
"""

    # =========================
    # AGGREGATION (NO DEDUP)
    # =========================

    def _aggregate_markdown(self, chunks: List[str]) -> str:
        sections: Dict[str, List[str]] = {}
        current = "Unknown"

        for md in chunks:
            if not md:
                continue

            for line in md.splitlines():
                line = line.strip()
                if not line:
                    continue

                if line.startswith("#"):
                    current = line.lstrip("#").strip() or "Unknown"
                    sections.setdefault(current, [])
                    continue

                if line.startswith("- "):
                    line = line[2:].strip()

                if line.lower() == "null":
                    continue

                sections.setdefault(current, [])
                sections[current].append(line)

        final = []
        for title, lines in sections.items():
            final.append(f"## {title}")
            for l in lines:   # ✅ no dedup
                final.append(f"- {l}")
            final.append("")

        return "\n".join(final).strip()

    # =========================
    # MARKDOWN → JSON
    # =========================

    def _split_markdown_to_json(self, markdown: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        current_key: Optional[str] = None
        buffer: List[str] = []

        def flush():
            nonlocal current_key, buffer
            if not current_key:
                return

            if not buffer:
                result[current_key] = None
            elif len(buffer) == 1:
                result[current_key] = buffer[0]
            else:
                result[current_key] = buffer

        for line in markdown.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("#"):
                flush()
                current_key = line.lstrip("#").strip() or "Unknown"
                buffer = []
                continue

            if line.startswith("- "):
                line = line[2:].strip()

            if line.lower() == "null":
                continue

            buffer.append(line)

        flush()

        return result or {"Fallback": "Không trích xuất được dữ liệu"}

    # =========================
    # HELPERS
    # =========================

    @staticmethod
    def _is_usable_markdown(content: str) -> bool:
        return bool(content and "##" in content)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return int(len(text) / CHARS_PER_TOKEN) + 1

    def _split_text(self, text: str, prompt_overhead_tokens: int = 0) -> List[TextChunk]:
        """Split text into chunks bounded by a CHARACTER budget.

        Whitespace-based splitting (``text.split()``) breaks for CJK / space-less
        text because a single "word" can be the entire document, producing chunks
        that overflow the model context. Splitting by characters is robust for any
        script. Each chunk is also kept under the input-token budget (minus the
        fixed prompt overhead) so the per-chunk prompt always fits the window.
        """
        if not text:
            return []

        # Desired chunk size (small, for extraction quality), capped so that
        # chunk + prompt overhead never exceeds the model input budget.
        desired_chars = int(self.target_chunk_tokens * CHARS_PER_TOKEN)
        safe_chars = int(max(256, MAX_INPUT_TOKENS - prompt_overhead_tokens) * CHARS_PER_TOKEN)
        max_chars = max(256, min(desired_chars, safe_chars))

        chunks: List[TextChunk] = []
        i = 0
        n = len(text)
        while i < n:
            end = min(i + max_chars, n)
            if end < n:
                window = text[i:end]
                brk = max(window.rfind("\n"), window.rfind(" "))
                if brk > max_chars // 2:
                    end = i + brk
            part = text[i:end].strip()
            if part:
                chunks.append(TextChunk(len(chunks), part, self._estimate_tokens(part)))
            i = end if end > i else i + max_chars

        logger.info(
            "extract:_split_text chars=%s max_chars=%s overhead_tokens=%s chunks=%s",
            n,
            max_chars,
            prompt_overhead_tokens,
            len(chunks),
        )
        return chunks

    def _load_document_text(self, file_path: str) -> str:
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            return self._extract_pdf_text(str(path))

        if suffix == ".docx":
            return extract_docx_content(str(path))

        if suffix == ".doc":
            return extract_doc_content(str(path))

        if suffix == ".xlsx":
            return extract_xlsx_content(str(path))

        if suffix == ".csv":
            return extract_csv_content(str(path))

        return extract_text_content(str(path))

    def _extract_pdf_text(self, file_path: str) -> str:
        reader = PdfReader(file_path)
        text = "\n".join([p.extract_text() or "" for p in reader.pages])

        if len(text.strip()) > 50:
            return text

        logger.info("PDF appears image-based (little text from pypdf), falling back to OCR: %s", file_path)
        return self._ocr_pdf(file_path)

    def _ocr_pdf(self, file_path: str) -> str:
        try:
            import io
            import fitz
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            logger.error("OCR fallback unavailable — install pymupdf and pytesseract: %s", exc)
            return ""

        doc = fitz.open(file_path)
        parts: List[str] = []
        try:
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                page_text = pytesseract.image_to_string(img, lang="vie+eng")
                if page_text.strip():
                    parts.append(page_text.strip())
        finally:
            doc.close()

        return "\n\n".join(parts)
