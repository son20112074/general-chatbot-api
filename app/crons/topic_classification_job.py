import json
import re
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.logger import get_logger
from app.domain.models.file import File
from app.domain.models.file_topic import FileTopic
from app.domain.models.topic import Topic

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
    api_url = f"{str(settings.LLM_API).rstrip('/')}/chat/completions"

    response = await http_client.post(api_url, headers=headers, json=payload)
    if response.status_code != 200:
        raise RuntimeError(f"LLM API error ({response.status_code}): {response.text[:500]}")

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
    if not topic_ids:
        return []
    result = await db.execute(
        select(FileTopic.topic_id).where(
            FileTopic.file_id == file_id,
            FileTopic.topic_id.in_(topic_ids),
        )
    )
    existing = {row[0] for row in result.fetchall()}
    return [tid for tid in topic_ids if tid not in existing]


async def _save_file_topics(
    db: AsyncSession,
    file_id: int,
    classification: dict[str, bool],
    topic_name_to_id: dict[str, int],
) -> None:
    for name, is_matched in classification.items():
        topic_id = topic_name_to_id.get(name)
        if topic_id is None:
            continue
        ft = FileTopic(file_id=file_id, topic_id=topic_id, is_matched=is_matched)
        db.add(ft)
    await db.flush()


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
) -> None:
    if not new_topics:
        return

    # 1. find all files with max lookback for all news_topics
    max_lookback_days = max((t.reclassify_lookback_day for t in new_topics), default=0)
    overall_lookback = datetime.utcnow() - timedelta(days=max_lookback_days)
    
    new_topic_ids = [t.id for t in new_topics]
    now = datetime.utcnow()

    async with get_db_session() as db:
        # Get all file with max lookback
        result = await db.execute(
            select(File.id, File.content, File.created_at, File.created_by).where(
                File.is_topic_classified == True,
                File.content.isnot(None),
                File.created_at >= overall_lookback,
            )
        )
        files = result.fetchall()

    # if not files => end
    if not files:
        async with get_db_session() as db:
            await db.execute(
                update(Topic)
                .where(Topic.id.in_(new_topic_ids))
                .values(last_classified_at=now)
            )
            await db.commit()
        return

    # 2. Process every File
    for file_id, content, file_created_at, file_created_by in files:
        new_file_topic_ids = [topic.id for topic in new_topics if topic.created_by == file_created_by]
        async with get_db_session() as db:
            # get new topic ids that this file hasn't classify.   
            missing_ids = await _get_missing_topic_ids_for_file(db, file_id, new_file_topic_ids)

        if not missing_ids:
            continue

        # Filter again missing_topics with lookback every topic
        # Only get topic has (File.created_at >= Topic.lookback)
        eligible_missing_topics = []
        for t_id in missing_ids:
            topic_obj = next((t for t in new_topics if (t.id == t_id and t.created_by == file_created_by)), None)
            if topic_obj:
                topic_lookback_threshold = now - timedelta(days=topic_obj.reclassify_lookback_day)
                if file_created_at >= topic_lookback_threshold:
                    eligible_missing_topics.append(topic_obj)

        if not eligible_missing_topics:
            continue

        try:
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

    # 3. Update last classified status for topics
    async with get_db_session() as db:
        await db.execute(
            update(Topic)
            .where(Topic.id.in_(new_topic_ids))
            .values(last_classified_at=now)
        )
        await db.commit()

    logger.info("New topics %s marked as classified", [t.name for t in new_topics])


async def _handle_new_files(
    http_client: httpx.AsyncClient,
    all_topics: list[Topic],
) -> None:
    async with get_db_session() as db:
        result = await db.execute(
            select(File.id, File.content, File.created_by).where(
                File.is_topic_classified.is_(None),
                File.topic_classify_retries < settings.TOPIC_CLASSIFY_MAX_RETRIES,
                File.content.isnot(None),
            ).order_by(File.id.asc()).limit(settings.TOPIC_CLASSIFY_BATCH_SIZE)
        )
        files = result.fetchall()

    if not files:
        return

    for file_id, content, created_by in files:
        try:
            file_topics = [topic for topic in all_topics if topic.created_by == created_by]
            await _classify_file_for_topics(http_client, file_id, content, file_topics)
        except Exception as exc:
            logger.error("Failed to classify file %d: %s", file_id, exc)
            async with get_db_session() as db:
                await db.execute(
                    update(File)
                    .where(File.id == file_id)
                    .values(topic_classify_retries=File.topic_classify_retries + 1)
                )
                await db.commit()


async def topic_classification_job() -> None:
    async with get_db_session() as db:
        logger.info("Get all topics")
        all_topics = await _get_active_topics(db)
        
    if not all_topics:
        return

    async with httpx.AsyncClient(timeout=180) as http_client:
        async with get_db_session() as db:
            logger.info("Get news topics")
            new_topics = await _get_new_topics(db)

        if new_topics:
            logger.info("Found %d new topic(s): %s", len(new_topics), [t.name for t in new_topics])
            await _handle_new_topics(http_client, new_topics)

        logger.info("Starting handle news files")
        await _handle_new_files(http_client, all_topics)


