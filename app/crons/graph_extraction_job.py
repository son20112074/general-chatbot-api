"""
Cron job: Process unprocessed files, extract nodes & edges via LLM,
and upsert them into the knowledge graph.

Improvements over original:
- Chunk overlap to avoid losing entities at boundaries
- LLM retry with exponential backoff
- Concurrent chunk processing with semaphore
- Edge upsert (dedup) instead of blind insert
- Shared httpx client per cycle
- Ontology validation of LLM output
- In-memory deduplication across chunks before DB upsert
- Partial failure handling: only mark file extracted when all chunks succeed
"""

import asyncio
import json
import re
import time
import unicodedata
import uuid
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError, root_validator, validator
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.logger import get_logger
from app.domain.models.edge import Edge
from app.domain.models.file import ExtractionState, File
from app.domain.models.node import Node

logger = get_logger()

# How many files to process per cycle
BATCH_SIZE = 10

# Chunk size for splitting content
CHUNK_SIZE = 10000
CHUNK_OVERLAP = 1000

# Max concurrent LLM calls per file
MAX_CONCURRENT_CHUNKS = 3

# Retry config
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0

# ── Allowed ontology types (for validation) ──
VALID_ENTITY_TYPES = frozenset(
    {
        "Cá_nhân",
        "Quốc_gia",
        "Tổ_chức",
        "Sự_kiện",
        "Địa_điểm",
        "Vũ_khí",
        "Công_nghệ",
    }
)

VALID_EDGE_TYPES = frozenset(
    {
        "THAM_GIA",
        "NHẮC_ĐẾN",
        "HOẠT_ĐỘNG_TẠI",
        "TƯƠNG_TÁC_VỚI",
        "NẰM_TẠI",
        "PHÁT_TRIỂN",
        "MUA_SẮM",
        "LIÊN_QUAN",
    }
)

# ── LLM System Prompt ──
EXTRACTION_SYSTEM_PROMPT = """\
Bạn là một extractor để trích xuất thực thể và mối quan hệ cho đồ thị tri thức. Cho một đoạn văn bản (chunk) và định nghĩa ontology RÕ RÀNG bằng tiếng Việt, hãy trích xuất TẤT CẢ thực thể và mối quan hệ có trong đoạn văn.

    PHẢI tuân thủ chính xác ontology được cung cấp. KHÔNG tạo loại thực thể hay loại mối quan hệ ngoài ontology. Nếu một mối quan hệ không khớp bất kỳ loại nào, hãy ghi `LIÊN_QUAN` để giữ tính kết nối.

Chỉ trả về JSON hợp lệ (không kèm diễn giải, không kèm fenced code blocks). Trường `name` PHẢI là dạng chính tắc (canonical) — tên chuẩn, không viết tắt.

Ví dụ định dạng JSON trả về:

```json
{
    "entities": [
        {
            "name": "Ví dụ: Hoa Kỳ",
            "type": "Quốc_gia",
            "attributes": {"khu_vực": "Bắc Mỹ", "mã_quốc_gia": "US"}
        }
    ],
    "relationships": [
        {
            "source": "Hoa Kỳ",
            "source_type": "Quốc_gia",
            "target": "Phòng thí nghiệm X",
            "target_type": "Tổ_chức",
            "type": "MUA_SẮM",
            "fact": "Mua công nghệ Y vào năm 2022"
        }
    ]
}
```

Ghi nhớ:
- Chỉ dùng các `Entity` và `Relationship` trong ontology được cung cấp.
- Tên thực thể phải ở dạng chính tắc (ví dụ: sử dụng "Hoa Kỳ" thay vì "Mỹ" nếu chuẩn hóa như vậy).
- Nếu không có thực thể hay mối quan hệ phù hợp, trả mảng rỗng tương ứng.
"""

