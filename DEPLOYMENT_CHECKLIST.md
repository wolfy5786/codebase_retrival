# Deployment Checklist - Phase 1

This checklist covers all steps needed to deploy the Java LSP Phase 1 implementation.

## Prerequisites

- [ ] Docker and Docker Compose installed
- [ ] Java JDK 17+ installed (for jdtls)
- [ ] Git (if cloning from repository)
- [ ] Supabase project created
- [ ] OpenAI API key (for future embedding support)

---

## 1. Install jdtls

Choose one option:

### Option A: Download jdtls

```bash
# Create directory
mkdir -p infrastructure/LSP/jdtls
cd infrastructure/LSP/jdtls

# Download latest jdtls snapshot
# Visit: https://download.eclipse.org/jdtls/snapshots/
# Download jdt-language-server-<version>.tar.gz

# Extract
tar -xzf jdt-language-server-*.tar.gz

# Verify
ls -la bin/jdtls

# Make executable (Unix/Linux/macOS)
chmod +x bin/jdtls
```

### Option B: Use existing jdtls

If you already have jdtls installed, set `JDTLS_HOME` in `.env` (step 2).

---

## 2. Configure Environment Variables

```bash
# Copy template
cp .env.example .env

# Edit .env and fill in:
nano .env
```

Required variables:

```env
# Supabase (get from https://app.supabase.com)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here
SUPABASE_JWT_SECRET=your-jwt-secret-here

# Neo4j (set a strong password)
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-strong-password-here

# Redis (default is fine)
REDIS_URL=redis://redis:6379

# OpenAI (for future Phase 2 embeddings)
OPENAI_API_KEY=sk-...

# jdtls (defaults should work if you followed Option A above)
JDTLS_HOME=/opt/jdtls
JDTLS_DATA_DIR=/tmp/jdtls-workspace

# Optional: Java home
JAVA_HOME=/usr/lib/jvm/java-17-openjdk
```

---

## 3. Run Supabase Migrations

### Prerequisites

- [ ] Supabase project created
- [ ] Supabase CLI installed (optional but recommended)

### Run migrations in order:

```sql
-- In Supabase SQL Editor (https://app.supabase.com/project/_/sql)
-- Run each migration file:

-- 1. migrations/0001_create_codebase.sql
-- 2. migrations/0002_create_file_manifest.sql
-- 3. migrations/0003_create_versions.sql
-- ... etc (run all migrations in order)
```

Verify tables exist:
```sql
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public';
```

Expected tables:
- `codebase`
- `codebase_file_manifest`
- `codebase_version`
- (and others from existing migrations)

---

## 4. Start Neo4j and Run Migrations

```bash
# Start Neo4j only
docker compose up neo4j -d

# Wait for Neo4j to be ready (check logs)
docker compose logs -f neo4j
# Wait for: "Started."

# Open Neo4j Browser
# Visit: http://localhost:7474
# Username: neo4j
# Password: (from NEO4J_PASSWORD in .env)
```

### Run Neo4j migrations:

In Neo4j Browser, copy and paste the contents of:

```cypher
-- File: neo4j/migrations/001_constraints.cypher
-- (Copy entire file contents and run)
```

### Verify:

```cypher
SHOW CONSTRAINTS;
SHOW INDEXES;
```

Expected output:
- 2 constraints
- 4 indexes

---

## 5. Build and Start Services

```bash
# Build all services
docker compose build

# Start all services
docker compose up -d

# Check status
docker compose ps

# Watch logs
docker compose logs -f ingestion-worker
```

Expected services running:
- `redis` (port 6379)
- `neo4j` (ports 7474, 7687)
- `ingestion-worker`
- `api` (port 8000)
- `web` (port 3000)

---

## 6. Verify Installation

### Check ingestion-worker logs:

```bash
docker compose logs ingestion-worker | head -20
```

Expected:
- No errors
- "dequeue_job started" messages (polling for jobs)

### Check Neo4j connection:

```cypher
-- In Neo4j Browser
MATCH (n) RETURN count(n);
```

Should return 0 (empty database initially).

### Check API:

```bash
curl http://localhost:8000/health
```

Expected: `{"status": "ok"}`

---

## 7. Test Java Ingestion (Phase 1)

### Prepare test data:

Create a simple Java project:

```bash
mkdir -p /tmp/test-java-project/src/main/java/com/example
cat > /tmp/test-java-project/src/main/java/com/example/HelloWorld.java <<'EOF'
package com.example;

public class HelloWorld {
    private String message;

    public HelloWorld(String message) {
        this.message = message;
    }

    public void sayHello() {
        System.out.println(message);
    }

    public static void main(String[] args) {
        HelloWorld app = new HelloWorld("Hello, World!");
        app.sayHello();
    }
}
EOF

# Create ZIP
cd /tmp
zip -r test-java-project.zip test-java-project/
```

### Upload via API:

```bash
# 1. Create codebase (replace with your Supabase anon key and API)
curl -X POST http://localhost:8000/api/v1/codebases \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_SUPABASE_ANON_KEY" \
  -d '{
    "name": "test-java-project",
    "description": "Test Java ingestion"
  }'

# 2. Upload ZIP (note the codebase_id from step 1)
curl -X POST http://localhost:8000/api/v1/codebases/{codebase_id}/ingest \
  -H "Authorization: Bearer YOUR_SUPABASE_ANON_KEY" \
  -F "file=@/tmp/test-java-project.zip"
```

