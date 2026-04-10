"""
Cron job: Process unprocessed files, extract nodes & edges via LLM,
and upsert them into the knowledge graph.

Adapted for general-chatbot-api project structure.
"""

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
CHUNK_SIZE = 3000

# ── LLM System Prompt ──
EXTRACTION_SYSTEM_PROMPT = """\
You are a military intelligence knowledge-graph entity extractor. Given a text \
chunk and a STRICT military ontology definition, extract all entities and \
relationships present in the text.

You MUST follow the predefined military ontology EXACTLY. Do NOT create entity \
types or relationship types outside the ontology. If something does not fit any \
ontology type, SKIP it.

**Output valid JSON only.**

```json
{
  "entities": [
    {
      "name": "Entity Name (canonical form, e.g. full unit designation)",
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
- Entity names must be canonical military designations (e.g. "3rd Infantry Division", not "the division").
- For personnel, use full rank + name (e.g. "General James Smith").
- For weapons/platforms, use official designations (e.g. "F-35A Lightning II").
- Extract ALL entities and relationships you can find, including implicit ones.
- Do NOT invent information not present in the text.
- If an entity could match multiple types, choose the most specific military type.
- Return an empty entities/relationships array if nothing in the text matches the ontology.
"""

# ── Military Ontology ──
MILITARY_ONTOLOGY_DESC = """\
Entity types (USE ONLY THESE — reject anything that does not fit):
  - MilitaryUnit: A military formation or unit (battalion, brigade, division, fleet, squadron, etc.)  attrs=[branch, size, designation, country, status]
  - MilitaryPersonnel: A military service member or defense official  attrs=[rank, role, branch, nationality, unit]
  - Weapon: A weapon, munition, or armament  attrs=[type, caliber, range, manufacturer, designation]
  - MilitaryPlatform: A vehicle, vessel, aircraft, or drone used by military  attrs=[type, designation, manufacturer, branch, status]
  - MilitaryBase: A military installation, base, camp, or outpost  attrs=[type, country, branch, coordinates, status]
  - MilitaryOperation: A named military operation, campaign, exercise, or mission  attrs=[type, start_date, end_date, status, theater]
  - DefenseOrganization: A military branch, defense ministry, alliance, or security agency  attrs=[type, country, parent_org]
  - Conflict: An armed conflict, war, battle, or skirmish  attrs=[type, start_date, end_date, theater, status]
  - Location: A geographic location relevant to military context (country, region, strait, border area)  attrs=[type, country, coordinates, strategic_significance]
  - MilitaryTechnology: A defense technology, system, radar, C4ISR, cyber tool, or satellite system  attrs=[type, category, manufacturer, status]
  - Treaty: A military treaty, agreement, pact, or arms control accord  attrs=[type, signed_date, parties, status]
  - ThreatActor: A non-state armed group, terrorist organization, insurgency, or militia  attrs=[type, ideology, region, status]
  - SupplyChain: A defense supply chain, logistics route, or procurement program  attrs=[type, origin, destination, status]
  - Intelligence: An intelligence report, assessment, signal, or surveillance finding  attrs=[type, classification, source, date]

Relationship types (USE ONLY THESE — reject anything that does not fit):
  - COMMANDS: A person commands a unit or operation  (MilitaryPersonnel→MilitaryUnit, MilitaryPersonnel→MilitaryOperation)
  - SUBORDINATE_TO: A unit is subordinate to another unit  (MilitaryUnit→MilitaryUnit)
  - DEPLOYED_AT: A unit or platform is deployed at a base or location  (MilitaryUnit→MilitaryBase, MilitaryUnit→Location, MilitaryPlatform→MilitaryBase)
  - OPERATES: A unit or organization operates a platform or weapon  (MilitaryUnit→MilitaryPlatform, MilitaryUnit→Weapon, DefenseOrganization→MilitaryPlatform)
  - PARTICIPATES_IN: A unit, person, or org participates in an operation or conflict  (MilitaryUnit→MilitaryOperation, MilitaryPersonnel→MilitaryOperation, DefenseOrganization→Conflict)
  - EQUIPPED_WITH: A unit or platform is equipped with a weapon or technology  (MilitaryUnit→Weapon, MilitaryPlatform→Weapon, MilitaryUnit→MilitaryTechnology)
  - STATIONED_AT: Personnel stationed at a base or location  (MilitaryPersonnel→MilitaryBase, MilitaryPersonnel→Location)
  - ALLIED_WITH: Alliance or cooperation between organizations or countries  (DefenseOrganization→DefenseOrganization, Location→Location)
  - HOSTILE_TO: Adversarial relationship  (DefenseOrganization→ThreatActor, Location→Location, MilitaryUnit→ThreatActor)
  - MANUFACTURES: An organization manufactures a platform, weapon, or technology  (DefenseOrganization→MilitaryPlatform, DefenseOrganization→Weapon, DefenseOrganization→MilitaryTechnology)
  - SUPPLIES: Supply or logistics relationship  (SupplyChain→MilitaryUnit, DefenseOrganization→MilitaryUnit, Location→SupplyChain)
  - OCCURRED_AT: An operation, conflict, or event occurred at a location  (MilitaryOperation→Location, Conflict→Location)
  - SIGNED_BY: A treaty or agreement signed by a party  (Treaty→DefenseOrganization, Treaty→Location)
  - TARGETS: An operation, unit, or weapon targets an entity  (MilitaryOperation→ThreatActor, MilitaryOperation→Location, Weapon→MilitaryPlatform)
  - MEMBER_OF: Membership in alliances or organizations  (DefenseOrganization→DefenseOrganization, Location→DefenseOrganization)
  - PRODUCED_BY: Intelligence report or assessment produced by an org  (Intelligence→DefenseOrganization)
  - REPORTS_ON: Intelligence covers a subject  (Intelligence→ThreatActor, Intelligence→Conflict, Intelligence→Location, Intelligence→MilitaryOperation)
"""


