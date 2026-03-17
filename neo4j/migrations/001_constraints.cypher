// Neo4j constraints and indexes for CodeGraph Phase 1
// Run these manually in Neo4j browser or via cypher-shell

// ─── Constraints ─────────────────────────────────────────────────────────────────

// Unique constraint on node ID (all nodes must have unique ID)
CREATE CONSTRAINT node_id_unique IF NOT EXISTS
FOR (n:CodeNode)
REQUIRE n.id IS UNIQUE;

// Existence constraint: all nodes must have codebase_id
CREATE CONSTRAINT node_codebase_id_exists IF NOT EXISTS
FOR (n:CodeNode)
REQUIRE n.codebase_id IS NOT NULL;

// ─── Indexes ─────────────────────────────────────────────────────────────────────

// Index on codebase_id for fast filtering (all queries filter by this)
CREATE INDEX node_codebase_id_idx IF NOT EXISTS
FOR (n:CodeNode)
ON (n.codebase_id);

// Index on path for delete-by-path operations (incremental updates)
CREATE INDEX node_path_idx IF NOT EXISTS
FOR (n:CodeNode)
ON (n.path);

// Composite index for common query pattern: codebase + language
CREATE INDEX node_codebase_language_idx IF NOT EXISTS
FOR (n:CodeNode)
ON (n.codebase_id, n.language);

// Index on level for hierarchical queries
CREATE INDEX node_level_idx IF NOT EXISTS
FOR (n:CodeNode)
ON (n.level);
