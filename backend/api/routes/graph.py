from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.deps import Neo4jDep
from graph.traversal import expand_neighbors, shortest_path, path_to_context

router = APIRouter()


class GraphNode(BaseModel):
    id: str
    name: str
    label: str


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str


class SubgraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class PathResponse(BaseModel):
    path_text: str
    nodes: list[dict[str, Any]]
    rels: list[str]


@router.get("/entity/{name}", response_model=SubgraphResponse)
async def get_entity_subgraph(name: str, depth: int = 2, neo4j: Neo4jDep = None):
    subgraph = expand_neighbors(neo4j, name, depth=min(depth, 3))
    return SubgraphResponse(
        nodes=[GraphNode(**n) for n in subgraph.get("nodes", [])],
        edges=[GraphEdge(**e) for e in subgraph.get("edges", [])],
    )


@router.get("/path", response_model=PathResponse)
async def get_path(
    from_entity: str = Query(alias="from"),
    to_entity: str = Query(alias="to"),
    neo4j: Neo4jDep = None,
):
    path = shortest_path(neo4j, from_entity, to_entity)
    if not path:
        raise HTTPException(404, f"No path found between '{from_entity}' and '{to_entity}'")
    return PathResponse(
        path_text=path_to_context(path),
        nodes=path.get("nodes", []),
        rels=path.get("rels", []),
    )
