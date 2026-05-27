"""Initialize Neo4j constraints and indexes."""
from graph.neo4j_client import Neo4jClient

CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Company) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (r:Risk) REQUIRE r.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (pr:Product) REQUIRE pr.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Industry) REQUIRE i.name IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS FOR (c:Company) ON (c.ticker)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.embedding_id)",
]


def init_schema(client: Neo4jClient) -> None:
    for stmt in CONSTRAINTS + INDEXES:
        client.run(stmt)
