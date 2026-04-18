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
import uuid
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.logger import get_logger
from app.domain.models.edge import Edge
from app.domain.models.file import File
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
VALID_ENTITY_TYPES = frozenset({
    "Person", "Country", "Organization", "Event",
    "Location", "Weapon", "Technology", "Document",
})
VALID_EDGE_TYPES = frozenset({
    "PARTICIPATES_IN", "MENTIONS", "OPERATES_IN", "INTERACTS_WITH",
    "LOCATED_IN", "DEVELOPS", "PURCHASE",
})

# ── LLM System Prompt ──
EXTRACTION_SYSTEM_PROMPT = """\
You are a knowledge-graph entity extractor. Given a text chunk and a STRICT \
ontology definition, extract all entities and relationships present in the text.

You MUST follow the predefined ontology EXACTLY. Do NOT create entity types or \
relationship types outside the ontology. If something does not fit any ontology \
type, SKIP it.

**Output valid JSON only.**

```json
{
  "entities": [
    {
      "name": "Entity Name (canonical form)",
      "type": "EntityType (MUST match one of the ontology entity types exactly)",
      "attributes": {"attr_name": "value", ...}
    }
  ],
  "relationships": [
    {
      "source": "Source Entity Name",
      "source_type": "SourceEntityType",
      "target": "Target Entity Name",
      "target_type": "TargetEntityType",
      "type": "RELATIONSHIP_TYPE (MUST match one of the ontology edge types exactly)",
      "fact": "A brief factual sentence describing this relationship"
    }
  ]
}
```

Rules:
- ONLY use entity types and relationship types defined in the ontology. No exceptions.
- Entity names must be in canonical form (e.g. full name for persons, official name for organizations).
- Extract ALL entities and relationships you can find, including implicit ones.
- Do NOT invent information not present in the text.
- If an entity could match multiple types, choose the most specific type.
- Return an empty entities/relationships array if nothing in the text matches the ontology.
"""

# ── Ontology ──
ONTOLOGY_DESC = """\
Entity types (USE ONLY THESE — reject anything that does not fit):
  - Person: An individual person  attrs=[role, nationality, title]
  - Country: A sovereign nation or state  attrs=[region, code]
  - Organization: A company, government body, military branch, NGO, or any formal group  attrs=[type, country, sector]
  - Event: A significant occurrence, incident, operation, or meeting  attrs=[type, date, status]
  - Location: A geographic place (city, region, base, facility, landmark)  attrs=[type, country, coordinates]
  - Weapon: A weapon, munition, or armament system  attrs=[type, caliber, range, manufacturer, designation]
  - Technology: A technology, system, platform, software, or technical capability  attrs=[type, category, manufacturer, status]
  - Document: A report, treaty, agreement, publication, or official record  attrs=[type, date, classification, author]

Relationship types (USE ONLY THESE — reject anything that does not fit):
  - PARTICIPATES_IN: An entity participates in an event or activity  (Person→Event, Organization→Event, Country→Event)
  - MENTIONS: A document mentions an entity  (Document→Person, Document→Organization, Document→Event, Document→Location, Document→Country, Document→Weapon, Document→Technology)
  - OPERATES_IN: An entity operates in a location or country  (Organization→Location, Organization→Country, Person→Location, Person→Country)
  - INTERACTS_WITH: An entity interacts with another entity  (Person→Person, Organization→Organization, Person→Organization, Country→Country, Country→Organization)
  - LOCATED_IN: An entity is located in a place  (Organization→Location, Organization→Country, Location→Country, Event→Location, Weapon→Location, Technology→Location)
  - DEVELOPS: An entity develops a technology, weapon, or document  (Organization→Technology, Organization→Weapon, Person→Technology, Person→Document, Organization→Document)
  - PURCHASE: An entity purchases from another entity  (Country→Weapon, Country→Technology, Organization→Weapon, Organization→Technology)
"""


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
    payload = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    response = await http_client.post(
        f"{settings.LLM_API}/v1/chat/completions",
        headers=headers,
        json=payload,
    )

    if response.status_code != 200:
        raise RuntimeError(f"LLM API error ({response.status_code}): {response.text[:500]}")

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
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "LLM call failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1, MAX_RETRIES, delay, exc,
                )
                await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Ontology validation
