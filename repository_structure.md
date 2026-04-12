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
├── PHASE1_IMPLEMENTATION.md        # Phase 1 design: minimal nodes (CodeNode) + CONTAINS + multi-threading
├── PHASE2_IMPLEMENTATION.md        # Phase 2 design: tiered labels/rels, Strategy pattern, DAG, memcache
├── DEPLOYMENT_CHECKLIST.md         # Deployment steps for Phase 1
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
│   │   │   ├── worker.py           # Main worker: job dequeue, orchestration, Phase 1 + Phase 2
│   │   │   ├── scanner.py          # Repo walker, file filtering, file-type classification, hash comparison
│   │   │   ├── hasher.py           # SHA-256 file hashing
│   │   │   ├── storage_uploader.py # Supabase Storage upload, manifest upsert
│   │   │   ├── lsp/                # LSP layer — shared client + per-language server adapters
│   │   │   │   ├── __init__.py
│   │   │   │   ├── client.py       # Shared JSON-RPC client (language-agnostic); connects to any LSP server via stdio
│   │   │   │   ├── hover_parse.py  # Flatten LSP hover payloads to plain text; split signature vs doc
│   │   │   │   ├── field_type_from_lsp.py  # Resolve field types via hover + typeDefinition (Java/C++)
│   │   │   │   └── servers/        # Per-language server adapters (spawn + init options only)
│   │   │   │       ├── __init__.py
│   │   │   │       └── java.py     # jdtls: spawn command, workspace data dir, initializationOptions
│   │   │   │       # Future: python.py, go.py, typescript.py, javascript.py, cpp.py, rust.py
│   │   │   ├── crawl/              # Two-phase crawl — Phase 1 (nodes+CONTAINS) + Phase 2 (tiered labels+relationships)
│   │   │   │   ├── __init__.py
│   │   │   │   ├── phase1.py       # Phase 1: documentSymbol walk → nodes (CodeNode only) + CONTAINS
│   │   │   │   ├── phase2_base.py  # Phase 2 orchestrator: tier execution, write coordination, memcache (WAL)
│   │   │   │   ├── phase2_rules.py # Rule dataclasses (LabelRule, RelationshipRule) and RuleRegistry
│   │   │   │   └── strategies/     # Strategy Pattern: per-language Phase 2 rules
│   │   │   │       ├── __init__.py # get_strategy(language) registry
│   │   │   │       ├── common.py   # Shared rules: kind→label mapping, common regex (all languages)
│   │   │   │       ├── java.py     # Java: extends/implements regex, @Test, @RequestMapping, etc.
│   │   │   │       ├── cpp.py      # C++: virtual/=0, destructor ~, gtest macros, socket, etc.
│   │   │   │       ├── python.py   # Python: class(Base), @abstractmethod, pytest, flask, etc.
│   │   │   │       └── js_ts.py    # JS/TS: extends, arrow functions, jest, express, etc.
│   │   │   ├── extractor/          # Phase 1 node extraction — shared base + per-language mappers
│   │   │   │   ├── __init__.py     # get_mapper() registry
│   │   │   │   ├── base.py         # Shared SymbolKind → structural property extraction
│   │   │   │   └── languages/      # Per-language refinements on top of base mapping
│   │   │   │       ├── __init__.py
│   │   │   │       ├── java/
│   │   │   │       │   ├── __init__.py
│   │   │   │       │   └── mapper.py   # Java: Phase 1 node property handling
│   │   │   │       └── cpp/
│   │   │   │           ├── __init__.py
│   │   │   │           └── mapper.py   # C++: Phase 1 node property handling
│   │   │   │       # Future: python/, go/, typescript/, javascript/, rust/
│   │   │   ├── graph_writer.py     # Neo4j writes (Phase 1 batch + Phase 2 per-tier) + read queries for Tier 2
│   │   │   ├── embeddings/         # Embedding generation (runs after Phase 2 completes)
│   │   │   │   ├── __init__.py
│   │   │   │   ├── build_text.py   # Build transient embedding input text per node
│   │   │   │   └── openai_embed.py # OpenAI batch embeddings API wrapper
│   │   │   └── ...
│   │   │   # Future: external_classifier.py (Async: cross-check external calls → LLM label assignment)
│   │   ├── requirements.txt
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
│   │   ├── Nodes.txt               # Node label definitions (CodeUnit, Class, Attribute, etc.)
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
| **Indexing** | `services/ingestion-worker` | Repo scan → Phase 1 (nodes+CONTAINS) → Phase 2 (tiered labels+relationships) → embeddings → Neo4j |
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
| Phase 1 crawl (nodes + CONTAINS) | `services/ingestion-worker/src/crawl/phase1.py` |
| Phase 2 orchestrator (tiered labels + rels) | `services/ingestion-worker/src/crawl/phase2_base.py` |
| Phase 2 rule definitions | `services/ingestion-worker/src/crawl/phase2_rules.py` |
| Phase 2 language strategies | `services/ingestion-worker/src/crawl/strategies/` |
| LSP shared client | `services/ingestion-worker/src/lsp/client.py` |
| LSP per-language server adapters | `services/ingestion-worker/src/lsp/servers/` |
| Phase 1 extractor base | `services/ingestion-worker/src/extractor/base.py` |
| Phase 1 per-language mappers | `services/ingestion-worker/src/extractor/languages/<lang>/mapper.py` |
| Graph writer (Phase 1 + Phase 2 + queries) | `services/ingestion-worker/src/graph_writer.py` |
| Embedding generator | `services/ingestion-worker/src/embeddings/` |
| External call classifier (async, future) | `services/ingestion-worker/src/external_classifier.py` |

