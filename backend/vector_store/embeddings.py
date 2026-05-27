"""Batch embedding generation via OpenAI text-embedding-3-small."""
import asyncio
from openai import AsyncOpenAI

BATCH_SIZE = 100


async def embed_texts(client: AsyncOpenAI, texts: list[str], model: str) -> list[list[float]]:
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = await client.embeddings.create(model=model, input=batch)
        all_embeddings.extend([item.embedding for item in response.data])
    return all_embeddings