# ---------------------------------------------------------------------------

def _validate_extracted(extracted: dict[str, Any]) -> dict[str, Any]:
    """Filter out entities/relationships that don't match the ontology."""
    valid_entities = []
    for ent in extracted.get("entities", []):
        etype = (ent.get("type") or "").strip()
        if etype not in VALID_ENTITY_TYPES:
            logger.warning("Dropping entity with invalid type %r: %s", etype, ent.get("name"))
            continue
        valid_entities.append(ent)

    valid_rels = []
    for rel in extracted.get("relationships", []):
        rtype = (rel.get("type") or "").strip()
        if rtype not in VALID_EDGE_TYPES:
            logger.warning("Dropping relationship with invalid type %r", rtype)
            continue
        src_type = (rel.get("source_type") or "").strip()
        tgt_type = (rel.get("target_type") or "").strip()
        if src_type not in VALID_ENTITY_TYPES or tgt_type not in VALID_ENTITY_TYPES:
            logger.warning("Dropping relationship with invalid entity types: %s→%s", src_type, tgt_type)
            continue
        valid_rels.append(rel)

    return {"entities": valid_entities, "relationships": valid_rels}


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
                existing_attrs = entity_map[key].get("attributes") or {}
                new_attrs = ent.get("attributes") or {}
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
    """Split text into chunks with overlap, breaking at paragraph boundaries."""
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:])
            break
        break_at = text.rfind("\n\n", start, end)
        if break_at == -1 or break_at <= start:
            break_at = text.rfind("\n", start, end)
        if break_at == -1 or break_at <= start:
            break_at = end
        chunks.append(text[start:break_at])
        # Move forward by (break position - overlap), ensuring progress
        next_start = max(break_at - overlap, start + 1)
        start = next_start
    return [c.strip() for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# Upsert nodes & edges (with edge dedup)
# ---------------------------------------------------------------------------

async def _upsert_nodes_edges(
    session: AsyncSession,
    file_id: int,
    extracted: dict[str, Any],
) -> tuple[int, int]:
    """Upsert entities and relationships into nodes/edges with file_id."""
    node_count = 0
    edge_count = 0

    # ── Upsert nodes ──
    for ent in extracted.get("entities", []):
        name = (ent.get("name") or "").strip()
        etype = (ent.get("type") or "Entity").strip()
        if not name:
            continue

        stmt = pg_insert(Node).values(
            id=uuid.uuid4(),
            file_id=file_id,
            name=name,
            entity_type=etype,
            attributes=ent.get("attributes") or {},
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_node_name_type",
            set_={
                "attributes": Node.attributes + stmt.excluded.attributes,
                "file_id": file_id,
            },
        )
        await session.execute(stmt)
        node_count += 1

    await session.flush()

    # ── Upsert edges (deduplicated) ──
    for rel in extracted.get("relationships", []):
        src_name = (rel.get("source") or "").strip()
        src_type = (rel.get("source_type") or "Entity").strip()
        tgt_name = (rel.get("target") or "").strip()
        tgt_type = (rel.get("target_type") or "Entity").strip()
        if not src_name or not tgt_name:
            continue

        # Look up source node
        src_row = (await session.execute(
            select(Node).where(
                Node.name == src_name,
                Node.entity_type == src_type,
            )
        )).scalar_one_or_none()

        # Look up target node
        tgt_row = (await session.execute(
            select(Node).where(
                Node.name == tgt_name,
                Node.entity_type == tgt_type,
            )
        )).scalar_one_or_none()

        # Auto-create nodes if missing
        if not src_row:
            src_row = Node(
                file_id=file_id,
                name=src_name, entity_type=src_type,
            )
            session.add(src_row)
            await session.flush()
        if not tgt_row:
            tgt_row = Node(
                file_id=file_id,
                name=tgt_name, entity_type=tgt_type,
            )
            session.add(tgt_row)
            await session.flush()

        edge_type = (rel.get("type") or "RELATED_TO").strip()
        fact = (rel.get("fact") or "")
        attrs = rel.get("attributes") or {}

        stmt = pg_insert(Edge).values(
            id=uuid.uuid4(),
            file_id=file_id,
            source_node_id=src_row.id,
            target_node_id=tgt_row.id,
            edge_type=edge_type,
            fact=fact,
            attributes=attrs,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_edge_src_tgt_type",
            set_={
                "fact": stmt.excluded.fact,
                "attributes": stmt.excluded.attributes,
                "file_id": file_id,
            },
        )
        await session.execute(stmt)
        edge_count += 1

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
                f"## Ontology (STRICT — use ONLY these types)\n{ONTOLOGY_DESC}\n\n"
                f"## Text chunk\n{chunk}\n\n"
                "Extract all entities and relationships from this text. "
                "Use ONLY the entity types and relationship types defined in the ontology above. "
                "Skip anything that does not fit the ontology."
            )
            extracted = await _llm_chat_json_with_retry(
                http_client,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=4096,
            )
            extracted.setdefault("entities", [])
            extracted.setdefault("relationships", [])
            return _validate_extracted(extracted)
        except Exception:
            logger.exception(
                "Failed to process chunk %d/%d for file %d (%s) after %d retries",
                chunk_idx + 1, total_chunks, file_id, file_name, MAX_RETRIES,
            )
            return None