---

## Indexing Flow (Two-Phase Crawl)

**Phase 1 -- Node Creation + CONTAINS (see `PHASE1_IMPLEMENTATION.md`):**
```
Repo input (ZIP) → Scanner (hash + filter + file-type classification)
    → Classify files by extension: File, Dockerfile, MarkupFile, Documentation, SQLNoSQLScript, CICD
    → Multi-threaded: for each File-typed source file:
        - LSP documentSymbol → walk tree → nodes (CodeNode label only) + CONTAINS edges
        - Store structural properties: id, name, kind, signature, detail, line range
    → Single-threaded: create whole-file nodes for non-File types (CodeNode + file-type label)
    → Graph Writer → Neo4j (batch write all nodes + CONTAINS edges)
```

**Phase 2 -- Semantic Labels + Relationships (see `PHASE2_IMPLEMENTATION.md`):**
```
Tier 1 (multi-threaded, regex/kind-based):
    → Map kind → semantic labels (Class, Method, Attribute, etc.)
    → Regex on source → additional labels (Abstract, Testing, Lambda, etc.)
    → Extract properties: return_type, parameter_types, access_modifier, modifiers, annotations
    → Regex-extract INHERITS/IMPLEMENTS from source declarations
    → Write to Neo4j (batch)

Tier 3 (multi-threaded, LSP-based):
    → hover + typeDefinition → Object/Instance labels + reference_type_detail
    → textDocument/definition → definition_uri
    → callHierarchy → CALLS edges
    → documentHighlight → SETS/GETS edges
    → Write to Neo4j (batch)

Tier 2 (sequential, DAG-ordered):
    → Step 2a: InnerClass label + INSTANTIATES edges → write
    → Step 2b: OVERRIDES + BELONGS_TO edges → write
    → Step 2c: External label + SPAWNS edges → write

All writes tracked in transactional memcache (WAL) for rollback on failure.

Post-Phase 2:
    → Embedding Generator → Graph Writer → Neo4j (vectors on settled nodes)
    → Storage upload + manifest upsert
    → Async: External Call Classifier (LLM label assignment for matched external calls)
```

---

## Data Flow Summary

```
[ZIP / GitHub / local path]
    → api (ingest endpoint; auth: JWT + codebase access)
    → ingestion-worker (auth: job context)
        → Phase 1: LSP documentSymbol → nodes (CodeNode) + CONTAINS → batch write to Neo4j
        → Phase 2: Tier 1 (regex labels) → Tier 3 (LSP labels/rels) → Tier 2 (graph-dep) → write per tier
        → Embeddings (after Phase 2) → Neo4j
    → Supabase Storage (raw files), file_manifest
    → Async: External Call Classifier (LLM label assignment)

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