### Watch logs:

```bash
docker compose logs -f ingestion-worker
```

Expected log sequence:
```
INFO: dequeue_job ended job_id=... found=True
INFO: process_job started job_id=... codebase_id=...
INFO: download_and_extract_scan_hash started
INFO: download_and_extract_scan_hash ended batch_size=1
INFO: process_job: found 1 Java files, running Phase 1
INFO: Phase 1 crawl started: language=java files=1
INFO: Starting jdtls: ...
INFO: jdtls started with PID ...
INFO: LSP initialized for workspace: ...
DEBUG: Phase 1: extracted 4 nodes, 3 CONTAINS edges from HelloWorld.java
INFO: Phase 1 crawl completed: nodes=4 contains_edges=3
INFO: process_job: writing 4 nodes to Neo4j
INFO: Node created: id=... labels=['Container', 'Class', 'Internal', 'JavaClass'] path=.../HelloWorld.java name=HelloWorld start_line=3
INFO: Node created: id=... labels=['StaticMember'] path=.../HelloWorld.java name=message start_line=4
INFO: Node created: id=... labels=['Instantiator', 'Constructor'] path=.../HelloWorld.java name=HelloWorld start_line=6
INFO: Node created: id=... labels=['CodeUnit', 'Method'] path=.../HelloWorld.java name=sayHello start_line=10
INFO: Node created: id=... labels=['CodeUnit', 'Method'] path=.../HelloWorld.java name=main start_line=14
INFO: Created 3 CONTAINS relationships
INFO: write_phase1 completed successfully
INFO: Phase 1 completed successfully
INFO: process_job commit phase: uploading to Storage
INFO: process_job commit phase: upsert manifest
INFO: process_job commit phase: insert codebase_version
INFO: process_job ended job_id=...
```

### Verify in Neo4j:

```cypher
// Count nodes
MATCH (n {codebase_id: 'YOUR_CODEBASE_ID'})
RETURN count(n);
// Expected: 5 (1 class + 1 field + 1 constructor + 2 methods)

// View nodes
MATCH (n {codebase_id: 'YOUR_CODEBASE_ID'})
RETURN n.name, labels(n), n.start_line, n.end_line
ORDER BY n.start_line;

// View CONTAINS relationships
MATCH (parent {codebase_id: 'YOUR_CODEBASE_ID'})-[r:CONTAINS]->(child)
RETURN parent.name, child.name, r.order;
```

---

## 8. Troubleshooting

### jdtls not found

```
FileNotFoundError: jdtls not found at infrastructure/LSP/jdtls/bin/jdtls
```

**Fix**: Install jdtls (see step 1) or set `JDTLS_HOME` in `.env`.

### jdtls fails to start

```
ERROR: Failed to start jdtls
```

**Checks**:
- [ ] Java 17+ installed: `java --version`
- [ ] jdtls script is executable: `chmod +x infrastructure/LSP/jdtls/bin/jdtls`
- [ ] `JAVA_HOME` set in `.env`

### Neo4j connection refused

```
ERROR: Neo4j connection refused
```

**Checks**:
- [ ] Neo4j running: `docker compose ps neo4j`
- [ ] Neo4j ready: `docker compose logs neo4j | grep "Started"`
- [ ] Password correct in `.env`

### No nodes created

**Checks**:
- [ ] Logs show "Phase 1 crawl started"?
- [ ] Logs show "Node created"?
- [ ] Java files in ZIP?
- [ ] Check codebase_id in Neo4j query matches job

### Worker not processing jobs

**Checks**:
- [ ] Worker running: `docker compose ps ingestion-worker`
- [ ] Redis running: `docker compose ps redis`
- [ ] Job in queue: `redis-cli LLEN ingestion:queue`

---

## 9. Production Deployment

### Additional steps for production:

- [ ] Set strong passwords for Neo4j and Supabase
- [ ] Use `docker-compose.prod.yml` with resource limits
- [ ] Set up monitoring (Neo4j metrics, worker health checks)
- [ ] Configure backups for Neo4j data volume
- [ ] Set up log aggregation (e.g., CloudWatch, Datadog)
- [ ] Use secrets management (AWS Secrets Manager, Vault)
- [ ] Set `ENVIRONMENT=production` in `.env`
- [ ] Run on EC2 or ECS with persistent volumes
- [ ] Use Neo4j AuraDB (managed) instead of self-hosted

---

## 10. Next Steps

After successful Phase 1 deployment:

- [ ] Test with larger Java projects
- [ ] Monitor Neo4j performance and memory usage
- [ ] Implement Phase 2 (embeddings, CALLS, INHERITS, IMPLEMENTS)
- [ ] Add support for Python (create `lsp/servers/python.py` + mapper)
- [ ] Add support for other languages (Go, JS/TS, C++, Rust)
- [ ] Implement incremental updates (delete-by-path)
- [ ] Add query interface (retrieval service)

---

## Support

For issues or questions:
- Check logs: `docker compose logs -f ingestion-worker`
- Review documentation:
  - `PHASE1_IMPLEMENTATION.md` - implementation details
  - `infrastructure/LSP/README.md` - LSP setup
  - `neo4j/migrations/README.md` - Neo4j migrations
- Check Neo4j Browser for data: http://localhost:7474

---

✅ **Phase 1 deployment complete!** Java files will now be analyzed and their code structure stored in Neo4j.
