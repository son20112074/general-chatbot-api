import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
from sqlalchemy import select, update, or_, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.logger import get_logger
from app.domain.models.file import File
from app.domain.models.file_topic import FileTopic
from app.domain.models.topic import Topic
from app.domain.models.user import User

logger = get_logger()

SYSTEM_PROMPT = (
    "You are a Vietnamese text classification assistant. "
    "Your task: read the provided document and determine which topics it belongs to. "
    "A document can belong to multiple topics at once. "
    "ONLY return valid JSON, no explanations, no markdown code fences. "
    "Keys are topic names (preserve original spelling and diacritics), values are true/false."
)


def _truncate_content(content: str) -> str:
    max_chars = settings.TOPIC_CLASSIFY_MAX_CONTENT_CHARS
    if len(content) <= max_chars:
        return content
    head = max_chars * 2 // 3
    tail = max_chars - head
    return content[:head] + "\n\n...[TRUNCATED]...\n\n" + content[-tail:]


def _build_messages(content: str, topic_names: list[str]) -> list[dict]:
    topics_json = json.dumps(topic_names, ensure_ascii=False)
    user_prompt = (
        f"Topic list: {topics_json}\n\n"
        f"Return JSON like {{\"topic1\": true, \"topic2\": false, ...}} "
        f"for ALL topics in the list.\n\n"
        f"Document content:\n---\n{content}\n---"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _parse_retry_after_seconds(response: httpx.Response) -> Optional[float]:
    """Extract retry-after wait seconds from a 429 response.

    Order of precedence:
      1. `Retry-After` header (seconds, integer or float).
      2. Body regex `try again in <N>s` (Groq style).
    Returns None if nothing parseable.
    """
    header = response.headers.get("Retry-After")
    if header:
        try:
            return float(header)
        except (TypeError, ValueError):
            pass
    text = response.text or ""
    m = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)\s*s", text, flags=re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except (TypeError, ValueError):
            return None
    return None


