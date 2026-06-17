import asyncio
import copy
import json
import logging
import math
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.infrastructure.services.template_extraction_service import (
    ExtractionReport,
    TemplateExtractionService,
)

logger = logging.getLogger(__name__)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    logger.addHandler(_handler)
logger.setLevel(logging.INFO)


@dataclass
class MultiFileExtractionReport:
    source_files: List[str]
    processed_files: int
    failed_files: int
    elapsed_ms: int
    final_json: Dict[str, Any]
    warnings: List[str]

    def to_dict(self):
        return asdict(self)


class TemplateExtractionMultiFilesService:
    def __init__(
        self,
        extraction_service: Optional[TemplateExtractionService] = None,
        max_concurrency: int = 5,
    ) -> None:
        self._extraction_service = extraction_service or TemplateExtractionService()
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return math.ceil((time.perf_counter() - started) * 1000)

    async def extract_documents(
        self,
        file_paths: List[str],
        extraction_prompt: str,
        report_template: str = "",
        template_file_path: Optional[str] = None,
    ) -> MultiFileExtractionReport:
        started = time.perf_counter()
        logger.info("multi_extract:start files=%s", len(file_paths))

        # Build template tree from file (hierarchical) or fall back to flat keys
        template_tree: Optional[Dict] = None
        if template_file_path:
            template_text = self._extraction_service._load_document_text(template_file_path)
            template_tree = self._normalize_tree_keys(
                await self._extract_template_tree_via_llm(template_text)
            )

            logger.info("multi_extract:template_tree_loaded top_keys=%s", len(template_tree))

        template_keys = (
            self._flatten_tree_keys(template_tree)
            if template_tree
            else self._extract_template_keys(report_template)
        )

        # Description is not in "- bullet" format → build hierarchical tree from it via LLM
        if not template_keys and not template_tree and report_template:
            logger.info("multi_extract:template_keys_empty — building tree from description via LLM")
            template_tree = self._normalize_tree_keys(
                await self._extract_template_tree_via_llm(report_template)
            )
            template_keys = self._flatten_tree_keys(template_tree) if template_tree else []
            logger.info(
                "multi_extract:template_tree_from_desc top_keys=%s flat_keys=%s",
                len(template_tree or {}),
                len(template_keys),
            )

        if not file_paths:
            scaffold = (
                self._build_scaffold(template_tree)
                if template_tree
                else {key: None for key in template_keys}
            )
            return MultiFileExtractionReport(
                source_files=[],
                processed_files=0,
                failed_files=0,
                elapsed_ms=0,
                final_json=scaffold,
                warnings=[],
            )

        tasks = [
            asyncio.create_task(self._extract_one(path, extraction_prompt))
            for path in file_paths
        ]
        results = await asyncio.gather(*tasks)

        file_markdowns: Dict[str, str] = {}
        warnings: List[str] = []
        failed_files = 0

        for file_path, report, err in results:
            if err is not None:
                failed_files += 1
                warnings.append(f"{file_path}: {err}")
                logger.warning("multi_extract:file_failed path=%s err=%s", file_path, err)
                continue

            markdown = self._safe_markdown(report)
            if markdown:
                file_markdowns[file_path] = markdown
                logger.info("multi_extract:file_markdown path=%s chars=%s", file_path, len(markdown))
            else:
                logger.info("multi_extract:file_markdown_empty path=%s", file_path)

        merge_started = time.perf_counter()
        merged_markdown = self._merge_markdowns(list(file_markdowns.values()))
        logger.info(
            "multi_extract:merge_done markdown_count=%s merged_chars=%s elapsed_ms=%s",
            len(file_markdowns),
            len(merged_markdown),
            self._elapsed_ms(merge_started),
        )

        file_count = len(file_paths)
        min_paragraphs = max(3, 3 * file_count)

        llm_cluster_started = time.perf_counter()
        llm_clustered_markdown = await self._cluster_markdown_via_llm(
            merged_markdown, template_keys, template_tree, min_paragraphs
        )
        logger.info(
            "multi_extract:llm_cluster_done in_chars=%s out_chars=%s elapsed_ms=%s",
            len(merged_markdown),
            len(llm_clustered_markdown),
            self._elapsed_ms(llm_cluster_started),
        )

        final_markdown = llm_clustered_markdown
        json_started = time.perf_counter()
        print(final_markdown)
        if template_tree:
            final_json = await self._map_to_json_via_llm(
                final_markdown, template_tree, min_paragraphs
            )
        else:
            final_json = self._final_markdown_to_json_with_template(
                final_markdown, template_keys
            )

        logger.info(
            "multi_extract:json_done keys=%s elapsed_ms=%s",
            len(final_json),
            self._elapsed_ms(json_started),
        )

        elapsed_ms = self._elapsed_ms(started)
        logger.info(
            "multi_extract:done files=%s processed=%s failed=%s elapsed_ms=%s",
            len(file_paths),
            len(file_markdowns),
            failed_files,
            elapsed_ms,
        )

        return MultiFileExtractionReport(
            source_files=file_paths,
            processed_files=len(file_markdowns),
            failed_files=failed_files,
            elapsed_ms=elapsed_ms,
            final_json=final_json,
            warnings=warnings,
        )

    # =========================
    # TEMPLATE TREE
    # =========================

    async def _extract_template_tree_via_llm(self, template_text: str) -> Dict:
        """Extract hierarchical template structure via LLM; returns a nested dict.

        Tree schema:
          - Each key   = exact section/subsection title (preserving numbering)
          - Empty dict = leaf node (no children)
          - Nested dict = parent node with subsections
        """
        prompt = f"""You are an expert in analyzing the structure of Vietnamese administrative documents (reports, official letters, templates).

Task:
Extract the hierarchical structure of the REPORT CONTENT into a JSON object.

---

## EXTRACTION SCOPE (CRITICAL)

ONLY extract main content sections starting from:
- I., II., III., IV., ...

And their nested levels:
- 1., 2., 3.
- a), b), c) (if present)
- deeper levels if they exist

COMPLETELY IGNORE:
- National header (e.g. "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
- Organization/unit name
- Document number
- Date/time
- Title like "BÁO CÁO"
- "Kính gửi"
- Introductory paragraphs (e.g. "Căn cứ...")
- Signature, recipients, footer

---

## OUTPUT RULES

- Return ONLY valid JSON (no markdown, no explanation)
- Each key must be the EXACT original section title (KEEP numbering like "I.", "1.", etc.)
- Value:
  - {{}} if it is a leaf node (no subsections)
  - {{ ... }} if it has nested subsections

---

## EXPECTED EXAMPLE

Input:
I. GENERAL SITUATION
II. IMPLEMENTATION RESULTS
    1. Achievements
        1. Task A
        2. Task B
    2. Overall evaluation

Output:
{{
  "I. GENERAL SITUATION": {{}},
  "II. IMPLEMENTATION RESULTS": {{
    "1. Achievements": {{
      "1. Task A": {{}},
      "2. Task B": {{}}
    }},
    "2. Overall evaluation": {{}}
  }}
}}

---

## TEMPLATE
{template_text}

JSON:"""

        raw = await self._extraction_service._call_llm(prompt)

        # Strip optional markdown code fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw.strip(), flags=re.MULTILINE)

        try:
            tree = json.loads(raw.strip())
            if isinstance(tree, dict) and tree:
                logger.info("multi_extract:template_tree_llm_ok top_keys=%s", len(tree))
                return tree
        except (json.JSONDecodeError, ValueError):
            logger.warning("multi_extract:template_tree_llm_parse_failed; using indent fallback")

        return self._parse_template_text_to_tree(template_text)

    @staticmethod
    def _parse_template_text_to_tree(template_text: str) -> Dict:
        """Fallback: infer tree from indentation without LLM."""
        lines = [
            (len(l) - len(l.lstrip()), l.strip())
            for l in template_text.splitlines()
            if l.strip()
        ]
        root: Dict = {}
        # stack items: (indent_level, container_dict, key_in_container)
        stack: List[Tuple[int, Dict, str]] = []

        for indent, raw_key in lines:
            key = raw_key.lstrip("-").strip()
            if not key:
                continue

            # pop until we find a shallower ancestor
            while stack and stack[-1][0] >= indent:
                stack.pop()

            if stack:
                _, parent_container, parent_key = stack[-1]
                if not isinstance(parent_container.get(parent_key), dict):
                    parent_container[parent_key] = {}
                container = parent_container[parent_key]
            else:
                container = root

            container[key] = {}
            stack.append((indent, container, key))

        return root

    @staticmethod
    def _capitalize_key(key: str) -> str:
        if not key:
            return key
        return key[0].upper() + key[1:]

    @classmethod
    def _normalize_tree_keys(cls, tree: Dict) -> Dict:
        """Recursively capitalize the first letter of every key in the template tree."""
        return {
            cls._capitalize_key(k): cls._normalize_tree_keys(v) if isinstance(v, dict) else v
            for k, v in tree.items()
        }

    @staticmethod
    def _flatten_tree_keys(tree: Dict, prefix: str = "") -> List[str]:
        """Return all leaf-node paths joined by ' > ' (for flat-key compatibility)."""
        keys: List[str] = []
        for key, children in tree.items():
            full = f"{prefix} > {key}" if prefix else key
            if isinstance(children, dict) and children:
                keys.extend(
                    TemplateExtractionMultiFilesService._flatten_tree_keys(children, full)
                )
            else:
                keys.append(full)
        return keys

    @staticmethod
    def _build_scaffold(tree: Dict) -> Dict[str, Any]:
        """Build nested dict from tree with all leaf values set to None."""
        result: Dict[str, Any] = {}
        for key, children in tree.items():
            if isinstance(children, dict) and children:
                result[key] = TemplateExtractionMultiFilesService._build_scaffold(children)
            else:
                result[key] = None
        return result

    @staticmethod
    def _tree_to_markdown_template(tree: Dict, depth: int = 2) -> str:
        """Render template tree as hierarchical markdown (## top, ### second, ...)."""
        lines: List[str] = []
        heading = "#" * depth
        for key, children in tree.items():
            lines.append(f"{heading} {key}")
            if isinstance(children, dict) and children:
                lines.append(
                    TemplateExtractionMultiFilesService._tree_to_markdown_template(
                        children, depth + 1
                    )
                )
            else:
                lines.append("<One concise paragraph or null>")
        return "\n".join(lines)

    # =========================
    # CLUSTER
    # =========================

    async def _cluster_markdown_via_llm(
        self,
        merged_markdown: str,
        template_keys: List[str],
        template_tree: Optional[Dict] = None,
        min_paragraphs: int = 3,
    ) -> str:
        if not merged_markdown or not merged_markdown.strip():
            logger.info("multi_cluster:skip_empty_markdown")
            return ""

        started = time.perf_counter()
        chunks = self._split_markdown_for_clustering(merged_markdown)
        logger.info("multi_cluster:start chunks=%s", len(chunks))

        tasks = [
            asyncio.create_task(
                self._cluster_one_chunk(idx, chunk, template_keys, template_tree, min_paragraphs)
            )
            for idx, chunk in enumerate(chunks)
        ]
        results = await asyncio.gather(*tasks)

        ordered = [
            text
            for _, text in sorted(results, key=lambda x: x[0])
            if text and text.strip()
        ]
        combined = "\n\n".join(ordered).strip()
        logger.info("multi_cluster:chunks_combined chars=%s", len(combined))

        global_started = time.perf_counter()
        logger.info("multi_cluster:global_merge_start chars=%s", len(combined))
        _, final = await self._cluster_one_chunk(
            -1, combined, template_keys, template_tree, min_paragraphs
        )
        logger.info(
            "multi_cluster:global_merge_done out_chars=%s elapsed_ms=%s",
            len(final or ""),
            self._elapsed_ms(global_started),
        )

        output = final or combined
        logger.info(
            "multi_cluster:done output_chars=%s elapsed_ms=%s",
            len(output),
            self._elapsed_ms(started),
        )
        return output

    async def _cluster_one_chunk(
        self,
        idx: int,
        chunk_markdown: str,
        template_keys: List[str],
        template_tree: Optional[Dict] = None,
        min_paragraphs: int = 3,
    ) -> Tuple[int, str]:
        started = time.perf_counter()
        prompt = self._build_cluster_prompt(
            chunk_markdown, template_keys, template_tree, min_paragraphs
        )
        try:
            logger.info("multi_cluster:chunk_start idx=%s chars=%s", idx, len(chunk_markdown))
            clustered = await self._extraction_service._call_llm(prompt)
            if clustered and clustered.strip():
                logger.info(
                    "multi_cluster:chunk_done idx=%s out_chars=%s elapsed_ms=%s",
                    idx,
                    len(clustered),
                    self._elapsed_ms(started),
                )
                return idx, clustered.strip()
        except Exception as exc:
            logger.exception(
                "multi_cluster:chunk_error idx=%s err=%s elapsed_ms=%s",
                idx,
                exc,
                self._elapsed_ms(started),
            )
        logger.info("multi_cluster:chunk_fallback idx=%s elapsed_ms=%s", idx, self._elapsed_ms(started))
        return idx, chunk_markdown

    @staticmethod
    def _build_cluster_prompt(
        chunk_markdown: str,
        template_keys: List[str],
        template_tree: Optional[Dict] = None,
        min_paragraphs: int = 3,
    ) -> str:
        summary_paragraphs = max(2, min_paragraphs - 1)
        if template_tree:
            template_section = TemplateExtractionMultiFilesService._tree_to_markdown_template(
                template_tree
            )
        else:
            template_section = "\n".join(
                f"## {key}\n<One concise paragraph or null>" for key in template_keys
            )
        print(template_section)
        return f"""## ROLE
        You are an expert in information synthesis and report writing.

        ## GOAL
        Synthesize the input into a comprehensive, detailed report that STRICTLY follows the given template.

        ---

        ## OUTPUT FORMAT (MANDATORY)

        # BÁO CÁO TỔNG HỢP

        {template_section}

        ---

        ## STRICT RULES (CRITICAL)

        - MUST use EXACT section titles as provided above (no renaming, no paraphrasing)
        - HOWEVER:
  Input sections may have DIFFERENT names.
  You MUST map input content to the MOST RELEVANT section based on meaning.
        - DO NOT require keyword match
        - ONLY output null if ABSOLUTELY no relevant information exists
        - If ANY section title is not EXACTLY the same as template → REWRITE it to match exactly.
        - DO NOT add new sections
        - DO NOT remove any section
        - DO NOT merge sections
        - You MUST try to fill EVERY leaf section
        - Prefer approximate mapping over null
        - null is ONLY allowed if absolutely no related information exists

        - Each LEAF section MUST contain at least {min_paragraphs} detailed paragraphs, EXCEPT sections whose title contains summary/conclusion/finalize/final/evaluation/đánh giá/kết luận/tổng kết/tổng hợp/kiến nghị — those need only {summary_paragraphs} paragraphs
        - Each paragraph MUST have 4-8 sentences covering different aspects of the topic — do NOT keep paragraphs short
        - Include all relevant facts, context, background, implications, and details from the input
        - DO NOT make up, invent, fabricate, or assume any data. Use ONLY information that is explicitly present in the input. If the input lacks enough material to reach {min_paragraphs} paragraphs for a section, write only as many paragraphs as the input genuinely supports rather than inventing content
        - Separate paragraphs with a blank line
        - NO bullet points
        - NO explanations about the writing process
        - Vietnamese only

        ---

        ## DEDUP RULES

        - Remove only HIGH-confidence duplicates
        - Prefer more complete and generalizable information
        - Do NOT merge different facts — keep each distinct piece of information

        ---

        ## DETAIL RULES

        - Preserve all specific numbers, dates, names, and figures from the input
        - Do NOT omit supporting context or background information
        - Expand abbreviations when helpful

        ---

        ## INPUT
        {chunk_markdown}
        """

    # =========================
    # HIERARCHICAL JSON OUTPUT
    # =========================

    async def _map_to_json_via_llm(
        self,
        merged_markdown: str,
        template_tree: Dict,
        min_paragraphs: int = 3,
    ) -> Dict[str, Any]:
        """Fill the template scaffold with extracted content by asking the LLM to return JSON directly.

        Bypasses fragile markdown heading-matching.  Falls back to the markdown-parser
        approach if the LLM returns unparseable output.
        """
        scaffold = self._build_scaffold(template_tree)
        scaffold_json = json.dumps(scaffold, ensure_ascii=False, indent=2)
        summary_paragraphs = max(2, min_paragraphs - 1)

        prompt = f"""You are an information extraction expert.

## TASK
Fill the provided JSON template with information extracted from the input document.

## JSON TEMPLATE (structure is FIXED — do NOT rename, add, or remove any key)
{scaffold_json}

## RULES
- Return ONLY valid JSON that exactly matches the template structure
- Keep ALL keys — do not add or omit any
- Fill each leaf (currently null) with at least {min_paragraphs} detailed Vietnamese paragraphs, where each paragraph has 4-8 sentences covering all relevant facts, figures, context, background, and implications from the input — do NOT keep paragraphs short. Separate paragraphs with \n\n. EXCEPTION: if the leaf key contains summary/conclusion/finalize/final/evaluation/đánh giá/kết luận/tổng kết/tổng hợp/kiến nghị, use only {summary_paragraphs} paragraphs
- DO NOT make up, invent, fabricate, or assume any data. Use ONLY information explicitly present in the input. If the input does not contain enough material to reach {min_paragraphs} paragraphs for a key, write only as many paragraphs as the input genuinely supports rather than inventing content
- If no information is available for a key → keep its value as null
- Do NOT wrap the output in markdown code fences
- Do NOT explain

## INPUT
{merged_markdown}

JSON:"""

        raw = await self._extraction_service._call_llm(prompt)

        # Strip optional markdown fences that some models add
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw.strip(), flags=re.MULTILINE)

        try:
            result = json.loads(raw.strip())
            if isinstance(result, dict) and result:
                logger.info("multi_extract:map_to_json_llm_ok keys=%s", len(result))
                return result
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "multi_extract:map_to_json_llm_parse_failed; falling back to markdown parser"
            )

        return self._final_markdown_to_nested_json_with_tree(merged_markdown, template_tree)

    def _final_markdown_to_nested_json_with_tree(
        self, markdown: str, tree: Dict
    ) -> Dict[str, Any]:
        """Parse clustered hierarchical markdown into nested JSON shaped by template tree."""
        scaffold = self._build_scaffold(copy.deepcopy(tree))

        if not markdown or not markdown.strip():
            return scaffold

        parsed = self._unwrap_report_title_wrapper(
            self._parse_hierarchical_markdown(markdown)
        )
        self._fill_scaffold_from_parsed(scaffold, parsed)

        if self._all_leaves_empty(scaffold):
            flat_keys = self._flatten_tree_keys(tree)
            flat_json = self._final_markdown_to_json_with_template(markdown, flat_keys)
            if not self._all_leaves_empty(flat_json):
                return flat_json

        return scaffold

    @staticmethod
    def _parse_hierarchical_markdown(markdown: str) -> Dict[str, Any]:
        """Parse multi-level markdown headings (##, ###, ...) into a nested dict.

        Leaf text is stored as a string value; parent nodes remain dicts.
        """
        root: Dict[str, Any] = {}
        # stack items: (depth, container_dict, key)
        stack: List[Tuple[int, Dict, str]] = []
        # paragraphs collected so far; current paragraph being built
        paragraphs: List[str] = []
        current: List[str] = []

        def _end_paragraph() -> None:
            if current:
                para = re.sub(r"[ \t]+", " ", " ".join(current)).strip()
                if para and para.lower() != "null":
                    paragraphs.append(para)
                current.clear()

        def _flush() -> None:
            nonlocal paragraphs
            _end_paragraph()
            if not stack or not paragraphs:
                paragraphs = []
                return
            _, container, key = stack[-1]
            text = "\n\n".join(paragraphs).strip()
            paragraphs = []
            if text and text.lower() != "null":
                # Only fill if still an empty leaf (not yet populated by a child heading)
                if container.get(key) == {} or container.get(key) is None:
                    container[key] = text

        for raw in markdown.splitlines():
            line = raw.strip()
            if not line:
                # blank line marks a paragraph boundary
                _end_paragraph()
                continue

            if line.startswith("#"):
                _flush()

                depth = len(line) - len(line.lstrip("#"))
                key = line.lstrip("#").strip()
                if not key:
                    continue

                # pop to find the correct parent depth
                while stack and stack[-1][0] >= depth:
                    stack.pop()

                if stack:
                    _, parent_container, parent_key = stack[-1]
                    child = parent_container.get(parent_key)
                    if not isinstance(child, dict):
                        parent_container[parent_key] = {}
                    container = parent_container[parent_key]
                else:
                    container = root

                container.setdefault(key, {})
                stack.append((depth, container, key))
                continue

            if line.startswith("- ") or line.startswith("* "):
                # bullet starts its own paragraph
                _end_paragraph()
                line = line[2:].strip()
            if line.lower() != "null":
                current.append(line)

        _flush()
        return root

    @staticmethod
    def _normalize_key(key: str) -> str:
        """Lowercase, collapse whitespace, strip leading punctuation for fuzzy key matching."""
        key = key.lower().strip()
        key = re.sub(r"[^\w\s]", "", key)
        key = re.sub(r"\s+", " ", key).strip()
        return key

    @classmethod
    def _unwrap_report_title_wrapper(cls, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Promote section children when LLM wraps content under a synthetic report title."""
        if len(parsed) != 1:
            return parsed

        only_key = next(iter(parsed))
        only_val = parsed[only_key]
        if not isinstance(only_val, dict) or not only_val:
            return parsed

        norm = cls._normalize_key(only_key)
        if norm.startswith("báo cáo") or norm in {"tổng hợp", "báo cáo tổng hợp"}:
            return only_val
        return parsed

    @classmethod
    def _all_leaves_empty(cls, data: Dict[str, Any]) -> bool:
        for value in data.values():
            if isinstance(value, dict):
                if not cls._all_leaves_empty(value):
                    return False
            elif isinstance(value, str) and value.strip():
                return False
            elif value is not None:
                return False
        return True

    def _find_nested_parsed_value(self, parsed: Dict[str, Any], norm_key: str) -> Any:
        for key, value in parsed.items():
            if self._normalize_key(key) == norm_key:
                return value
            if isinstance(value, dict):
                found = self._find_nested_parsed_value(value, norm_key)
                if found is not None:
                    return found
        return None

    def _fill_scaffold_from_parsed(self, scaffold: Dict, parsed: Dict) -> None:
        parsed_norm_map = {
            self._normalize_key(k): k for k in parsed.keys()
        }

        for key in scaffold:
            norm_key = self._normalize_key(key)
            scaffold_val = scaffold[key]

            parsed_key = parsed_norm_map.get(norm_key)
            if parsed_key is not None:
                parsed_val = parsed[parsed_key]
            else:
                parsed_val = self._find_nested_parsed_value(parsed, norm_key)

            if parsed_val is None:
                continue

            if isinstance(scaffold_val, dict) and isinstance(parsed_val, dict):
                self._fill_scaffold_from_parsed(scaffold_val, parsed_val)
            elif scaffold_val is None:
                if isinstance(parsed_val, str) and parsed_val.strip():
                    scaffold[key] = parsed_val.strip()
                elif parsed_val and not isinstance(parsed_val, dict):
                    scaffold[key] = parsed_val

    # =========================
    # EXTRACT ONE FILE
    # =========================

    async def _extract_one(
        self,
        file_path: str,
        extraction_prompt: str,
    ) -> Tuple[str, Optional[ExtractionReport], Optional[str]]:
        started = time.perf_counter()
        try:
            async with self._semaphore:
                logger.info("multi_extract:file_start path=%s", file_path)
                report = await self._extraction_service.extract_document(
                    file_path=file_path,
                    extraction_prompt=extraction_prompt,
                )
            logger.info(
                "multi_extract:file_done path=%s failed_chunks=%s elapsed_ms=%s",
                file_path,
                report.failed_chunks,
                self._elapsed_ms(started),
            )
            return file_path, report, None
        except Exception as exc:
            logger.exception(
                "multi_extract:file_error path=%s err=%s elapsed_ms=%s",
                file_path,
                exc,
                self._elapsed_ms(started),
            )
            return file_path, None, str(exc)

    # =========================
    # HELPERS
    # =========================

    @staticmethod
    def _safe_markdown(report: Optional[ExtractionReport]) -> str:
        if report is None:
            logger.info("multi_extract:safe_markdown_none_report")
            return ""
        data = getattr(report, "aggregated_data", {}) or {}
        markdown = data.get("markdown")
        if isinstance(markdown, str):
            logger.info("multi_extract:safe_markdown_ok chars=%s", len(markdown.strip()))
            return markdown.strip()
        logger.info("multi_extract:safe_markdown_missing")
        return ""

    @staticmethod
    def _merge_markdowns(markdowns: List[str]) -> str:
        merged = "\n\n".join(md.strip() for md in markdowns if md and md.strip()).strip()
        logger.info(
            "multi_extract:merge_markdowns inputs=%s output_chars=%s",
            len(markdowns),
            len(merged),
        )
        return merged

    @staticmethod
    def _split_markdown_for_clustering(markdown: str, max_chars: int = 6000) -> List[str]:
        lines = markdown.splitlines()
        chunks: List[str] = []
        current: List[str] = []
        size = 0

        for line in lines:
            line_size = len(line) + 1
            if current and size + line_size > max_chars:
                chunks.append("\n".join(current).strip())
                current = []
                size = 0
            current.append(line)
            size += line_size

        if current:
            chunks.append("\n".join(current).strip())

        out = [c for c in chunks if c]
        logger.info(
            "multi_cluster:split_markdown chars=%s max_chars=%s chunks=%s",
            len(markdown or ""),
            max_chars,
            len(out),
        )
        return out

    # =========================
    # FLAT TEMPLATE (LEGACY)
    # =========================

    @staticmethod
    def _extract_template_keys(template: str) -> List[str]:
        if not template:
            return []
        keys: List[str] = []
        for raw in template.splitlines():
            line = raw.strip()
            if not line.startswith("- "):
                continue
            key = line[2:].strip()
            if key:
                keys.append(key)
        return keys

    @staticmethod
    def _final_markdown_to_json_with_template(
        markdown: str,
        template_keys: List[str],
    ) -> Dict[str, Any]:
        if not markdown or not markdown.strip():
            return {key: None for key in template_keys}

        # When no template keys, derive keys from ## headings in the markdown itself
        if not template_keys:
            keys_from_md: List[str] = [
                line.lstrip("#").strip()
                for line in markdown.splitlines()
                if line.strip().startswith("## ")
            ]
            template_keys = keys_from_md

        result: Dict[str, Any] = {key: None for key in template_keys}
        current_section: Optional[str] = None
        paragraphs: List[str] = []
        current: List[str] = []

        def end_paragraph():
            if current:
                para = re.sub(r"[ \t]+", " ", " ".join(current)).strip()
                if para:
                    paragraphs.append(para)
                current.clear()

        def flush():
            nonlocal current_section, paragraphs
            end_paragraph()
            if current_section in result and paragraphs:
                text = "\n\n".join(paragraphs).strip()
                if text:
                    result[current_section] = text
            paragraphs = []

        for raw in markdown.splitlines():
            line = raw.strip()
            if not line:
                end_paragraph()
                continue

            if line.startswith("## "):
                flush()
                current_section = line[3:].strip()
                continue

            if line.startswith("#"):
                continue

            if line.startswith("- ") or line.startswith("* "):
                end_paragraph()
                line = line[2:].strip()

            if current_section:
                current.append(line)

        flush()
        return result

    @staticmethod
    def _parse_sections_and_facts(markdown: str) -> Dict[str, List[str]]:
        if not markdown:
            return {}

        sections: Dict[str, List[str]] = {}
        current_section = "Thông tin"
        sections.setdefault(current_section, [])

        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("##"):
                current_section = line.lstrip("#").strip() or "Thông tin"
                sections.setdefault(current_section, [])
                continue

            if line.startswith("###"):
                continue

            fact = line[2:].strip() if line.startswith("- ") else line

            if fact:
                sections[current_section].append(fact)

        return {k: v for k, v in sections.items() if v}

    def _render_clustered_markdown(self, section_clusters: Dict[str, List[List[str]]]) -> str:
        if not section_clusters:
            return ""

        lines: List[str] = []
        for section, clusters in section_clusters.items():
            lines.append(f"## {section}")

            non_empty = [c for c in clusters if c]
            if not non_empty:
                lines.append("- null")
                lines.append("")
                continue

            for idx, cluster in enumerate(non_empty, start=1):
                group_name = self._build_group_name(cluster[0])
                lines.append(f"### Nhóm {idx}: {group_name}")
                for fact in cluster:
                    lines.append(f"- {fact}")
                lines.append("")

        return "\n".join(lines).strip()

    @staticmethod
    def _build_group_name(seed_fact: str) -> str:
        fact = (seed_fact or "").strip()
        if not fact:
            return "Thông tin liên quan"
        words = fact.split()
        return " ".join(words[:12]).strip() or "Thông tin liên quan"
