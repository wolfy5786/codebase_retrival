"""Remove all Neo4j nodes for a codebase (DETACH DELETE by codebase_id)."""
import logging
import os

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


def delete_codebase_graph(codebase_id: str) -> None:
    """
    Delete every node (and incident relationships) tagged with this codebase_id.
    Idempotent: no-op if the graph has no matching nodes.
    """
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        raise RuntimeError("NEO4J_PASSWORD environment variable is required")

    logger.info("delete_codebase_graph started codebase_id=%s", codebase_id)
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            session.run(
                """
                MATCH (n {codebase_id: $codebase_id})
                DETACH DELETE n
                """,
                codebase_id=codebase_id,
            )
    finally:
        driver.close()
    logger.info("delete_codebase_graph completed codebase_id=%s", codebase_id)
