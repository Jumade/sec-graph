"""Neo4j driver wrapper."""
from typing import Any

from neo4j import GraphDatabase, Driver, ManagedTransaction


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver: Driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    def run(self, query: str, **params) -> list[dict[str, Any]]:
        with self._driver.session() as session:
            result = session.run(query, **params)
            return [dict(r) for r in result]

    def run_write(self, fn) -> Any:
        with self._driver.session() as session:
            return session.execute_write(fn)

    def run_read(self, fn) -> Any:
        with self._driver.session() as session:
            return session.execute_read(fn)