# ── Ontology ──
ONTOLOGY_DESC = """\
Loại thực thể (CHỈ DÙNG NHỮNG LOẠI NÀY):
    - Cá_nhân: Cá nhân attrs=[vai_trò, quốc_tịch, chức_danh]
    - Quốc_gia: Quốc gia attrs=[khu_vực, mã_quốc_gia]
    - Tổ_chức: Công ty, cơ quan, tổ chức attrs=[loại_hình, quốc_gia, lĩnh_vực]
    - Sự_kiện: Sự kiện/chiến dịch/biến cố attrs=[loại_hình, ngày_tháng, trạng_thái]
    - Địa_điểm: Địa điểm (thành phố, cơ sở, cơ quan) attrs=[loại_hình, tọa_độ]
    - Vũ_khí: Vũ khí/đạn dược attrs=[loại, cỡ_nòng, tầm_bắn]
    - Công_nghệ: Hệ thống/công nghệ attrs=[loại, danh_mục, trạng_thái]

Loại mối quan hệ (CHỈ DÙNG NHỮNG LOẠI NÀY — nếu không phân loại được, dùng `LIÊN_QUAN`):
    - THAM_GIA: Tham gia vào sự kiện (Cá_nhân→Sự_kiện, Tổ_chức→Sự_kiện)
    - NHẮC_ĐẾN: Tài liệu/đoạn văn đề cập đến thực thể (Document→Entity)
    - HOẠT_ĐỘNG_TẠI: Hoạt động tại địa điểm/quốc gia (Tổ_chức→Địa_điểm, Cá_nhân→Quốc_gia)
    - TƯƠNG_TÁC_VỚI: Tương tác giữa các thực thể (Cá_nhân↔Tổ_chức, Quốc_gia↔Quốc_gia)
    - NẰM_TẠI: Thuộc vị trí (Tổ_chức→Địa_điểm, Địa_điểm→Quốc_gia)
    - PHÁT_TRIỂN: Phát triển công nghệ/vũ_khí (Tổ_chức→Công_nghệ)
    - MUA_SẮM: Mua bán/thu mua (Quốc_gia→Vũ_khí, Tổ_chức→Công_nghệ)
"""

# File-level retry cap for marking FAILED
FILE_MAX_RETRIES = 3

# Simple alias map to canonicalize common country names (extend as needed)
ALIAS_MAP = {
    "Mỹ": "Hoa Kỳ",
    "US": "Hoa Kỳ",
    "USA": "Hoa Kỳ",
    "United States": "Hoa Kỳ",
}


# ---------------------------------------------------------------------------
# LLM helper – calls the OpenAI-compatible API for JSON extraction
# ---------------------------------------------------------------------------


