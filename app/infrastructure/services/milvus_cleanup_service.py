"""Xóa chunk vector Milvus theo scalar field `path`."""

from __future__ import annotations

import logging

from pymilvus import MilvusClient

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: MilvusClient | None = None


def _milvus_expr_string_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _get_client() -> MilvusClient:
    global _client
    if _client is None:
        _client = MilvusClient(uri=settings.MILVUS_URI, timeout=30)
    return _client


def delete_chunks_by_path(path: str | None) -> None:
    """Xóa mọi chunk trong collection có `path` khớp chính xác."""
    if not path or not str(path).strip():
        return

    normalized = str(path).strip()
    filter_expr = f'path == "{_milvus_expr_string_literal(normalized)}"'
    client = _get_client()
    client.delete(
        collection_name=settings.MILVUS_COLLECTION,
        filter=filter_expr,
    )
    logger.info(
        "Deleted Milvus chunks | collection=%s | path=%s",
        settings.MILVUS_COLLECTION,
        normalized,
    )


async def delete_chunks_by_path_async(path: str | None) -> None:
    """Wrapper async: không chặn event loop khi gọi pymilvus."""
    import asyncio

    if not path or not str(path).strip():
        return
    await asyncio.to_thread(delete_chunks_by_path, path)
