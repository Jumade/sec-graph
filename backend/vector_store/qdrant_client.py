"""Qdrant collection management, upsert, and hybrid search."""
import asyncio
import logging
from typing import Any
from uuid import uuid5, NAMESPACE_DNS

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

logger = logging.getLogger(__name__)
VECTOR_SIZE = 1536  # text-embedding-3-small


class QdrantStore:
    def __init__(self, host: str, port: int, collection: str) -> None:
        self._client = AsyncQdrantClient(host=host, port=port)
        self._collection = collection

    async def ensure_collection(self, retries: int = 10, delay: float = 3.0) -> None:
        for attempt in range(retries):
            try:
                existing = await self._client.get_collections()
                names = [c.name for c in existing.collections]
                if self._collection not in names:
                    await self._client.create_collection(
                        collection_name=self._collection,
                        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
                    )
                    logger.info("Created Qdrant collection %s", self._collection)
                return
            except Exception as e:
                if attempt < retries - 1:
                    logger.warning("Qdrant not ready (attempt %d/%d): %s", attempt + 1, retries, e)
                    await asyncio.sleep(delay)
                else:
                    raise

    async def upsert_chunks(self, chunks: list[dict], embeddings: list[list[float]]) -> None:
        points = [
            PointStruct(
                id=str(uuid5(NAMESPACE_DNS, chunk["chunk_id"])),
                vector=embedding,
                payload=chunk,
            )
            for chunk, embedding in zip(chunks, embeddings)
        ]
        await self._client.upsert(collection_name=self._collection, points=points)

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 20,
        company_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        query_filter = None
        if company_filter:
            query_filter = Filter(
                must=[FieldCondition(key="ticker", match=MatchValue(value=company_filter.upper()))]
            )

        results = await self._client.search(
            collection_name=self._collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        return [
            {"score": r.score, **r.payload}
            for r in results
        ]