async def _llm_chat_json(
    http_client: httpx.AsyncClient,
    messages: list[dict[str, str]],
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Call the LLM API and return parsed JSON. Uses shared http_client."""
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    base_url = settings.LLM_API.rstrip("/")
    response = await http_client.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=payload,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"LLM API error ({response.status_code}): {response.text[:500]}"
        )

    result = response.json()
    raw = result["choices"][0]["message"]["content"] or ""

    # Strip <think> blocks and markdown fences
    raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\n?```\s*$", "", raw)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(f"LLM returned invalid JSON: {raw[:500]}")


async def _llm_chat_json_with_retry(
    http_client: httpx.AsyncClient,
    messages: list[dict[str, str]],
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Call LLM with retry and exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            return await _llm_chat_json(http_client, messages, temperature, max_tokens)
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "LLM call failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Ontology validation
# ---------------------------------------------------------------------------


def canonicalize_name(name: str) -> str:
    """Normalize and map common aliases to canonical names."""
    if not name:
        return name
    n = unicodedata.normalize("NFC", str(name)).strip()
    n = re.sub(r"\s+", " ", n)
    mapped = ALIAS_MAP.get(n)
    if not mapped:
        # case-insensitive alias lookup
        for k, v in ALIAS_MAP.items():
            if n.lower() == k.lower():
                mapped = v
                break
    return mapped or n


class EntitySchema(BaseModel):
    name: str
    type: str
    attributes: dict[str, Any] = Field(default_factory=dict)

    @validator("name")
    def name_must_be_nonempty(cls, v: str) -> str:
        v2 = canonicalize_name(v or "")
        if not v2:
            raise ValueError("empty name")
        return v2

    @validator("type")
    def type_must_be_allowed(cls, v: str) -> str:
        vt = (v or "").strip()
        if vt not in VALID_ENTITY_TYPES:
            raise ValueError(f"Invalid entity type: {vt}")
        return vt


class RelationshipSchema(BaseModel):
    source: str
    source_type: str
    target: str
    target_type: str
    type: str
    fact: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @validator("source", "target")
    def normalize_entity_name(cls, v: str) -> str:
        v2 = canonicalize_name(v or "")
        if not v2:
            raise ValueError("empty source/target")
        return v2

    @validator("source_type", "target_type")
    def entity_types_must_be_allowed(cls, v: str) -> str:
        vt = (v or "").strip()
        return vt

    @root_validator(skip_on_failure=True)
    def at_least_one_entity_type_allowed(cls, values: dict[str, Any]) -> dict[str, Any]:
        src_t = (values.get("source_type") or "").strip()
        tgt_t = (values.get("target_type") or "").strip()
        # Accept relationship if either side matches a known entity type
        if src_t in VALID_ENTITY_TYPES or tgt_t in VALID_ENTITY_TYPES:
            return values
        raise ValueError(
            f"Neither source_type ({src_t}) nor target_type ({tgt_t}) is a valid entity type"
        )

    @validator("type")
    def edge_type_or_fallback(cls, v: str) -> str:
        vt = (v or "").strip()
        if vt not in VALID_EDGE_TYPES:
            logger.warning("Mapping edge type %r to LIÊN_QUAN", vt)
            return "LIÊN_QUAN"
        return vt


class ExtractionResponse(BaseModel):
    entities: list[EntitySchema] = Field(default_factory=list)
    relationships: list[RelationshipSchema] = Field(default_factory=list)


def _validate_extracted(extracted: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize LLM output using Pydantic models.

    - Keeps valid items
    - Drops invalid ones
    - Logs errors per item
    """
    extracted = extracted or {}

    raw_entities = extracted.get("entities", []) or []
    raw_relationships = extracted.get("relationships", []) or []

    valid_entities: List[Dict[str, Any]] = []
    valid_relationships: List[Dict[str, Any]] = []

    # Validate entities individually
    for i, ent in enumerate(raw_entities):
        try:
            obj = EntitySchema.parse_obj(ent)
            valid_entities.append(obj.dict())
        except ValidationError as e:
            logger.warning("Invalid entity at index %s: %s | data=%s", i, e, ent)

    # Validate relationships individually
    for i, rel in enumerate(raw_relationships):
        try:
            obj = RelationshipSchema.parse_obj(rel)
            valid_relationships.append(obj.dict())
        except ValidationError as e:
            logger.warning("Invalid relationship at index %s: %s | data=%s", i, e, rel)

    return {
        "entities": valid_entities,
        "relationships": valid_relationships,
    }


# ---------------------------------------------------------------------------
# In-memory deduplication across chunks
# ---------------------------------------------------------------------------


def _deduplicate_results(all_extracted: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge and deduplicate entities/relationships from multiple chunks."""
    # Deduplicate entities by (name, type) — merge attributes
    entity_map: dict[tuple[str, str], dict[str, Any]] = {}
    for extracted in all_extracted:
        for ent in extracted.get("entities", []):
            name = (ent.get("name") or "").strip()
            etype = (ent.get("type") or "Entity").strip()
            if not name:
                continue
            key = (name, etype)
            if key in entity_map:
                existing_attrs = dict(entity_map[key].get("attributes") or {})
                new_attrs = dict(ent.get("attributes") or {})
                # Merge: new values override only if non-empty
                merged = {**existing_attrs}
                for k, v in new_attrs.items():
                    if v not in (None, "", []):
                        merged[k] = v
                entity_map[key]["attributes"] = merged
            else:
                entity_map[key] = ent

    # Deduplicate relationships by (source, source_type, target, target_type, type)
    rel_map: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for extracted in all_extracted:
        for rel in extracted.get("relationships", []):
            src = (rel.get("source") or "").strip()
            src_t = (rel.get("source_type") or "").strip()
            tgt = (rel.get("target") or "").strip()
            tgt_t = (rel.get("target_type") or "").strip()
            rtype = (rel.get("type") or "").strip()
            if not src or not tgt:
                continue
            key = (src, src_t, tgt, tgt_t, rtype)
            if key not in rel_map:
                rel_map[key] = rel

    return {
        "entities": list(entity_map.values()),
        "relationships": list(rel_map.values()),
    }


# ---------------------------------------------------------------------------
# Text splitting (with overlap)
# ---------------------------------------------------------------------------


def _split_content(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split text into chunks with overlap.

    Prefer splitting at double newlines or sentence boundaries so we don't cut
    in the middle of a sentence or named entity.
    """
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    text_len = len(text)
    sentence_break_pattern = re.compile(r"(?<=[\.\?!\…])\s+")

    while start < text_len:
        end = min(start + chunk_size, text_len)
        if end >= text_len:
            chunks.append(text[start:].strip())
            break

        # Prefer paragraph break
        break_at = text.rfind("\n\n", start, end)
        if break_at <= start:
            # Try sentence boundary (last match before `end`)
            candidates = [
                m.end() for m in sentence_break_pattern.finditer(text, start, end)
            ]
            if candidates:
                break_at = candidates[-1]
            else:
                # Fall back to last newline
                nl = text.rfind("\n", start, end)
                break_at = nl if nl > start else end

        chunk = text[start:break_at].strip()
        if chunk:
            chunks.append(chunk)

        # Advance with overlap
        next_start = max(break_at - overlap, start + 1)
        start = next_start

    return chunks


# ---------------------------------------------------------------------------
# Upsert nodes & edges (with edge dedup)
# ---------------------------------------------------------------------------


async def _upsert_nodes_edges(
    session: AsyncSession,
    doc_file: File,
    extracted: dict[str, Any],
) -> tuple[int, int]:
    """Bulk upsert nodes and edges for a given file extraction.

    This implementation performs a single bulk upsert for nodes (including the
    Document node) and a single bulk upsert for edges (including NHẮC_ĐẾN
    mention edges). It builds an in-memory map of (name, type) -> id using
    the `RETURNING` clause so no SELECTs are executed inside loops.
    """
    node_count = 0
    edge_count = 0

    # Document node name
    file_name = (
        doc_file.name
        if doc_file and getattr(doc_file, "name", None)
        else f"file:{getattr(doc_file, 'id', 'unknown')}"
    )

    # Build unique set of nodes to upsert: Document + extracted entities
    nodes_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    nodes_by_key[(file_name, "Document")] = {
        "id": uuid.uuid4(),
        "name": file_name,
        "entity_type": "Document",
        "attributes": {"file_name": file_name},
    }

    for ent in extracted.get("entities", []):
        name = ent.get("name") or ""
        etype = ent.get("type") or ""
        if not name or not etype:
            continue
        key = (name, etype)
        attrs = dict(ent.get("attributes") or {})
        if key in nodes_by_key:
            # merge attributes
            existing = nodes_by_key[key].get("attributes") or {}
            merged = {**existing}
            for k, v in attrs.items():
                if v not in (None, "", []):
                    merged[k] = v
            nodes_by_key[key]["attributes"] = merged
        else:
            nodes_by_key[key] = {
                "id": uuid.uuid4(),
                "name": name,
                "entity_type": etype,
                "attributes": attrs,
            }

    # build nodes from relationships (in case they weren't in entities list)
    # just create if one of source/target types matches a known entity type; otherwise skip
    # for eg:
    # - valid_node - valid_or_invalid_relationshiop - valid_node
    # - valid_node - valid_or_invalid_relationship - invalid_node
    for rel in extracted.get("relationships", []):
        src_name = rel.get("source") or ""
        src_type = rel.get("source_type") or ""
        tgt_name = rel.get("target") or ""
        tgt_type = rel.get("target_type") or ""

        # if one of source/target is valid type,
        # we create nodes for both (even if the other type is invalid) to preserve connectivity in the graph;
        # the invalid type will just be stored as-is and can be cleaned up later
        if src_type in VALID_ENTITY_TYPES or tgt_type in VALID_ENTITY_TYPES:

            if src_name and src_type:
                key = (src_name, src_type)
                if key not in nodes_by_key:
                    nodes_by_key[key] = {
                        "id": uuid.uuid4(),
                        "name": src_name,
                        "entity_type": src_type,
                        "attributes": {},
                    }

            if tgt_name and tgt_type:
                key = (tgt_name, tgt_type)
                if key not in nodes_by_key:
                    nodes_by_key[key] = {
                        "id": uuid.uuid4(),
                        "name": tgt_name,
                        "entity_type": tgt_type,
                        "attributes": {},
                    }

    node_values = list(nodes_by_key.values())

    id_map: dict[tuple[str, str], Any] = {}
    if node_values:
        stmt_nodes = pg_insert(Node).values(node_values)
        stmt_nodes = stmt_nodes.on_conflict_do_update(
            constraint="uq_node_name_type",
            set_={"attributes": Node.attributes + stmt_nodes.excluded.attributes},
        )
        stmt_nodes = stmt_nodes.returning(Node.name, Node.entity_type, Node.id)
        res = await session.execute(stmt_nodes)
        rows = res.fetchall()
        for row in rows:
            mapping = row._mapping
            id_map[(mapping["name"], mapping["entity_type"])] = mapping["id"]
        node_count = len(node_values)

    # Build edge rows in memory using id_map
    edge_values: list[dict[str, Any]] = []
    for rel in extracted.get("relationships", []):
        src_key = (rel.get("source"), rel.get("source_type"))
        tgt_key = (rel.get("target"), rel.get("target_type"))
        src_id = id_map.get(src_key)
        tgt_id = id_map.get(tgt_key)
        if not src_id or not tgt_id:
            # skip edges where either node wasn't upserted/found
            continue
        edge_values.append(
            {
                "id": uuid.uuid4(),
                "source_node_id": src_id,
                "target_node_id": tgt_id,
                        "edge_type": (rel.get("type") or "LIÊN_QUAN"),
                "fact": rel.get("fact") or "",
                "attributes": rel.get("attributes") or {},
            }
        )

    # Mentions (NHẮC_ĐẾN) edges from document node -> each entity node
    doc_id = id_map.get((file_name, "Document"))
    if doc_id:
        for (name, etype), node in nodes_by_key.items():
            if (name, etype) == (file_name, "Document"):
                continue
            ent_id = id_map.get((name, etype))
            if not ent_id:
                continue
            edge_values.append(
                {
                    "id": uuid.uuid4(),
                    "source_node_id": doc_id,
                    "target_node_id": ent_id,
                    "edge_type": "NHẮC_ĐẾN",
                    "fact": f"Nhắc trong {file_name}",
                    "attributes": {},
                }
            )

    if edge_values:
        stmt_edges = pg_insert(Edge).values(edge_values)
        stmt_edges = stmt_edges.on_conflict_do_update(
            constraint="uq_edge_src_tgt_type",
            set_={
                "fact": stmt_edges.excluded.fact,
                "attributes": stmt_edges.excluded.attributes,
            },
        )
        await session.execute(stmt_edges)
        edge_count = len(edge_values)

    await session.flush()
    return node_count, edge_count


# ---------------------------------------------------------------------------
# Process a single file
# ---------------------------------------------------------------------------


async def _extract_chunk(
    http_client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    chunk: str,
    chunk_idx: int,
    total_chunks: int,
    file_id: int,
    file_name: str,
) -> dict[str, Any] | None:
    """Extract entities/relationships from a single chunk with concurrency control."""
    async with semaphore:
        try:
            user_msg = (
                f"## Ontology (VI)\n{ONTOLOGY_DESC}\n\n"
                f"## Văn bản (chunk)\n{chunk}\n\n"
                "Vui lòng trả về đúng JSON theo mẫu trong 'system prompt'. Trường `name` phải ở dạng chính tắc."
            )
            extracted_raw = await _llm_chat_json_with_retry(
                http_client,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=4096,
            )
            if not isinstance(extracted_raw, dict):
                logger.warning(
                    "Chunk %d/%d for file %d (%s) returned non-dict LLM response",
                    chunk_idx + 1,
                    total_chunks,
                    file_id,
                    file_name,
                )
                return None
            extracted_raw.setdefault("entities", [])
            extracted_raw.setdefault("relationships", [])
            validated = _validate_extracted(extracted_raw)
            return validated
        except Exception:
            logger.exception(
                "Failed to process chunk %d/%d for file %d (%s) after %d retries",
                chunk_idx + 1,
                total_chunks,
                file_id,
                file_name,
                MAX_RETRIES,
            )
            return None


async def _process_single_file(
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    doc_file: File,
) -> None:
    """Process one file: extract nodes/edges from content via LLM."""
    start_time = time.time()
    content = getattr(doc_file, "content", "") or ""
    if not isinstance(content, str) or not content.strip():
        logger.info(
            "File %d (%s) has empty content, skipping", doc_file.id, doc_file.name
        )
        return

    chunks = _split_content(content)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHUNKS)

    # Process all chunks concurrently
    tasks = [
        _extract_chunk(
            http_client,
            semaphore,
            chunk,
            i,
            len(chunks),
            getattr(doc_file, "id", 0) or 0,
            getattr(doc_file, "name", "") or "",
        )
        for i, chunk in enumerate(chunks)
    ]
    results = await asyncio.gather(*tasks)

    # Check for partial failures — don't mark as extracted if any chunk failed
    failed_chunks = [i for i, r in enumerate(results) if r is None]
    successful_results = [r for r in results if r is not None]

    if failed_chunks:
        logger.warning(
            "File %d (%s): %d/%d chunks failed — will NOT mark as extracted",
            doc_file.id,
            doc_file.name,
            len(failed_chunks),
            len(chunks),
        )

    if not successful_results:
        logger.error(
            "File %d (%s): all chunks failed, skipping DB upsert",
            doc_file.id,
            doc_file.name,
        )
        # Increment attempt counter and set PENDING or FAILED
        cur_attempts = (
            await session.execute(
                select(File.extraction_attempts).where(File.id == doc_file.id)
            )
        ).scalar_one_or_none() or 0
        if cur_attempts + 1 >= FILE_MAX_RETRIES:
            await session.execute(
                update(File)
                .where(File.id == doc_file.id)
                .values(
                    extraction_state=ExtractionState.FAILED,
                    extraction_attempts=cur_attempts + 1,
                )
            )
        else:
            await session.execute(
                update(File)
                .where(File.id == doc_file.id)
                .values(
                    extraction_state=ExtractionState.PENDING,
                    extraction_attempts=cur_attempts + 1,
                )
            )
        return

    # Deduplicate across all chunks, then upsert once
    merged = _deduplicate_results(successful_results)

    total_nodes, total_edges = await _upsert_nodes_edges(
        session,
        doc_file,
        merged,
    )

    duration = int(time.time() - start_time)

    # Only mark as done if ALL chunks succeeded
    if not failed_chunks:
        await session.execute(
            update(File)
            .where(File.id == doc_file.id)
            .values(extraction_state=ExtractionState.DONE, extraction_attempts=0)
        )
    else:
        # partial failure: increment attempt counter and set PENDING or FAILED
        cur_attempts = (
            await session.execute(
                select(File.extraction_attempts).where(File.id == doc_file.id)
            )
        ).scalar_one_or_none() or 0
        if cur_attempts + 1 >= FILE_MAX_RETRIES:
            await session.execute(
                update(File)
                .where(File.id == doc_file.id)
                .values(
                    extraction_state=ExtractionState.FAILED,
                    extraction_attempts=cur_attempts + 1,
                )
            )
        else:
            await session.execute(
                update(File)
                .where(File.id == doc_file.id)
                .values(
                    extraction_state=ExtractionState.PENDING,
                    extraction_attempts=cur_attempts + 1,
                )
            )

    logger.info(
        "Processed file %d (%s): %d nodes, %d edges in %ds (chunks: %d ok, %d failed)",
        doc_file.id,
        doc_file.name,
        total_nodes,
        total_edges,
        duration,
        len(successful_results),
        len(failed_chunks),
    )


# ---------------------------------------------------------------------------
# One extraction cycle
# ---------------------------------------------------------------------------


async def _run_extraction_cycle() -> int:
    """
    Fetch unprocessed files, extract graph data, upsert.
    Returns number of files processed.
    """
    async with httpx.AsyncClient(timeout=300.0) as http_client:
        async with get_db_session() as session:
            result = await session.execute(
                select(File)
                .where(
                    File.extraction_state == ExtractionState.PENDING,
                    File.content.isnot(None),
                    File.content != "",
                    File.is_deleted.isnot(True),
                )
                .limit(BATCH_SIZE)
            )
            files = result.scalars().all()

            if not files:
                return 0

            processed = 0
            for doc_file in files:
                try:
                    # Atomically claim the file by setting extraction_state -> 'processing'
                    res = await session.execute(
                        update(File)
                        .where(
                            File.id == doc_file.id,
                            File.extraction_state == ExtractionState.PENDING,
                        )
                        .values(extraction_state=ExtractionState.PROCESSING)
                        .returning(File.id)
                    )
                    claimed = res.scalar_one_or_none()
                    if not claimed:
                        # someone else claimed it in the meantime
                        continue
                    # persist the claim
                    await session.commit()

                    try:
                        await _process_single_file(session, http_client, doc_file)
                        await session.commit()
                        processed += 1
                    except Exception:
                        logger.exception(
                            "Failed to process file %d (%s)", doc_file.id, doc_file.name
                        )
                        # reset state to pending so it can be retried
                        try:
                            await session.execute(
                                update(File)
                                .where(File.id == doc_file.id)
                                .values(extraction_state=ExtractionState.PENDING)
                            )
                            await session.commit()
                        except Exception:
                            await session.rollback()
                except Exception:
                    logger.exception(
                        "Claiming or processing failed for file %s",
                        getattr(doc_file, "id", "?"),
                    )

    return processed


# ---------------------------------------------------------------------------
# Entry point – called by APScheduler
# ---------------------------------------------------------------------------


async def graph_extraction_job():
    """APScheduler job: extract knowledge graph from unprocessed files."""
    try:
        count = await _run_extraction_cycle()
        if count > 0:
            logger.info(
                "[CronJob] Graph extraction cycle complete: processed %d files", count
            )
    except Exception:
        logger.exception("[CronJob] Graph extraction cycle failed")


async def _run_forever() -> None:
    """Single event loop: asyncio.run() must not be called in a tight loop (closes the loop each time)."""
    while True:
        await graph_extraction_job()
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(_run_forever())