# ---------------------------------------------------------------------------
# LLM helper – calls the OpenAI-compatible API for JSON extraction
# ---------------------------------------------------------------------------

async def _llm_chat_json(
    messages: list[dict[str, str]],
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Call the LLM API and return parsed JSON."""
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

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            f"{settings.LLM_API}/chat/completions",
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


# ---------------------------------------------------------------------------
# Text splitting
# ---------------------------------------------------------------------------

def _split_content(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text into chunks, breaking at paragraph boundaries when possible."""
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
        start = break_at
    return [c.strip() for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# Upsert nodes & edges
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

    # ── Insert edges ──
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

        edge = Edge(
            file_id=file_id,
            source_node_id=src_row.id,
            target_node_id=tgt_row.id,
            edge_type=(rel.get("type") or "RELATED_TO").strip(),
            fact=(rel.get("fact") or ""),
            attributes=rel.get("attributes") or {},
        )
        session.add(edge)
        edge_count += 1

    return node_count, edge_count


# ---------------------------------------------------------------------------
# Process a single file
# ---------------------------------------------------------------------------

async def _process_single_file(
    session: AsyncSession,
    doc_file: File,
) -> None:
    """Process one file: extract nodes/edges from content via LLM."""
    start_time = time.time()
    content = doc_file.content or ""
    if not content.strip():
        logger.info("File %d (%s) has empty content, skipping", doc_file.id, doc_file.name)
        return

    chunks = _split_content(content)
    total_nodes = 0
    total_edges = 0

    for i, chunk in enumerate(chunks):
        try:
            user_msg = (
                f"## Military Ontology (STRICT — use ONLY these types)\n{MILITARY_ONTOLOGY_DESC}\n\n"
                f"## Text chunk\n{chunk}\n\n"
                "Extract all military entities and relationships from this text. "
                "Use ONLY the entity types and relationship types defined in the ontology above. "
                "Skip anything that does not fit the military ontology."
            )
            extracted = await _llm_chat_json(
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=4096,
            )
            extracted.setdefault("entities", [])
            extracted.setdefault("relationships", [])

            n_nodes, n_edges = await _upsert_nodes_edges(
                session, doc_file.id, extracted,
            )
            total_nodes += n_nodes
            total_edges += n_edges

        except Exception:
            logger.exception(
                "Failed to process chunk %d/%d for file %d (%s)",
                i + 1, len(chunks), doc_file.id, doc_file.name,
            )

    duration = int(time.time() - start_time)

    # Mark file as graph-extracted
    await session.execute(
        update(File)
        .where(File.id == doc_file.id)
        .values(is_graph_extracted=True)
    )

    logger.info(
        "Processed file %d (%s): %d nodes, %d edges in %ds",
        doc_file.id, doc_file.name, total_nodes, total_edges, duration,
    )


# ---------------------------------------------------------------------------
# One extraction cycle
# ---------------------------------------------------------------------------

async def _run_extraction_cycle() -> int:
    """
    Fetch unprocessed files, extract graph data, upsert.
    Returns number of files processed.
    """
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
                await _process_single_file(session, doc_file)
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