async def _call_llm(
    http_client: httpx.AsyncClient,
    messages: list[dict],
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": 0,
    }
    api_url = f"{str(settings.LLM_API).rstrip('/')}"

    max_retries = max(0, int(settings.TOPIC_CLASSIFY_LLM_RATE_LIMIT_RETRIES))
    max_sleep = max(0, int(settings.TOPIC_CLASSIFY_LLM_RATE_LIMIT_MAX_SLEEP_SECONDS))

    response: Optional[httpx.Response] = None
    for attempt in range(max_retries + 1):
        response = await http_client.post(api_url, headers=headers, json=payload)
        if response.status_code == 200:
            break
        if response.status_code == 429 and attempt < max_retries:
            wait = _parse_retry_after_seconds(response)
            sleep_s = min(max_sleep, wait) if wait is not None else min(max_sleep, 2 ** attempt)
            sleep_s = max(0.0, float(sleep_s))
            logger.warning(
                "LLM 429 rate-limit; sleeping %.2fs before retry %d/%d",
                sleep_s, attempt + 1, max_retries,
            )
            await asyncio.sleep(sleep_s)
            continue
        raise RuntimeError(
            f"LLM API error ({response.status_code}): {response.text[:500]}"
        )

    assert response is not None
    if response.status_code != 200:
        raise RuntimeError(
            f"LLM API error ({response.status_code}) after retries: {response.text[:500]}"
        )

    result = response.json()
    raw = result["choices"][0]["message"]["content"] or ""

    raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\n?```\s*$", "", raw)
    raw = raw.strip()

    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not m:
        raise ValueError(f"No JSON found in LLM output: {raw[:500]}")

    return json.loads(m.group(0))


def _parse_classification(
    llm_result: dict[str, Any], topic_names: list[str]
) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for name in topic_names:
        v = llm_result.get(name)
        if isinstance(v, bool):
            result[name] = v
        elif isinstance(v, str):
            result[name] = v.strip().lower() in ("true", "yes", "1")
        else:
            result[name] = False
    return result


async def _get_active_topics(db: AsyncSession) -> list[Topic]:
    result = await db.execute(
        select(Topic).where(Topic.is_deleted == False)
    )
    return list(result.scalars().all())


async def _get_new_topics(db: AsyncSession) -> list[Topic]:
    result = await db.execute(
        select(Topic).where(
            Topic.is_deleted == False,
            Topic.last_classified_at.is_(None),
        )
    )
    return list(result.scalars().all())


async def _get_missing_topic_ids_for_file(
    db: AsyncSession, file_id: int, topic_ids: list[int]
) -> list[int]:
    """Return topic IDs the cron should still try to classify for `file_id`.

    A pair is *eligible for classification* when:
      - no row exists yet, OR
      - row exists, was last touched by the cron (`updated_at IS NULL`),
        AND it is a failure tombstone (`classify_attempts > 0`)
        AND `classify_attempts < TOPIC_CLASSIFY_PAIR_MAX_RETRIES`.

    Manual rows (`updated_at IS NOT NULL`) are always preserved — never returned.
    Successful auto rows (attempts == 0) are never re-classified.
    Tombstones at the retry cap are dropped (no further LLM calls).
    """
    if not topic_ids:
        return []
    pair_cap = int(settings.TOPIC_CLASSIFY_PAIR_MAX_RETRIES)
    result = await db.execute(
        select(FileTopic.topic_id, FileTopic.classify_attempts, FileTopic.updated_at).where(
            FileTopic.file_id == file_id,
            FileTopic.topic_id.in_(topic_ids),
        )
    )
    rows = result.fetchall()
    existing_topic_ids = {row[0] for row in rows}
    # Topics with no row yet — fully eligible.
    missing = [tid for tid in topic_ids if tid not in existing_topic_ids]
    # Tombstones (auto, updated_at NULL, attempts > 0) below the cap → still retriable.
    for topic_id, attempts, updated_at in rows:
        a = attempts or 0
        if updated_at is None and 0 < a < pair_cap:
            missing.append(topic_id)
    return missing


async def _record_classify_failure(
    db: AsyncSession, file_id: int, topic_id: int
) -> int:
    """Upsert failure tombstone for (file_id, topic_id). Returns the new attempts count.

    Uses PostgreSQL ON CONFLICT to bump `classify_attempts` atomically.
    Sets `is_matched=False`, leaves `updated_at=NULL` so the row stays
    flagged as cron-owned (manual API would set updated_at).
    """
    stmt = (
        pg_insert(FileTopic)
        .values(file_id=file_id, topic_id=topic_id, is_matched=False, classify_attempts=1)
        .on_conflict_do_update(
            constraint="uq_file_topic",
            set_={
                "classify_attempts": FileTopic.__table__.c.classify_attempts + 1,
                "is_matched": False,
                "updated_at": None,
            },
        )
        .returning(FileTopic.classify_attempts)
    )
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def _save_file_topics(
    db: AsyncSession,
    file_id: int,
    classification: dict[str, bool],
    topic_name_to_id: dict[str, int],
) -> None:
    """Upsert auto-classified rows. `updated_at` stays NULL so manual API rows
    (set updated_at explicitly) remain distinguishable.

    On conflict (a previous failure left a tombstone with classify_attempts > 0,
    updated_at NULL): overwrite is_matched and reset classify_attempts to 0.
    """
    for name, is_matched in classification.items():
        topic_id = topic_name_to_id.get(name)
        if topic_id is None:
            continue
        stmt = (
            pg_insert(FileTopic)
            .values(
                file_id=file_id,
                topic_id=topic_id,
                is_matched=is_matched,
                classify_attempts=0,
            )
            .on_conflict_do_update(
                constraint="uq_file_topic",
                set_={
                    "is_matched": is_matched,
                    "classify_attempts": 0,
                    "updated_at": None,
                },
                # Only overwrite cron-owned rows — never trample manual matches.
                where=FileTopic.__table__.c.updated_at.is_(None),
            )
        )
        await db.execute(stmt)


async def _get_creator_role_map(
    db: AsyncSession, topics: list[Topic]
) -> dict[int, Optional[int]]:
    """Map topic_id → creator's role_id (None if creator missing or has no role)."""
    if not topics:
        return {}
    creator_ids = list({t.created_by for t in topics if t.created_by is not None})
    if not creator_ids:
        return {t.id: None for t in topics}
    result = await db.execute(
        select(User.id, User.role_id).where(User.id.in_(creator_ids))
    )
    creator_role: dict[int, Optional[int]] = {uid: rid for uid, rid in result.all()}
    return {t.id: creator_role.get(t.created_by) for t in topics}


class _AncestorCache:
    """Per-cron-tick cache: role_id → set of strict ancestor role_ids."""

    def __init__(self) -> None:
        self._cache: dict[int, set[int]] = {}

    async def get(self, db: AsyncSession, role_id: Optional[int]) -> set[int]:
        if role_id is None:
            return set()
        if role_id in self._cache:
            return self._cache[role_id]
        from app.domain.services.role_service import RoleService
        ids = await RoleService(db).get_ancestor_role_ids(role_id)
        s = set(ids)
        self._cache[role_id] = s
        return s


def _eligible_topics_for_file(
    topics: list[Topic],
    creator_role_map: dict[int, Optional[int]],
    file_owner_id: int,
    ancestor_role_ids: set[int],
) -> list[Topic]:
    """Topics matching: creator == file_owner OR creator's role ∈ ancestor_role_ids."""
    eligible: list[Topic] = []
    for t in topics:
        if t.created_by == file_owner_id:
            eligible.append(t)
            continue
        crid = creator_role_map.get(t.id)
        if crid is not None and crid in ancestor_role_ids:
            eligible.append(t)
    return eligible


async def _classify_file_for_topics(
    http_client: httpx.AsyncClient,
    file_id: int,
    content: str,
    topics: list[Topic],
) -> None:
    topic_names = [t.name for t in topics]
    topic_name_to_id = {t.name: t.id for t in topics}

    truncated = _truncate_content(content)
    messages = _build_messages(truncated, topic_names)
    llm_result = await _call_llm(http_client, messages)
    classification = _parse_classification(llm_result, topic_names)

    async with get_db_session() as db:
        await _save_file_topics(db, file_id, classification, topic_name_to_id)
        await db.execute(
            update(File)
            .where(File.id == file_id)
            .values(is_topic_classified=True, topic_classify_retries=0)
        )
        await db.commit()

    matched = [n for n, v in classification.items() if v]
    logger.info("File %d classified: matched topics=%s", file_id, matched)


async def _handle_new_topics(
    http_client: httpx.AsyncClient,
    new_topics: list[Topic],
    new_creator_role_map: dict[int, Optional[int]],
) -> None:
    if not new_topics:
        return

    new_topic_ids = [t.id for t in new_topics]
    now = datetime.utcnow()
    max_lookback_days = max((t.reclassify_lookback_day for t in new_topics), default=0)
    overall_lookback = now - timedelta(days=max_lookback_days)

    # 1. Compute eligible_user_ids = union over all new_topics of:
    #    {topic creator} ∪ {users whose role is a descendant of the creator's role}.
    eligible_user_ids: set[int] = set()
    async with get_db_session() as db:
        from app.domain.services.role_service import RoleService
        role_service = RoleService(db)
        descendant_cache: dict[int, list[int]] = {}
        for t in new_topics:
            if t.created_by is not None:
                eligible_user_ids.add(t.created_by)
            crid = new_creator_role_map.get(t.id)
            if crid is None:
                continue
            if crid not in descendant_cache:
                descendant_cache[crid] = await role_service.get_child_roles(crid)
            descendants = descendant_cache[crid]
            if descendants:
                user_result = await db.execute(
                    select(User.id).where(User.role_id.in_(descendants))
                )
                eligible_user_ids.update(uid for (uid,) in user_result.all())

    # 2. No eligible users → mark new topics classified and return.
    if not eligible_user_ids:
        async with get_db_session() as db:
            await db.execute(
                update(Topic)
                .where(Topic.id.in_(new_topic_ids))
                .values(last_classified_at=now)
            )
            await db.commit()
        logger.info("No eligible users for new topics; marked classified.")
        return

    # 3. Fetch candidate files (already classified, in lookback, owner ∈ eligible_user_ids).
    async with get_db_session() as db:
        result = await db.execute(
            select(
                File.id, File.content, File.created_at, File.created_by, User.role_id
            )
            .join(User, File.created_by == User.id)
            .where(
                File.is_topic_classified == True,
                File.content.isnot(None),
                File.created_at >= overall_lookback,
                File.created_by.in_(eligible_user_ids),
            )
        )
        files = result.fetchall()

    if not files:
        async with get_db_session() as db:
            await db.execute(
                update(Topic)
                .where(Topic.id.in_(new_topic_ids))
                .values(last_classified_at=now)
            )
            await db.commit()
        return

    ancestor_cache = _AncestorCache()
    # Track pairs that failed during this tick AND still have retry budget.
    # If non-zero at end → keep last_classified_at NULL so next tick retries.
    still_retriable = 0
    pair_cap = int(settings.TOPIC_CLASSIFY_PAIR_MAX_RETRIES)

    # 4. Process each candidate file.
    for file_id, content, file_created_at, file_created_by, owner_role_id in files:
        eligible_missing_topics: list[Topic] = []
        try:
            async with get_db_session() as db:
                ancestor_ids = await ancestor_cache.get(db, owner_role_id)

            # Per-file: keep new topics where creator == owner OR creator's role ∈ ancestors.
            file_eligible = _eligible_topics_for_file(
                new_topics, new_creator_role_map, file_created_by, ancestor_ids
            )
            if not file_eligible:
                continue

            async with get_db_session() as db:
                missing_ids = await _get_missing_topic_ids_for_file(
                    db, file_id, [t.id for t in file_eligible]
                )
            if not missing_ids:
                continue

            # Per-topic lookback filter.
            missing_set = set(missing_ids)
            for t in file_eligible:
                if t.id not in missing_set:
                    continue
                threshold = now - timedelta(days=t.reclassify_lookback_day)
                if file_created_at >= threshold:
                    eligible_missing_topics.append(t)

            if not eligible_missing_topics:
                continue

            topic_names = [t.name for t in eligible_missing_topics]
            topic_name_to_id = {t.name: t.id for t in eligible_missing_topics}
            truncated = _truncate_content(content)
            messages = _build_messages(truncated, topic_names)
            llm_result = await _call_llm(http_client, messages)
            classification = _parse_classification(llm_result, topic_names)

            async with get_db_session() as db:
                await _save_file_topics(db, file_id, classification, topic_name_to_id)
                await db.commit()

            matched = [n for n, v in classification.items() if v]
            logger.info("File %d re-classified for topics: %s", file_id, matched)
        except Exception as exc:
            logger.error("Failed to re-classify file %d: %s", file_id, exc)
            # Bump per-pair attempts for every topic we attempted this round.
            # Pairs that drop below the cap remain retriable next tick.
            try:
                async with get_db_session() as db:
                    for t in eligible_missing_topics:
                        attempts = await _record_classify_failure(db, file_id, t.id)
                        if attempts < pair_cap:
                            still_retriable += 1
                        else:
                            logger.warning(
                                "Pair (file=%d, topic=%d) hit cap (%d); skipping further retries.",
                                file_id, t.id, pair_cap,
                            )
                    await db.commit()
            except Exception as inner:
                logger.error(
                    "Failed to record classify failure for file %d: %s", file_id, inner,
                )
                # If we cannot persist the failure, still treat it as retriable so
                # the topic is not prematurely marked done.
                still_retriable += len(eligible_missing_topics)

    # 5. Mark new topics as classified ONLY when no pair is still retriable.
    if still_retriable == 0:
        async with get_db_session() as db:
            await db.execute(
                update(Topic)
                .where(Topic.id.in_(new_topic_ids))
                .values(last_classified_at=now)
            )
            await db.commit()
        logger.info("New topics %s marked as classified", [t.name for t in new_topics])
    else:
        logger.warning(
            "New topics %s NOT marked classified: %d pair(s) still retriable; will retry next tick.",
            [t.name for t in new_topics], still_retriable,
        )


async def _handle_new_files(
    http_client: httpx.AsyncClient,
    all_topics: list[Topic],
    creator_role_map: dict[int, Optional[int]],
) -> None:
    async with get_db_session() as db:
        result = await db.execute(
            select(File.id, File.content, File.created_by, User.role_id)
            .join(User, File.created_by == User.id)
            .where(
                File.is_topic_classified.is_(None),
                File.topic_classify_retries < settings.TOPIC_CLASSIFY_MAX_RETRIES,
                File.content.isnot(None),
            )
            .order_by(File.id.asc())
            .limit(settings.TOPIC_CLASSIFY_BATCH_SIZE)
        )
        files = result.fetchall()

    if not files:
        return

    ancestor_cache = _AncestorCache()

    for file_id, content, created_by, owner_role_id in files:
        missing_topics: list[Topic] = []
        try:
            async with get_db_session() as db:
                ancestor_ids = await ancestor_cache.get(db, owner_role_id)

            eligible = _eligible_topics_for_file(
                all_topics, creator_role_map, created_by, ancestor_ids
            )
            if not eligible:
                async with get_db_session() as db:
                    await db.execute(
                        update(File)
                        .where(File.id == file_id)
                        .values(is_topic_classified=True, topic_classify_retries=0)
                    )
                    await db.commit()
                logger.info("File %d has no eligible topics; marked classified.", file_id)
                continue

            async with get_db_session() as db:
                missing_ids = await _get_missing_topic_ids_for_file(
                    db, file_id, [t.id for t in eligible]
                )

            if not missing_ids:
                # All eligible pairs already exist (manual rows or prior cron run).
                async with get_db_session() as db:
                    await db.execute(
                        update(File)
                        .where(File.id == file_id)
                        .values(is_topic_classified=True, topic_classify_retries=0)
                    )
                    await db.commit()
                logger.info(
                    "File %d already has rows for every eligible topic; manual rows preserved.",
                    file_id,
                )
                continue

            missing_set = set(missing_ids)
            missing_topics = [t for t in eligible if t.id in missing_set]
            await _classify_file_for_topics(http_client, file_id, content, missing_topics)
        except Exception as exc:
            logger.error("Failed to classify file %d: %s", file_id, exc)
            # Record per-pair failure so future ticks can stop hammering bad pairs,
            # AND bump the file-level retry counter (existing first-time semantics).
            try:
                async with get_db_session() as db:
                    for t in missing_topics:
                        await _record_classify_failure(db, file_id, t.id)
                    await db.execute(
                        update(File)
                        .where(File.id == file_id)
                        .values(topic_classify_retries=File.topic_classify_retries + 1)
                    )
                    await db.commit()
            except Exception as inner:
                logger.error(
                    "Failed to persist failure for file %d: %s", file_id, inner,
                )


async def topic_classification_job() -> None:
    async with get_db_session() as db:
        # logger.info("Get all topics")
        all_topics = await _get_active_topics(db)
        all_creator_role_map = await _get_creator_role_map(db, all_topics)

    if not all_topics:
        return

    async with httpx.AsyncClient(timeout=180) as http_client:
        async with get_db_session() as db:
            # logger.info("Get new topics")
            new_topics = await _get_new_topics(db)
            new_creator_role_map = (
                await _get_creator_role_map(db, new_topics) if new_topics else {}
            )

        if new_topics:
            logger.info(
                "Found %d new topic(s): %s",
                len(new_topics),
                [t.name for t in new_topics],
            )
            await _handle_new_topics(http_client, new_topics, new_creator_role_map)

        # logger.info("Starting handle new files")
        await _handle_new_files(http_client, all_topics, all_creator_role_map)

async def _run_forever() -> None:
    """Single event loop: asyncio.run() must not be called in a tight loop (closes the loop each time)."""
    while True:
        await topic_classification_job()
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(_run_forever())