async def _process_single_file(
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    doc_file: File,
) -> None:
    """Process one file: extract nodes/edges from content via LLM."""
    start_time = time.time()
    content = doc_file.content or ""
    if not content.strip():
        logger.info("File %d (%s) has empty content, skipping", doc_file.id, doc_file.name)
        return

    chunks = _split_content(content)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHUNKS)

    # Process all chunks concurrently
    tasks = [
        _extract_chunk(http_client, semaphore, chunk, i, len(chunks), doc_file.id, doc_file.name)
        for i, chunk in enumerate(chunks)
    ]
    results = await asyncio.gather(*tasks)

    # Check for partial failures — don't mark as extracted if any chunk failed
    failed_chunks = [i for i, r in enumerate(results) if r is None]
    successful_results = [r for r in results if r is not None]

    if failed_chunks:
        logger.warning(
            "File %d (%s): %d/%d chunks failed — will NOT mark as extracted",
            doc_file.id, doc_file.name, len(failed_chunks), len(chunks),
        )

    if not successful_results:
        logger.error("File %d (%s): all chunks failed, skipping DB upsert", doc_file.id, doc_file.name)
        return

    # Deduplicate across all chunks, then upsert once
    merged = _deduplicate_results(successful_results)

    total_nodes, total_edges = await _upsert_nodes_edges(
        session, doc_file.id, merged,
    )

    duration = int(time.time() - start_time)

    # Only mark as extracted if ALL chunks succeeded
    if not failed_chunks:
        await session.execute(
            update(File)
            .where(File.id == doc_file.id)
            .values(is_graph_extracted=True)
        )

    logger.info(
        "Processed file %d (%s): %d nodes, %d edges in %ds (chunks: %d ok, %d failed)",
        doc_file.id, doc_file.name, total_nodes, total_edges, duration,
        len(successful_results), len(failed_chunks),
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
                    File.is_graph_extracted.isnot(True),
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
                    await _process_single_file(session, http_client, doc_file)
                    await session.commit()
                    processed += 1
                except Exception:
                    logger.exception("Failed to process file %d (%s)", doc_file.id, doc_file.name)
                    await session.rollback()

    return processed


# ---------------------------------------------------------------------------
# Entry point – called by APScheduler
# ---------------------------------------------------------------------------

async def graph_extraction_job():
    """APScheduler job: extract knowledge graph from unprocessed files."""
    try:
        count = await _run_extraction_cycle()
        if count > 0:
            logger.info("[CronJob] Graph extraction cycle complete: processed %d files", count)
    except Exception:
        logger.exception("[CronJob] Graph extraction cycle failed")

async def _run_forever() -> None:
    """Single event loop: asyncio.run() must not be called in a tight loop (closes the loop each time)."""
    while True:
        await graph_extraction_job()
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(_run_forever())
