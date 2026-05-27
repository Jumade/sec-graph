"""Graph traversal utilities for GraphRAG context building."""
import re
from typing import Any

from graph.neo4j_client import Neo4jClient

_LABEL_RE = re.compile(r"[^a-zA-Z0-9_]")


def _safe_label(label: str) -> str:
    """Sanitize an LLM-produced label to a valid Cypher identifier."""
    sanitized = _LABEL_RE.sub("_", label.strip())
    return sanitized if sanitized else "Entity"


def shortest_path(client: Neo4jClient, start: str, end: str, max_depth: int = 6) -> list[dict]:
    # shortestPath does not accept a parameterized depth — must be a literal
    query = f"""
    MATCH (a {{name: $start}}), (b {{name: $end}})
    MATCH path = shortestPath((a)-[*1..{max_depth}]-(b))
    RETURN [node IN nodes(path) | {{name: node.name, labels: labels(node)}}] AS nodes,
           [rel IN relationships(path) | type(rel)] AS rels
    LIMIT 1
    """
    results = client.run(query, start=start, end=end)
    return results[0] if results else {}


def expand_neighbors(client: Neo4jClient, name: str, depth: int = 1, max_nodes: int = 40) -> dict[str, Any]:
    # depth=1 keeps only direct neighbours (depth 2 explodes on dense graphs)
    # max_nodes caps the subgraph so the visualisation stays readable
    query = f"""
    MATCH (root {{name: $name}})
    CALL apoc.path.subgraphAll(root, {{maxLevel: {depth}}}) YIELD nodes, relationships
    WITH nodes[..{max_nodes}] AS limited, relationships
    WITH limited, [n IN limited | n.name] AS names, relationships
    RETURN
      [n IN limited | {{id: toString(id(n)), name: n.name, label: labels(n)[0]}}] AS nodes,
      [r IN relationships
       WHERE startNode(r).name IN names AND endNode(r).name IN names
       | {{source: toString(startNode(r).name), target: toString(endNode(r).name), type: type(r)}}
      ] AS edges
    """
    results = client.run(query, name=name)
    return results[0] if results else {"nodes": [], "edges": []}


def path_to_context(path: dict) -> str:
    if not path:
        return ""
    nodes = path.get("nodes", [])
    rels = path.get("rels", [])
    parts = []
    for i, node in enumerate(nodes):
        parts.append(node["name"])
        if i < len(rels):
            parts.append(f"--[{rels[i]}]-->")
    return " ".join(parts)


def upsert_entity(client: Neo4jClient, name: str, label: str, props: dict) -> None:
    safe = _safe_label(label)
    query = f"""
    MERGE (n:{safe} {{name: $name}})
    SET n += $props
    """
    client.run(query, name=name, props=props)


def upsert_relationship(
    client: Neo4jClient,
    head: str,
    head_label: str,
    rel_type: str,
    tail: str,
    tail_label: str,
    props: dict,
) -> None:
    safe_head = _safe_label(head_label)
    safe_tail = _safe_label(tail_label)
    safe_rel = _safe_label(rel_type)
    query = f"""
    MERGE (a:{safe_head} {{name: $head}})
    MERGE (b:{safe_tail} {{name: $tail}})
    MERGE (a)-[r:{safe_rel}]->(b)
    SET r += $props
    """
    client.run(query, head=head, tail=tail, props=props)
