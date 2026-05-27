from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from openai import AsyncOpenAI

from core.config import Settings, get_settings
from graph.neo4j_client import Neo4jClient
from vector_store.qdrant_client import QdrantStore


_neo4j: Neo4jClient | None = None
_qdrant: QdrantStore | None = None
_openai: AsyncOpenAI | None = None


def get_neo4j() -> Neo4jClient:
    return _neo4j


def get_qdrant() -> QdrantStore:
    return _qdrant


def get_openai_client() -> AsyncOpenAI:
    return _openai


def init_clients(settings: Settings) -> None:
    global _neo4j, _qdrant, _openai
    _neo4j = Neo4jClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    _qdrant = QdrantStore(settings.qdrant_host, settings.qdrant_port, settings.qdrant_collection)
    _openai = AsyncOpenAI(api_key=settings.openai_api_key)


def close_clients() -> None:
    if _neo4j:
        _neo4j.close()


SettingsDep = Annotated[Settings, Depends(get_settings)]
Neo4jDep = Annotated[Neo4jClient, Depends(get_neo4j)]
QdrantDep = Annotated[QdrantStore, Depends(get_qdrant)]
OpenAIDep = Annotated[AsyncOpenAI, Depends(get_openai_client)]
