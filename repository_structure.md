# CodeGraph — Repository Structure

> Annotated directory tree reflecting the monorepo design: client interfaces, API gateway, indexing and retrieval services, core system, data layer, and deployment infrastructure.

---

## Design Principles

- **Monorepo** — all services, apps, and shared libraries live in one repository.
- **Strict codebase isolation** — every graph node and query is scoped to a `codebase_id`.
- **Multi-interface** — Web UI, VS Code extension, MCP server, and REST API share the same backend.
- **Containerized** — Docker Compose for local dev; AWS-ready for production.

---

## Directory Tree

```
codegraph/
├── .env.example                    # Template for required env vars (Supabase, Neo4j, Redis, OpenAI)
├── .gitignore
├── README.md                       # Project overview, architecture, getting started
├── repository_structure.md         # This file — annotated directory tree
├── docker-compose.yml              # Local dev: api, indexer, retrieval, neo4j, redis, web
├── docker-compose.prod.yml         # Production overrides for EC2 deployment
│
├── apps/                           # Client applications
│   ├── web/                        # React 18 + TypeScript + Vite + Tailwind
│   │   ├── src/
│   │   │   ├── components/         # Reusable UI components
│   │   │   ├── pages/              # Ingest, Query, Admin Analytics, etc.
│   │   │   ├── hooks/              # Auth, SSE, query feedback
│   │   │   ├── lib/                # Supabase client, API helpers
│   │   │   └── ...
│   │   ├── public/
│   │   ├── package.json
│   │   ├── vite.config.ts
│   │   └── CONTRIBUTING.md         # Conventions; new components need Storybook stories
│   │
│   ├── vscode-extension/           # VS Code Extension (TypeScript)
│   │   ├── src/
│   │   │   ├── ingest.ts           # One-click workspace indexing
│   │   │   ├── query.ts            # Natural-language search sidebar
│   │   │   ├── decorations.ts      # Line-level hover annotations
│   │   │   └── ...
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── CONTRIBUTING.md
│   │
│   └── mcp-server/                 # MCP entrypoint — CodeGraph tools for AI assistants (Claude, Cursor)
│       ├── src/
│       │   ├── main.py             # MCP server bootstrap (Python + MCP SDK)
│       │   ├── tools/              # ingest_repo, query_code, get_node, list_repos
│       │   └── ...
│       ├── requirements.txt
│       └── CONTRIBUTING.md
│
├── services/                       # Backend microservices
│   ├── api/                        # FastAPI gateway — auth, routing, rate limiting
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── auth/               # Service-level auth (shared pattern)
│   │   │   │   ├── dependencies.py # get_current_user, require_role
│   │   │   │   ├── jwt.py          # Supabase JWT verification
│   │   │   │   └── rls.py          # Codebase access checks (RLS)
│   │   │   ├── middleware/         # JWT verification, latency tracking
│   │   │   ├── routers/            # /api/v1/codebases, /query, /admin, etc.
│   │   │   └── ...
│   │   ├── requirements.txt
│   │   ├── Dockerfile
│   │   └── CONTRIBUTING.md         # New endpoints require integration tests
│   │
│   ├── ingestion-worker/           # Background indexing worker (Python + LSP per-language)
│   │   ├── src/
│   │   │   ├── worker.py           # Main worker: job dequeue, orchestration, Phase 1 integration
│   │   │   ├── scanner.py          # Repo walker, file filtering, hash comparison
│   │   │   ├── hasher.py           # SHA-256 file hashing
│   │   │   ├── storage_uploader.py # Supabase Storage upload, manifest upsert
│   │   │   ├── lsp/                # LSP layer — shared client + per-language server adapters
│   │   │   │   ├── __init__.py
│   │   │   │   ├── client.py       # ✅ Shared JSON-RPC client (language-agnostic); connects to any LSP server via stdio
│   │   │   │   └── servers/        # Per-language server adapters (spawn + init options only)
│   │   │   │       ├── __init__.py
│   │   │   │       └── java.py     # ✅ jdtls: spawn command, workspace data dir, initializationOptions
│   │   │   │       # Future: python.py, go.py, typescript.py, javascript.py, cpp.py, rust.py
│   │   │   ├── crawl/              # Two-phase crawl strategy — shared, language-agnostic
│   │   │   │   ├── __init__.py
│   │   │   │   └── phase1.py       # ✅ Shared: documentSymbol walk → nodes + CONTAINS (delegates label mapping to extractor)
│   │   │   │   # Future: phase2.py (callHierarchy, typeHierarchy, definition → remaining relationships + secondary labels)
│   │   │   ├── extractor/          # Node & relationship extraction — shared base + per-language mappers
│   │   │   │   ├── __init__.py     # ✅ get_mapper() registry
│   │   │   │   ├── base.py         # ✅ Shared SymbolKind → CodeGraph label mapping (covers all standard LSP kinds)
│   │   │   │   └── languages/      # Per-language refinements on top of base mapping
│   │   │   │       ├── __init__.py
│   │   │   │       └── java/
│   │   │   │           ├── __init__.py
│   │   │   │           └── mapper.py   # ✅ Java: InnerClass detection, static modifier, language-specific labels
│   │   │   │       # Future: python/, go/, typescript/, javascript/, cpp/, rust/
│   │   │   ├── graph_writer.py     # ✅ Neo4j node/edge writes; logs each node created
│   │   │   └── ...
│   │   │   # Future: embedding.py (OpenAI text-embedding-3-small)
│   │   │   # Future: external_classifier.py (Async: cross-check external calls → LLM label assignment)
│   │   ├── requirements.txt        # ✅ Updated with neo4j, lsprotocol
│   │   ├── Dockerfile
│   │   └── CONTRIBUTING.md
│   │
│   └── retrieval/                  # LLM orchestration + graph/vector search
│       ├── src/
│       │   ├── auth/               # Service-level auth (query-scoped user/codebase)
│       │   │   └── query_context.py# Validate codebase access before query execution
│       │   ├── orchestrator.py     # LLM: natural language → Cypher queries
│       │   ├── strategies/         # graph-only vs embedding+graph
│       │   ├── neo4j_client.py     # Invokes Neo4j MCP for Cypher execution
│       │   ├── snippet_fetcher.py  # Supabase Storage → code snippets
│       │   ├── result_aggregator.py# Deduplication, diversification
│       │   └── ...
│       ├── requirements.txt
│       ├── Dockerfile
│       └── CONTRIBUTING.md
│
├── packages/                       # Shared packages (internal MCP, CLI, shared libs)
│   ├── neo4j-mcp/                  # Neo4j MCP server — Cypher execution for indexer & retrieval
│   │   ├── src/
│   │   │   ├── tools/              # execute_cypher, write_nodes, delete_by_path
│   │   │   ├── client.ts           # Neo4j driver wrapper
│   │   │   └── ...
│   │   ├── package.json
│   │   └── tsconfig.json
│   │
│   └── shared/                     # (Optional) Shared types, constants across services
│
├── core_system/                    # Core retrieval system — documentation & config
│   ├── Retrival_system_README.md   # Full retrieval design: nodes, relationships, chunking
│   ├── documentation/
│   │   ├── Nodes.txt               # Node label definitions (CodeUnit, Container, etc.)
│   │   ├── Relationships.txt      # Edge types (CALLS, CONTAINS, INHERITS, etc.)
│   │   ├── ExternalAPILists.md     # Schema for external API classification
│   │   └── module_breakdown.png    # Architecture diagram
│   │
│   └── config/
│       ├── README.md               # Config usage and path resolution
│       └── external_apis/          # Per-language JSON: external call → LLM label triggers
│           ├── python.json         # Categories: database, network_send, network_accept,
│           ├── java.json           #   messaging, ipc, thread_comm, fork_spawn
│           ├── go.json
│           ├── javascript.json
│           ├── typescript.json
│           ├── cpp.json
│           └── rust.json
│
├── supabase/                       # Supabase schema & migrations
│   └── migrations/
│       ├── 001_init.sql            # codebase, file_manifest, codebase_version
│       ├── 002_query_log.sql       # query_log, query_feedback
│       └── 003_ingestion_log.sql   # ingestion_log, RLS policies
│
├── neo4j/                          # Neo4j schema, migrations & constraints
│   └── migrations/
│       └── 001_constraints.cypher  # ✅ Uniqueness, existence constraints, indexes (Phase 1)
│   # Future: 002_vector_index.cypher (Vector index for embedding similarity - Phase 2)
│
├── infrastructure/                 # IaC, LSP servers & deployment
│   ├── terraform/
│   │   ├── ec2/                    # EC2 + Docker Compose topology
│   │   ├── lambda/                 # API + retrieval as Lambda (stateless)
│   │   └── ...
│   │
│   └── LSP/                        # Language Server Protocol servers (indexer uses these)
│       └── jdtls/                  # ✅ Eclipse JDT Language Server for Java (Phase 1 implemented)
│           └── bin/
│               ├── jdtls           # Unix launch script
│               └── jdtls.bat       # Windows launch script
│       # Future: python/, go/, typescript/, cpp/, rust/
│
├── scripts/                        # Deployment & utility scripts
│   └── push-ecr.sh                 # Push Docker images to Amazon ECR
│
└── tests/                          # Cross-service integration tests (optional)
    ├── integration/
    └── e2e/
```

