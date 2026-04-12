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
    Phase 1: structural nodes (``kind``, ``detail``, etc.) + CONTAINS.
    Phase 2 Tier 1: ``apply_phase2_tier1`` adds semantic labels and Tier-1 properties;
    ``apply_phase2_tier1_relationships`` merges Java ``INHERITS`` / ``IMPLEMENTS`` edges.
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
            
            # Build label string for Cypher (e.g. :Class:Internal:JavaClass)
            label_str = ":" + ":".join(labels)
            
            # Extract properties
            props = {
                "id": node.get("id"),
                "codebase_id": node.get("codebase_id"),
                "name": node.get("name"),
                "language": node.get("language"),
                "path": node.get("path"),
                "storage_ref": node.get("storage_ref"),
                "start_line": node.get("start_line"),
                "end_line": node.get("end_line"),
                "kind": node.get("kind"),
                "detail": node.get("detail"),
                "signature": node.get("signature"),
                # TODO: uncomment when ready for production — skipped during development to avoid OpenAI credit consumption
                # "embedding": node.get("embedding"),
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
    
    def apply_phase2_tier1(
        self,
        updates: list[dict],
        codebase_id: str,
    ) -> None:
        """
        Apply Phase 2 Tier 1: add labels and set properties on existing nodes.

        Each item must have ``id``, ``labels_to_add`` (list of strings), and
        ``properties`` (dict). Labels must be safe identifier-like tokens.
        """
        if not updates:
            logger.info("apply_phase2_tier1: no updates (codebase_id=%s)", codebase_id)
            return

        logger.info(
            "apply_phase2_tier1 started: rows=%d codebase_id=%s",
            len(updates),
            codebase_id,
        )

        try:
            with self.driver.session() as session:
                by_label: dict[str, list[str]] = {}
                prop_rows: list[dict[str, Any]] = []

                for row in updates:
                    nid = row.get("id")
                    if not nid:
                        continue
                    for lb in row.get("labels_to_add") or []:
                        s = str(lb)
                        if not s or not s.replace("_", "").isalnum():
                            logger.warning(
                                "apply_phase2_tier1: skipping invalid label %r for %s",
                                lb,
                                nid,
                            )
                            continue
                        by_label.setdefault(s, []).append(nid)

                    props = row.get("properties") or {}
                    clean = {k: v for k, v in props.items() if v is not None}
                    if clean:
                        prop_rows.append({"id": nid, "props": clean})

                for label, ids in by_label.items():
                    self._add_labels_batch(session, label, ids, codebase_id)

                if prop_rows:
                    session.run(
                        """
                        UNWIND $rows AS row
                        MATCH (n:CodeNode {codebase_id: $codebase_id, id: row.id})
                        SET n += row.props
                        """,
                        rows=prop_rows,
                        codebase_id=codebase_id,
                    )
                    logger.info(
                        "apply_phase2_tier1: set properties on %d nodes",
                        len(prop_rows),
                    )

            logger.info("apply_phase2_tier1 completed: codebase_id=%s", codebase_id)

        except Exception as e:
            logger.exception("apply_phase2_tier1 failed: %s", e)
            raise

    def apply_phase2_tier1_relationships(
        self,
        candidates: list[dict],
        codebase_id: str,
    ) -> None:
        """
        Merge Tier 1 ``INHERITS`` / ``IMPLEMENTS`` edges from crawl candidates.

        Each candidate has ``from_id``, ``target_name`` (``CodeNode.name``), and
        ``rel_type`` (``INHERITS`` or ``IMPLEMENTS``). Targets are resolved to
        ``CodeNode`` rows with ``kind`` in ``[5, 11]`` (class / interface).
        Multiple matches for the same name emit one edge per target (ambiguous-name rule).
        """
        if not candidates:
            logger.info(
                "apply_phase2_tier1_relationships: no candidates (codebase_id=%s)",
                codebase_id,
            )
            return

        logger.info(
            "apply_phase2_tier1_relationships started: candidates=%d codebase_id=%s",
            len(candidates),
            codebase_id,
        )

        try:
            with self.driver.session() as session:
                names = sorted(
                    {str(c["target_name"]) for c in candidates if c.get("target_name")}
                )
                name_to_ids: dict[str, list[str]] = {}
                if names:
                    res = session.run(
                        """
                        UNWIND $names AS name
                        MATCH (b:CodeNode {codebase_id: $codebase_id, name: name})
                        WHERE b.kind IN [5, 11]
                        RETURN name, collect(b.id) AS ids
                        """,
                        names=names,
                        codebase_id=codebase_id,
                    )
                    for rec in res:
                        name_to_ids[rec["name"]] = list(rec["ids"] or [])

                inherits_pairs: list[dict[str, str]] = []
                implements_pairs: list[dict[str, str]] = []
                seen_inherits: set[tuple[str, str]] = set()
                seen_implements: set[tuple[str, str]] = set()

                for c in candidates:
                    fid = c.get("from_id")
                    tname = c.get("target_name")
                    rtype = (c.get("rel_type") or "").upper()
                    if not fid or not tname or rtype not in ("INHERITS", "IMPLEMENTS"):
                        continue
                    ids = name_to_ids.get(str(tname), [])
                    if not ids:
                        logger.debug(
                            "Tier1 rel: no target for name=%r from_id=%s type=%s",
                            tname,
                            fid,
                            rtype,
                        )
                        continue
                    if len(ids) > 1:
                        logger.warning(
                            "Tier1 rel: ambiguous target name=%r -> %d matches from_id=%s type=%s",
                            tname,
                            len(ids),
                            fid,
                            rtype,
                        )
                    for tid in ids:
                        if tid == fid:
                            continue
                        row = {"from_id": fid, "to_id": tid}
                        if rtype == "INHERITS":
                            key = (fid, tid)
                            if key in seen_inherits:
                                continue
                            seen_inherits.add(key)
                            inherits_pairs.append(row)
                        else:
                            key = (fid, tid)
                            if key in seen_implements:
                                continue
                            seen_implements.add(key)
                            implements_pairs.append(row)

                self._merge_tier1_edges_batch(
                    session, inherits_pairs, codebase_id, "INHERITS"
                )
                self._merge_tier1_edges_batch(
                    session, implements_pairs, codebase_id, "IMPLEMENTS"
                )

            logger.info(
                "apply_phase2_tier1_relationships completed: codebase_id=%s",
                codebase_id,
            )

        except Exception as e:
            logger.exception("apply_phase2_tier1_relationships failed: %s", e)
            raise

    def _merge_tier1_edges_batch(
        self,
        session: Any,
        pairs: list[dict[str, str]],
        codebase_id: str,
        rel_type: str,
    ) -> None:
        if not pairs:
            logger.debug("Tier1: no %s edges to merge", rel_type)
            return
        if rel_type == "INHERITS":
            query = """
            UNWIND $pairs AS p
            MATCH (a:CodeNode {codebase_id: $codebase_id, id: p.from_id})
            MATCH (b:CodeNode {codebase_id: $codebase_id, id: p.to_id})
            MERGE (a)-[:INHERITS]->(b)
            """
        elif rel_type == "IMPLEMENTS":
            query = """
            UNWIND $pairs AS p
            MATCH (a:CodeNode {codebase_id: $codebase_id, id: p.from_id})
            MATCH (b:CodeNode {codebase_id: $codebase_id, id: p.to_id})
            MERGE (a)-[:IMPLEMENTS]->(b)
            """
        else:
            raise ValueError(f"unsupported rel_type: {rel_type!r}")
        session.run(query, pairs=pairs, codebase_id=codebase_id)
        logger.info("apply_phase2_tier1_relationships: merged %d %s edge(s)", len(pairs), rel_type)

    def _add_labels_batch(
        self,
        session: Any,
        label: str,
        node_ids: list[str],
        codebase_id: str,
    ) -> None:
        """SET static label token on matching CodeNodes (one label per batch)."""
        if not node_ids:
            return
        query = f"""
            UNWIND $ids AS nid
            MATCH (n:CodeNode {{codebase_id: $codebase_id, id: nid}})
            SET n:{label}
            """
        session.run(query, ids=node_ids, codebase_id=codebase_id)
        logger.info(
            "apply_phase2_tier1: added label %s to %d nodes",
            label,
            len(node_ids),
        )

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
