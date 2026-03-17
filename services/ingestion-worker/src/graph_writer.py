"""
Neo4j graph writer: batch-creates nodes and relationships.
Logs each node created as per Phase 1 requirements.
"""
import logging
import os
from typing import Any

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


class GraphWriter:
    """
    Writes nodes and relationships to Neo4j.
    Phase 1: nodes + CONTAINS relationships only.
    """
    
    def __init__(self):
        """Initialize Neo4j driver from environment variables."""
        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        user = os.environ.get("NEO4J_USER", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD")
        
        if not password:
            raise ValueError("NEO4J_PASSWORD environment variable is required")
        
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            logger.info("Neo4j driver initialized: %s", uri)
        except Exception as e:
            logger.exception("Failed to initialize Neo4j driver: %s", e)
            raise
    
    def get_graph_stats_for_codebase(self, codebase_id: str) -> dict[str, int]:
        """
        Return node and relationship counts for a specific codebase.
        Used to verify the graph was written correctly after ingestion.
        """
        try:
            with self.driver.session() as session:
                node_result = session.run(
                    "MATCH (n {codebase_id: $codebase_id}) RETURN count(n) AS node_count",
                    codebase_id=codebase_id,
                )
                rel_result = session.run(
                    """
                    MATCH (a {codebase_id: $codebase_id})-[r]->(b {codebase_id: $codebase_id})
                    RETURN count(r) AS relationship_count
                    """,
                    codebase_id=codebase_id,
                )
                node_count = node_result.single()["node_count"] or 0
                rel_count = rel_result.single()["relationship_count"] or 0
                return {"node_count": node_count, "relationship_count": rel_count}
        except Exception as e:
            logger.exception("get_graph_stats_for_codebase failed: %s", e)
            raise

    def close(self):
        """Close Neo4j driver."""
        try:
            if self.driver:
                self.driver.close()
                logger.info("Neo4j driver closed")
        except Exception as e:
            logger.debug("Neo4j driver close error: %s", e)
    
    def write_phase1(
        self,
        nodes: list[dict],
        contains_edges: list[dict],
        codebase_id: str,
    ) -> None:
        """
        Write Phase 1 results to Neo4j: nodes + CONTAINS relationships.
        Logs each node created.
        
        Args:
            nodes: List of node dicts with id, labels, properties
            contains_edges: List of CONTAINS edge dicts
            codebase_id: Codebase UUID for validation
            
        Raises:
            Exception: On any Neo4j write failure
        """
        logger.info(
            "write_phase1 started: nodes=%d contains_edges=%d codebase_id=%s",
            len(nodes),
            len(contains_edges),
            codebase_id,
        )
        
        try:
            with self.driver.session() as session:
                # Write nodes
                for node in nodes:
                    self._create_node(session, node)
                
                # Write CONTAINS edges
                self._create_contains_edges(session, contains_edges)
                
            logger.info("write_phase1 completed successfully")
            
        except Exception as e:
            logger.exception("write_phase1 failed: %s", e)
            raise
    
    def _create_node(self, session: Any, node: dict) -> None:
        """
        Create a single node in Neo4j and log it.
        
        Args:
            session: Neo4j session
            node: Node dict with id, labels, and properties
        """
        try:
            # Extract labels (list of strings)
            labels = node.get("labels", [])
            if not labels:
                logger.warning("Node has no labels, skipping: %s", node.get("id"))
                return
            
            # Build label string for Cypher (e.g. :Container:Class:Internal)
            label_str = ":" + ":".join(labels)
            
            # Extract properties
            props = {
                "id": node.get("id"),
                "codebase_id": node.get("codebase_id"),
                "name": node.get("name"),
                "language": node.get("language"),
                "level": node.get("level"),
                "path": node.get("path"),
                "storage_ref": node.get("storage_ref"),
                "start_line": node.get("start_line"),
                "end_line": node.get("end_line"),
                "signature": node.get("signature"),
            }
            
            # Remove None values
            props = {k: v for k, v in props.items() if v is not None}
            
            # Create node
            query = f"""
            MERGE (n{label_str} {{id: $id}})
            SET n += $props
            RETURN n.id as node_id
            """
            
            result = session.run(query, id=props["id"], props=props)
            record = result.single()
            
            if record:
                # Log node creation
                logger.info(
                    "Node created: id=%s labels=%s path=%s name=%s start_line=%d",
                    props["id"],
                    labels,
                    props.get("path", ""),
                    props.get("name", ""),
                    props.get("start_line", 0),
                )
            
        except Exception as e:
            logger.exception("Failed to create node %s: %s", node.get("id"), e)
            raise
    
    def _create_contains_edges(self, session: Any, edges: list[dict]) -> None:
        """
        Batch-create CONTAINS relationships.
        
        Args:
            session: Neo4j session
            edges: List of CONTAINS edge dicts with from_id, to_id, order
        """
        if not edges:
            logger.debug("No CONTAINS edges to create")
            return
        
        try:
            query = """
            UNWIND $edges AS edge
            MATCH (from {id: edge.from_id})
            MATCH (to {id: edge.to_id})
            MERGE (from)-[r:CONTAINS]->(to)
            SET r.order = edge.order
            """
            
            session.run(query, edges=edges)
            
            logger.info("Created %d CONTAINS relationships", len(edges))
            
        except Exception as e:
            logger.exception("Failed to create CONTAINS edges: %s", e)
            raise
    
    def delete_by_codebase(self, codebase_id: str) -> int:
        """
        Delete all nodes and relationships for a codebase.
        Used for cleanup or re-ingestion.
        
        Args:
            codebase_id: Codebase UUID
            
        Returns:
            Number of nodes deleted
        """
        logger.info("delete_by_codebase started: codebase_id=%s", codebase_id)
        
        try:
            with self.driver.session() as session:
                # Delete all relationships first
                session.run(
                    """
                    MATCH (n {codebase_id: $codebase_id})-[r]-()
                    DELETE r
                    """,
                    codebase_id=codebase_id,
                )
                
                # Delete all nodes
                result = session.run(
                    """
                    MATCH (n {codebase_id: $codebase_id})
                    DELETE n
                    RETURN count(n) as deleted
                    """,
                    codebase_id=codebase_id,
                )
                
                record = result.single()
                deleted = record["deleted"] if record else 0
                
                logger.info("delete_by_codebase completed: deleted=%d", deleted)
                return deleted
                
        except Exception as e:
            logger.exception("delete_by_codebase failed: %s", e)
            raise