---

## Layer Mapping

| Layer | Path | Purpose |
|-------|------|---------|
| **Client** | `apps/web`, `apps/vscode-extension`, `apps/mcp-server` | User-facing entry points; all call same backend |
| **API Gateway** | `services/api` | Auth, routing, rate limiting; delegates to indexer & retrieval |
| **Auth** | `services/*/auth/` | JWT verification, RLS, job/query-scoped codebase access |
| **Indexing** | `services/indexer` | Repo scan → LSP (Phase 1: nodes+CONTAINS, Phase 2: relationships) → embeddings → Neo4j MCP |
| **Retrieval** | `services/retrieval` | LLM → Cypher → Neo4j MCP → snippets → results |
| **Neo4j MCP** | `packages/neo4j-mcp` | MCP server for Cypher execution; used by indexer & retrieval |
| **Core Design** | `core_system/` | Node/relationship schemas; external API config |
| **Data** | Supabase (external), Neo4j, Redis | Auth, PostgreSQL, Storage, graph DB, job queue |
| **Infra** | `infrastructure/`, `scripts/` | Terraform, LSP configs, ECR push, production compose |

---

## Key Paths

| Concern | Location |
|---------|----------|
| Node labels & semantics | `core_system/documentation/Nodes.txt` |
| Relationship constraints | `core_system/documentation/Relationships.txt` |
| External API classification | `core_system/config/external_apis/*.json` |
| Supabase schema | `supabase/migrations/` |
| Neo4j schema & migrations | `neo4j/migrations/`, `neo4j/schema/` |
| Auth (service-level) | `services/api/app/auth/`, `services/indexer/src/auth/`, `services/retrieval/src/auth/` |
| API surface | `services/api/app/routers/` |
| Query strategy logic | `services/retrieval/` |
| Neo4j MCP tools | `packages/neo4j-mcp/src/tools/` |
| MCP entrypoint (user tools) | `apps/mcp-server/src/tools/` |
| Two-phase crawl (Phase 1/2) — shared core | `services/indexer/src/crawl/` |
| LSP shared client | `services/indexer/src/lsp/client.py` |
| LSP per-language server adapters | `services/indexer/src/lsp/servers/` |
| Extractor shared SymbolKind mapping | `services/indexer/src/extractor/base.py` |
| Extractor per-language mappers | `services/indexer/src/extractor/languages/<lang>/mapper.py` |
| External call classifier | `services/indexer/src/external_classifier.py` |
| LSP configs | `infrastructure/lsps/configs/` |

