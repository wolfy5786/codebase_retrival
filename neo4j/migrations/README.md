# Neo4j Migrations

This directory contains Cypher migration scripts for the CodeGraph Neo4j database schema.

## Prerequisites

- Neo4j 5.x running (via Docker Compose or standalone)
- Neo4j credentials configured in `.env`

## Running Migrations

### Option 1: Neo4j Browser (Recommended for Development)

1. Start Neo4j:
   ```bash
   docker compose up neo4j
   ```

2. Open Neo4j Browser: http://localhost:7474

3. Login with credentials from `.env`:
   - Username: `neo4j`
   - Password: (value of `NEO4J_PASSWORD`)

4. Copy and paste the contents of each migration file in order:
   - `001_constraints.cypher` - Constraints and indexes for Phase 1

5. Execute the Cypher statements

### Option 2: cypher-shell (Command Line)

```bash
# From project root
docker compose exec neo4j cypher-shell -u neo4j -p <NEO4J_PASSWORD>

# Then copy-paste the migration file contents
```

### Option 3: Automated (Production)

For production deployments, use a tool like:
- [neo4j-migrations](https://github.com/michael-simons/neo4j-migrations)
- Custom migration runner script

## Migration Files

| File | Description | Status |
|------|-------------|--------|
| `001_constraints.cypher` | Phase 1: Node constraints, existence checks, basic indexes | ✅ Ready |
| `002_vector_index.cypher` | Phase 2: Vector index for embeddings | 🔜 Future |

## Test Graph Stats (Verify Ingestion per Codebase)

After an ingestion, verify nodes and relationships for a specific codebase:

```bash
# Via Docker (from project root) — pass the codebase_id
docker compose run --rm ingestion-worker python -m src.test_graph <codebase_id>

# Locally (from services/ingestion-worker)
python -m src.test_graph <codebase_id>
```

Example: `Neo4j graph stats for codebase_id=abc-123: nodes=42, relationships=38`

The worker also runs this query automatically after each ingestion and logs the result.

## Verification

After running migrations, verify constraints and indexes:

```cypher
// Show all constraints
SHOW CONSTRAINTS;

// Show all indexes
SHOW INDEXES;
```

Expected output after Phase 1:
- Constraint: `node_id_unique` on `:CodeNode(id)`
- Constraint: `node_codebase_id_exists` on `:CodeNode(codebase_id)`
- Index: `node_codebase_id_idx` on `:CodeNode(codebase_id)`
- Index: `node_path_idx` on `:CodeNode(path)`
- Index: `node_codebase_language_idx` on `:CodeNode(codebase_id, language)`
- Index: `node_level_idx` on `:CodeNode(level)`

## Rollback

To drop all constraints and indexes (use with caution):

```cypher
// Drop all constraints
DROP CONSTRAINT node_id_unique IF EXISTS;
DROP CONSTRAINT node_codebase_id_exists IF EXISTS;

// Drop all indexes
DROP INDEX node_codebase_id_idx IF EXISTS;
DROP INDEX node_path_idx IF EXISTS;
DROP INDEX node_codebase_language_idx IF EXISTS;
DROP INDEX node_level_idx IF EXISTS;

// Delete all data (danger!)
MATCH (n) DETACH DELETE n;
```
