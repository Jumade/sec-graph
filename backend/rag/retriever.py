"""Hybrid retriever: vector search + graph neighbor expansion."""
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from core.config import get_settings
from extraction.entity_extractor import extract_entities
from graph.neo4j_client import Neo4jClient
from graph.traversal import expand_neighbors, path_to_context, shortest_path
from vector_store.embeddings import embed_texts
from vector_store.qdrant_client import QdrantStore


@dataclass
class RetrievalResult:
    chunks: list[dict[str, Any]]
    graph_context: str
    entities_found: list[str]
    graph_subgraph: dict[str, Any]


async def retrieve(
    question: str,
    openai_client: AsyncOpenAI,
    qdrant: QdrantStore,
    neo4j: Neo4jClient,
    top_k: int = 20,
    company_filter: str | None = None,
) -> RetrievalResult:
    settings = get_settings()

    # 1. Embed query → vector search
    [query_vector] = await embed_texts(openai_client, [question], settings.openai_embedding_model)
    chunks = await qdrant.search(query_vector, top_k=top_k, company_filter=company_filter)

    # 2. Extract entity mentions from the question
    entities = await extract_entities(openai_client, question)
    entity_names = [e.name for e in entities]

    # 3. Graph expansion for each entity
    graph_contexts: list[str] = []
    combined_nodes: list[dict] = []
    combined_edges: list[dict] = []

    for name in entity_names[:5]:  # limit to 5 entities per query
        subgraph = expand_neighbors(neo4j, name, depth=2)
        combined_nodes.extend(subgraph.get("nodes", []))
        combined_edges.extend(subgraph.get("edges", []))

    # 4. Shortest paths between entity pairs (for path queries)
    path_contexts: list[str] = []
    if len(entity_names) >= 2:
        for i in range(min(len(entity_names) - 1, 3)):
            path = shortest_path(neo4j, entity_names[i], entity_names[i + 1])
            ctx = path_to_context(path)
            if ctx:
                path_contexts.append(ctx)

    graph_context = ""
    if path_contexts:
        graph_context += "Graph paths:\n" + "\n".join(path_contexts) + "\n\n"
    if combined_edges:
        edge_lines = [f"{e['source']} --[{e['type']}]--> {e['target']}" for e in combined_edges[:30]]
        graph_context += "Related graph edges:\n" + "\n".join(edge_lines)

    # Deduplicate nodes/edges by id
    seen_nodes = {n["id"] for n in combined_nodes}
    unique_nodes = list({n["id"]: n for n in combined_nodes}.values())
    seen_edges = set()
    unique_edges = []
    for e in combined_edges:
        key = (e["source"], e["type"], e["target"])
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(e)

    return RetrievalResult(
        chunks=chunks,
        graph_context=graph_context,
        entities_found=entity_names,
        graph_subgraph={"nodes": unique_nodes, "edges": unique_edges},
    )