---

## Indexing Flow (Two-Phase Crawl)

**Phase 1 (✅ Implemented for Java):**
```
Repo input (ZIP) → Scanner (hash + filter + Storage + manifest)
    → Filter .java files
    → CRAWL STEP 1 (Phase 1): jdtls documentSymbol → core nodes + CONTAINS only
        - Shared phase1.py walks DocumentSymbol tree
        - Delegates label mapping to Java mapper
        - Builds nodes (id, labels, properties, storage_ref, line range)
        - Builds CONTAINS edges (parent → child)
    → Graph Writer → Neo4j (batch write nodes + CONTAINS edges)
        - Logs each node created
    → Storage upload + manifest upsert
```

**Phase 2 (Future):**
```
    → CRAWL STEP 2: callHierarchy, typeHierarchy, definition, etc. → secondary/tertiary labels + relationships
    → Library/framework matching: external calls vs external_apis/*.json → LLM assigns labels
    → Tertiary labels (Dockerfile, Markup, SQL, CI/CD): entire file = one node, no embedding
    → Embedding Generator → Graph Writer → Neo4j (embeddings + remaining relationships)
    → Async: External Call Classifier (LLM label assignment for matched external calls)
```

---

## Data Flow Summary

```
[ZIP / GitHub / local path]
    → api (ingest endpoint; auth: JWT + codebase access)
    → ingestion-worker (auth: job context) → LSP Phase 1 (✅ Java only) → extract → Neo4j direct write
    → Supabase Storage (raw files), file_manifest
    # Future: Phase 2 → embed → external_classifier

[Natural-language query]
    → api (query endpoint; auth: JWT + codebase access)
      OR apps/mcp-server (query_code tool) → api
    → retrieval (auth: query context) → LLM → Cypher
    → Neo4j MCP (execute_cypher) → Neo4j
    → snippet_fetcher (Storage) → api (response with top-5 results)

[MCP entrypoint]
    apps/mcp-server (Python + MCP SDK) ← Claude, Cursor, etc. (stdio/SSE)
    → tools: ingest_repo, query_code, get_node, list_repos
    → calls api gateway (REST) under the hood
```
