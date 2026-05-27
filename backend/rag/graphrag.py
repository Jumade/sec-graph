"""GraphRAG pipeline: retrieve context → generate grounded answer."""
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from core.config import get_settings
from graph.neo4j_client import Neo4jClient
from rag.retriever import RetrievalResult, retrieve
from vector_store.qdrant_client import QdrantStore


@dataclass
class GraphRAGAnswer:
    answer: str
    citations: list[dict[str, Any]]
    graph_context: str
    entities: list[str]
    graph_subgraph: dict[str, Any]


SYSTEM_PROMPT = """You are a financial intelligence analyst with access to SEC filing data and a knowledge graph.
Answer the user's question using ONLY the provided context.
Cite your sources by referencing the filing_id in brackets, e.g. [0001234567-23-000001].
If the graph paths are relevant, mention the relationship chain.
If the context is insufficient, say so explicitly — do not hallucinate."""


def _build_prompt(question: str, result: RetrievalResult) -> str:
    chunk_context = "\n\n".join(
        f"[{c.get('filing_id', 'unknown')}] ({c.get('ticker', '')} {c.get('filed_date', '')})\n{c.get('text', '')[:600]}"
        for c in result.chunks[:10]
    )
    return (
        f"## Graph Context\n{result.graph_context or 'No graph paths found.'}\n\n"
        f"## Filing Excerpts\n{chunk_context}\n\n"
        f"## Question\n{question}"
    )


async def answer_question(
    question: str,
    openai_client: AsyncOpenAI,
    qdrant: QdrantStore,
    neo4j: Neo4jClient,
    company_filter: str | None = None,
) -> GraphRAGAnswer:
    settings = get_settings()
    result = await retrieve(question, openai_client, qdrant, neo4j, company_filter=company_filter)

    prompt = _build_prompt(question, result)
    response = await openai_client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    answer_text = response.choices[0].message.content

    citations = [
        {
            "filing_id": c.get("filing_id"),
            "ticker": c.get("ticker"),
            "filed_date": c.get("filed_date"),
            "form_type": c.get("form_type"),
            "score": c.get("score"),
        }
        for c in result.chunks[:10]
    ]

    return GraphRAGAnswer(
        answer=answer_text,
        citations=citations,
        graph_context=result.graph_context,
        entities=result.entities_found,
        graph_subgraph=result.graph_subgraph,
    )
