# CodeGraph

> Semantic code search and retrieval platform powered by a graph database, vector embeddings, and LLM orchestration.

CodeGraph ingests an entire repository into a Neo4j knowledge graph, embeds every semantic code unit (functions, classes, modules, lambdas, try/except blocks, etc.), and lets developers query their codebase in plain English. Results are ranked, deduplicated, and returned with exact file paths and line numbers — giving developers the top 5 most relevant code locations for any question.

**Language support (current implementation):** The indexer and LSP-driven graph pipeline are wired for **Java** only. Support for Python, JavaScript, TypeScript, and other languages will be added in a later release.

---

## Table of Contents

- [Features](#features)
- [Demo Graph](#Demo Graph)
- [System Architecture](#system-architecture)
- [Tech Stack](#tech-stack)
- [Ingestion Interfaces](#ingestion-interfaces)
- [Codebase Management & Isolation](#codebase-management--isolation)
- [Query Interfaces](#query-interfaces)
- [Observability & Analytics](#observability--analytics)
- [Retrieval System](#retrieval-system)
- [User Auth & Admin Control](#user-auth--admin-control)
- [Getting Started (Local)](#getting-started-local)
- [Environment Variables](#environment-variables)
- [Deployment](#deployment)
- [Monorepo Structure](#monorepo-structure)
- [Contributing](#contributing)

---

## Features

- **Multi-interface ingestion** — upload a ZIP archive, paste a GitHub URL, use the VS Code extension, or call the MCP server.
- **Full repository indexing** — parses **Java** via LSP into a Neo4j knowledge graph with vector embeddings on every node (additional languages planned).
- **Semantic code search** — natural-language queries are passed to an LLM, which generates Neo4j queries and chooses between graph-only and embedding-with-graph strategies based on the question.
- **Two retrieval modes** — *context only*: queries execute via MCP to Neo4j and results are returned directly; *context with explanation*: results are retrieved via MCP, then an LLM writes an explanation before returning to the user.
- **Multi-query reasoning (explanation mode)** — when explanation is required, the LLM parses the question(s) in the prompt and may run one or more queries until satisfied with the retrieved context before generating the answer.
- **Graph vs embedding queries** — for embedding-included queries, the three most relevant nodes are fetched; for graph-only queries, result count depends on the question.
- **Source attribution** — results include file path, start/end line numbers, the semantic unit name, and relevance score where applicable.
- **Multi-part codebase ingestion** — a single codebase can be assembled from multiple ZIP uploads or folder uploads; all parts are merged into one isolated graph namespace.
- **Strict codebase isolation** — every graph node and every query is scoped to a single `codebase_id`; results from one codebase can never appear in another codebase's query, regardless of user.
- **Git-like incremental updates** — when a new upload arrives for an existing codebase, file hashes are compared against the stored manifest; only new, modified, or deleted files are processed. Stale nodes and edges are pruned; unchanged files are skipped entirely.
- **Query history & result logging** — every query, its top-5 results, and all latency metrics are persisted in Supabase (PostgreSQL) and associated with the repository and user.
- **Relevancy feedback** — after every query, users rate result quality on a 1–10 scale; ratings are stored alongside the query log and can be used to tune retrieval over time.
- **Three-dimensional latency tracking** — backend latency (server request-to-response), client latency (UI submit-to-render, measured in the browser and reported back), and ingestion latency (wall-clock time from job start to graph write completion) are all recorded per event.
- **User auth & admin control** — authentication and user management are handled by Supabase Auth; only administrators can create new users via the Supabase service role key.
- **Containerized monorepo** — all services run via Docker Compose for local development and are AWS-ready for production.

---
## Demo Graph
<img width="406" height="532" alt="visualisation" src="https://github.com/user-attachments/assets/a192f1e2-62d6-452f-adf5-c635898688f5" />
<img width="406" height="532" alt="visualisation1" src="https://github.com/user-attachments/assets/47a34594-a208-4f67-8ff9-428962f2d036" />

---
## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Client Interfaces                         │
│  Web UI  │  VS Code Extension  │  MCP Server  │  REST API (CLI)  │
└────────────────────────┬─────────────────────────────────────────┘
                         │ HTTPS / WebSocket
┌────────────────────────▼─────────────────────────────────────────┐
│                      API Gateway (FastAPI)                        │
│    Supabase JWT middleware  │  Rate limiting  │  Routing          │
└──────────────────┬──────────────────────────┬────────────────────┘
                   │                          │
        ┌──────────▼──────────┐  ┌────────────▼─────────────────┐
        │   Indexer Service   │  │      Retrieval Service        │
        │                     │  │                               │
        │  • Repo Scanner     │  │  • LLM Orchestrator           │
        │  • LSP Parser       │  │  • Vector Search              │
        │  • Node/Edge        │  │  • Graph Traversal            │
        │    Extractor        │  │    Return Result              │
        │  • Embedding        │  │                               │
        │    Generator        │  │                               │
        └──────────┬──────────┘  └────────────┬─────────────────┘
                   │                          │
┌──────────────────▼──────────────────────────▼────────────────────┐
│                          Data Layer                               │
│  Supabase Auth + PostgreSQL    │  Neo4j (graph + vector indexes)  │
│  Supabase Storage (raw code)   │  Redis (job queue / cache)       │
└──────────────────────────────────────────────────────────────────┘
```

### Indexing Flow

Graph construction uses **LSP (Language Server Protocol)**. **Current implementation: Java only** (other languages planned). The input folder is crawled in two steps.

```
Repo Input (ZIP / GitHub URL / local path)
       │
       ▼
Repository Scanner
  ├── skip .env, images, audio, video, .exe, binary & auto-generated files (textual content only)
  ├── SHA-256 hash each file → compare against Supabase file_manifest
  │     unchanged files → skip entirely
  └── upload accepted files to Supabase Storage
        key: codebases/{codebase_id}/files/{relative_path}
        update file_manifest (hash + storage_ref)
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ CRAWL STEP 1 — Core nodes only                                                │
│                                                                               │
│  For each code file: LSP analyzes the file → identifies nodes                 │
│  Primary (core) labels: CodeUnit/Function/Method, Class, Attribute,            │
│  Interface, Module/file, Lambda, Database, try, except/catch,                   │
│  Instantiator/Constructor, Destructor, InnerClass, Object/Instance, Internal,  │
│  Abstract, Enum, Event, etc. (see Nodes.txt). **External** is added only in     │
│  Phase 2 when definition resolves outside the repo.                             │
│                                                                               │
│  Node creation: LSP identifies nodes → attributes become node attributes       │
│  Embedding: body + docstring + definition → vector (OpenAI text-embedding-3)   │
│  When a node contains inner nodes: inner nodes are NOT attributes; they are    │
│  marked via relationships. Inner nodes' bodies excluded from outer embedding;  │
│  only their definition + docstring used.                                       │
│                                                                               │
│  Phase 1 also draws the CONTAINS relationship (parent → child containment).   │
└─────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ CRAWL STEP 2 — External label (only new node label), tertiary, relationships  │
│                                                                               │
│  • **Node labels:** Phase 2 may add only the **External** label to existing   │
│    nodes (definition outside the scanned repo). All other labels are Phase 1  │
│    or tertiary-by-extension.                                                  │
│  • Add relationships (CALLS, SETS, GETS, INHERITS, IMPLEMENTS, BELONGS_TO,    │
│    OVERRIDES, INSTANTIATES — CONTAINS already drawn in Phase 1)               │
│                                                                               │
│  • Tertiary labels (Dockerfile, Markup Lang file, SQL/NoSQL script,            │
│    Documentation, CI/CD): added by file extension. Ingested differently —     │
│    entire file = one node, no embedding.                                      │
│                                                                               │
│  • Orphan CALLS targets: after Phase 2, some CALLS edges point to target       │
│    node IDs that do not exist in the crawled graph. These represent calls to  │
│    external APIs, standard-library functions, or third-party packages outside │
│    the scanned repository.                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
Graph Writer  ──► Neo4j (metadata + storage_ref + embedding vector)
```

#### Identifying the External label

A node receives the **External** label when it is *not implemented by the user* and *not part of the project* — for example, library functions, framework APIs, or third-party package symbols. Identification is done during LSP analysis: the symbol's definition resolves to a file path or module outside the scanned repository (e.g. stdlib, installed packages, or dependency imports). Nodes marked External are mutually exclusive with Internal.

### Query Flow

```
Natural-language query
       │
       ▼
LLM Orchestrator  (GPT family)
  • Writes Neo4j query or queries (Cypher)
  • Chooses strategy per question:
      - graph-only     → pure Cypher on Neo4j (result count question-dependent)
      - embedding+graph → cosine similarity + graph constraints (fetch top-3 nodes)
       │
       ▼
┌──────┴───────┐
│ Context only │  Execute query(ies) via MCP → Neo4j → return results directly to user
└──────────────┘

┌─────────────────────────┐
│ Context with explanation│  Execute query(ies) via MCP → Neo4j
└────────────┬────────────┘
             │  LLM parses question(s); may run 1+ queries until satisfied
             ▼
       Retrieve results → LLM writes explanation → return to user
             │
             ▼
       Snippet Fetcher (when applicable)
           • Read storage_ref + start_line/end_line from each node
           • Download source file from Supabase Storage
           • Slice relevant lines  (cache file per query to avoid re-downloads)
             │
             ▼
       Response: file path, line range, unit name,
                 code snippet, relevance score (+ explanation when requested)
```

---

## Tech Stack


| Layer               | Technology                               |
| ------------------- | ---------------------------------------- |
| Backend API         | Python 3.12, FastAPI                     |
| Indexing pipeline   | Python, LSP (**Java** in current build; more languages later) |
| Graph database      | Neo4j (vector indexes)                   |
| Database & Auth     | Supabase (hosted PostgreSQL, Auth/GoTrue, Row Level Security) |
| Cache / job queue   | Redis 7                                  |
| LLM & embeddings    | OpenAI (GPT-4o, text-embedding-3-small)  |
| Web frontend        | React 18, TypeScript, Vite, Tailwind CSS |
| VS Code extension   | TypeScript, VS Code Extension API        |
| MCP server          | Python, Model Context Protocol SDK   |
| Auth (backend SDK)  | supabase-py (service role for admin ops) |
| Auth (frontend SDK) | @supabase/supabase-js                    |
| Containerization    | Docker, Docker Compose                   |
| Cloud (production)  | AWS EC2 / Lambda, ECR, S3                |
| IaC                 | Terraform                                |


---

## Ingestion Interfaces

> **Multi-part uploads.** A codebase does not have to arrive in a single upload. You can upload multiple ZIP files or directory paths and assign them all to the same named codebase. Each part is merged into that codebase's graph namespace. This is useful for monorepos split across archives, or for adding a second service directory to an already-indexed codebase. Subsequent uploads to an existing codebase trigger an incremental update — only changed files are reprocessed (see [Codebase Management & Isolation](#codebase-management--isolation)).

### 1. Web UI — ZIP Upload

Navigate to the **Ingest** page, select or create a target codebase, and upload one or more `.zip` archives. The backend extracts each archive in turn, merges files into the codebase's working directory, and streams progress back to the UI via Server-Sent Events (SSE).

### 2. Web UI — GitHub URL

Paste any public or private (token-authenticated) GitHub repository URL and assign it to a target codebase. The backend clones the repo, merges it into the codebase, and shows real-time progress.

### 3. MCP Server

The `mcp-server` package exposes CodeGraph tools to any MCP-compatible AI assistant (e.g. Claude via Cursor, Claude Desktop). Supported tools:


| Tool          | Description                                      |
| ------------- | ------------------------------------------------ |
| `ingest_repo` | Trigger indexing from a GitHub URL or local path |
| `query_code`  | Run a natural-language search query              |
| `get_node`    | Fetch a specific node by ID or path              |
| `list_repos`  | List all indexed repositories                    |


### 4. VS Code Extension

The `vscode-extension` package adds a CodeGraph panel to VS Code:

- **Ingest current workspace** — one-click indexing of the root folder currently open in VS Code.
- **Query sidebar** — type a natural-language question and see top-5 results with jump-to-source links directly in the editor.
- **Line decoration** — hover annotations showing which nodes the current line belongs to.

---

## Codebase Management & Isolation

### What is a Codebase?

A **codebase** is a named, versioned logical unit that groups one or more source uploads into a single queryable graph. It is the central entity everything else attaches to — ingestion jobs, query logs, feedback records, and access grants all reference a `codebase_id`.

A user creates a codebase once (giving it a name and optionally a description), then submits one or more uploads to it. All uploads are merged into the codebase's graph namespace. A single codebase can contain files from multiple ZIP archives, multiple GitHub clones, or a mix of both.

### Strict Isolation

Every node written to Neo4j carries a `codebase_id` property. **All graph queries and all vector similarity searches include a hard `codebase_id` filter.** This is enforced at the retrieval service layer — not just at the API layer — so it is not possible for a query to return results from a different codebase, even if the graph is shared within the same Neo4j instance.

Isolation guarantees:

- **Cross-codebase**: a query against codebase A never returns a node from codebase B.
- **Cross-user**: user X cannot query a codebase belonging to user Y unless an admin explicitly grants access.
- **Within-user**: a user's own codebases are isolated from each other. Querying "my auth service" codebase does not surface results from "my payment service" codebase.

### Git-Like Incremental Updates

Every upload to an existing codebase is treated as a **patch**, not a rebuild. The system maintains a **file manifest** in Supabase — a record of every file path in the codebase along with its content hash and the last time it was indexed.

When a new upload arrives:

```
Incoming files
      │
      ▼
Compare each file path + hash against the stored manifest
      │
      ├── New file (path not in manifest)
      │       → parse → extract nodes/edges → embed → write to Neo4j
      │       → add entry to manifest
      │
      ├── Modified file (path matches, hash differs)
      │       → delete all existing nodes and edges for that file path from Neo4j
      │       → re-parse → extract nodes/edges → embed → write to Neo4j
      │       → update manifest hash + timestamp
      │
      ├── Deleted file (path in manifest, not present in upload)
      │       → delete all nodes and edges for that file path from Neo4j
      │       → remove from manifest
      │
      └── Unchanged file (path matches, hash identical)
              → skip entirely (no parsing, no embedding, no DB writes)
```

This means:
- **Indexing cost scales with the size of the change**, not the size of the codebase.
- **Embeddings are only recomputed for nodes whose source content actually changed.**
- Relationships that cross file boundaries (e.g. a `CALLS` edge from file A to a function in file B) are re-evaluated when either file changes.

### Codebase Versioning

Each upload that results in at least one change creates a new **codebase version** entry in Supabase, recording:

| Column | Description |
|---|---|
| `version` | Monotonically incrementing integer per codebase |
| `upload_source` | `zip`, `github`, or `local` |
| `files_added` | Count of new files in this upload |
| `files_modified` | Count of changed files |
| `files_deleted` | Count of removed files |
| `files_unchanged` | Count of skipped files |
| `created_at` | Timestamp of the upload |

Admins and codebase owners can view the version history from the UI.

### Codebase-Scoped API Endpoints

All query and ingestion endpoints require a `codebase_id`. There is no concept of a "global" query.

```
POST   /api/v1/codebases                    — create a new codebase
GET    /api/v1/codebases                    — list codebases accessible to the current user
GET    /api/v1/codebases/{id}               — codebase detail + version history
DELETE /api/v1/codebases/{id}               — delete codebase and all its graph data

POST   /api/v1/codebases/{id}/ingest        — upload ZIP / provide GitHub URL
GET    /api/v1/codebases/{id}/manifest      — list all indexed files + hashes
GET    /api/v1/codebases/{id}/versions      — ingestion version history

POST   /api/v1/codebases/{id}/query         — run a natural-language query (scoped to this codebase)
```

---

## Query Interfaces

All interfaces return the same result shape:

```json
{
  "query_id": "3f7a1c2e-84b0-4d9e-a21f-9c3e5d8b1f02",
  "query": "where is JWT token validation handled?",
  "backend_latency_ms": 312,
  "results": [
    {
      "rank": 1,
      "score": 0.94,
      "unit": "validate_token",
      "labels": ["Function", "Internal"],
      "language": "python",
      "file": "services/auth/src/jwt_utils.py",
      "start_line": 42,
      "end_line": 67,
      "snippet": "def validate_token(token: str) -> TokenPayload:\n    ..."
    }
  ]
}
```

Fields:

- `query_id` — stable UUID for this query run; used to attach user feedback and client latency after the response is rendered.
- `query` — the original natural-language query string.
- `backend_latency_ms` — time in milliseconds from when the API gateway received the request to when the response was sent (server-side only).
- `rank` — position in top-5 (1–5).
- `score` — combined vector + graph relevance score (0–1).
- `unit` — name of the code unit (function, class, module, etc.).
- `labels` — node labels (e.g. `Function`, `Class`, `Module`); semantic type is derived from labels, not a separate `kind` property.
- `language` — source language.
- `file` — relative path from the repository root.
- `start_line` / `end_line` — exact source range.
- `snippet` — the raw source lines `start_line`–`end_line` fetched from Supabase Storage at query time using the node's `storage_ref`. Not stored in Neo4j or PostgreSQL.

After the results are rendered in the UI, the client sends a separate lightweight `PATCH /api/v1/query/{query_id}/telemetry` request carrying `client_latency_ms` (time from submit click to first result paint, measured in the browser). This keeps the main query response fast while still capturing end-to-end latency.

---

## Observability & Analytics

### Query Logging

Every query execution is recorded in the `query_log` Supabase table with:

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Stable identifier returned in every query response |
| `user_id` | UUID FK | User who ran the query |
| `codebase_id` | UUID FK | Codebase the query was run against |
| `query_text` | TEXT | Raw natural-language query string |
| `strategy` | TEXT | Retrieval strategy chosen (`vector`, `graph`, `hybrid`) |
| `results` | JSONB | Full top-5 result payload stored verbatim |
| `backend_latency_ms` | INT | Server-side request-to-response time |
| `client_latency_ms` | INT | Browser submit-to-render time (patched in after render) |
| `created_at` | TIMESTAMPTZ | Query timestamp |

### User Feedback

After each query response is rendered, the UI shows a **feedback bar** prompting the user to rate result relevancy on a scale of **1 to 10**. Submitting a rating is optional but encouraged. Ratings are recorded in the `query_feedback` table:

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Feedback record identifier |
| `query_id` | UUID FK | Links back to the `query_log` record |
| `user_id` | UUID FK | User who submitted the rating |
| `rating` | SMALLINT | Relevancy score 1–10 |
| `comment` | TEXT | Optional free-text comment |
| `created_at` | TIMESTAMPTZ | Submission timestamp |

**Feedback endpoint:**
```
POST /api/v1/query/{query_id}/feedback
Body: { "rating": 7, "comment": "Found the right class but missed the method" }
```

### Ingestion Latency

Every ingestion job records its timing in the `ingestion_log` table:

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Job identifier |
| `codebase_id` | UUID FK | Codebase being indexed |
| `user_id` | UUID FK | User who triggered ingestion |
| `source_type` | TEXT | `zip`, `github`, or `local` |
| `status` | TEXT | `pending`, `running`, `completed`, `failed` |
| `file_count` | INT | Total files scanned |
| `node_count` | INT | Total graph nodes written |
| `ingestion_latency_ms` | INT | Wall-clock time from job start to graph write completion |
| `started_at` | TIMESTAMPTZ | Job start timestamp |
| `completed_at` | TIMESTAMPTZ | Job end timestamp |

### Latency Dimensions

| Dimension | Where measured | How recorded |
|---|---|---|
| **Backend latency** | API gateway middleware — start timer on request receipt, stop on response send | Written to `query_log.backend_latency_ms` synchronously |
| **Client latency** | Browser — `performance.now()` at submit click vs. first result paint | Sent via `PATCH /api/v1/query/{query_id}/telemetry` after render |
| **Ingestion latency** | Indexer worker — wall clock from job dequeue to final Neo4j write | Written to `ingestion_log.ingestion_latency_ms` on job completion |

### Admin Analytics View

Admins can view aggregate analytics at `/admin/analytics`:

- Average backend and client latency per repository and per user over time.
- Average feedback rating per repository.
- Query volume over time (daily/weekly).
- Ingestion job history with per-job latency and node counts.

---

## Retrieval System

The retrieval system is documented in full in `[core_system/Retrival_system_README.md](core_system/Retrival_system_README.md)`.

### Search and Retrieval Modes

| Mode | Flow |
|------|------|
| **Context only** | Natural-language query → LLM generates Neo4j query → execute via MCP to Neo4j → return results directly to user. |
| **Context with explanation** | Natural-language query → LLM generates Neo4j query → execute via MCP → LLM parses question(s), may run 1+ queries until satisfied → LLM writes explanation → return to user. |

### Query Strategy

The LLM selects between:
- **Graph-only queries** — pure Cypher; result count depends on the question.
- **Embedding-with-graph queries** — combine vector similarity and graph constraints; fetch the **three most relevant nodes**.

### Other Details

- **All constraints enforced at application level** — node mutual exclusivity, relationship validity (From/To labels), and file filtering are enforced by the application, not the database.
- **File filtering** — ingestion skips `.env`, images, audio, video, `.exe`, and other non-textual files; only textual content is ingested.
- **Node-based chunking** — each chunk maps to one semantic unit (class, function, try/except block, lambda, etc.), never an arbitrary line window.
- **Hierarchical levels** — nodes carry a `level` property (0 = repo root → 4+ = inner blocks), enabling level-scoped queries.
- **Outer node embedding** — when a class contains methods, the class node's embedding uses method signatures only, not full method bodies, preventing token bloat and over-weighting.
- **Lean nodes** — Neo4j nodes store only metadata (`storage_ref`, `start_line`, `end_line`, `signature`, `annotations` when present, `docstring`, etc.) and the `embedding` vector. Node type is defined by labels, not a redundant `kind` property. Raw code lives in Supabase Storage; file hashes live in Supabase PostgreSQL.
- **On-demand snippet retrieval** — at query time, the retrieval service fetches raw lines from Supabase Storage using `storage_ref` + line range. Files are cached in-process per query.
- **Diversification** — the result aggregator avoids returning multiple near-duplicate chunks from the same file or class/module scope.
- **Incremental updates** — file hashes tracked in Supabase `file_manifest`; only re-parses, re-uploads, and re-embeds files that changed.

---

## User Auth & Admin Control

Authentication and user management are delegated entirely to **Supabase Auth** (backed by GoTrue). The API gateway validates every incoming request by verifying the Supabase-issued JWT against the project's JWT secret — no custom token issuance or refresh logic is written in the application.

### How it works

- **Login / session management** — handled by the `@supabase/supabase-js` client in the web app and VS Code extension. Supabase issues access tokens (1-hour default) and refresh tokens automatically.
- **JWT verification on the backend** — FastAPI middleware calls `supabase-py` to validate the JWT on every protected request. The decoded claims carry the user's `id`, `email`, and `app_metadata.role`.
- **Roles** — stored in Supabase's `app_metadata` field on each user record, which is included in the JWT. `app_metadata` can only be written by the service role key, not by users themselves.
- **Row Level Security (RLS)** — all Supabase tables (`query_log`, `query_feedback`, `ingestion_log`, `codebase`, `codebase_file_manifest`) have RLS policies enforcing that users can only read and write their own rows.

### Roles

| Role | Capabilities |
|---|---|
| `admin` | Create users, delete users, view all codebases, manage all ingestion jobs, view aggregate analytics |
| `user` | Query codebases they own or have been granted access to, ingest their own codebases |

### Admin-only operations

Admin operations (creating/deleting users, assigning roles) use the **Supabase service role key** via `supabase-py`. The service role key bypasses RLS and has full database access — it is only used server-side and is never exposed to clients.

```
POST   /api/v1/admin/users            — create a new Supabase auth user + set role in app_metadata
DELETE /api/v1/admin/users/{id}       — delete user from Supabase Auth
PATCH  /api/v1/admin/users/{id}/role  — update app_metadata.role via service role key
GET    /api/v1/admin/users            — list all users from Supabase Auth admin API
POST   /api/v1/admin/codebases/{id}/grant — grant a user access to a codebase
```

### Auth endpoints (all users)

Standard Supabase Auth flows are used directly from the client SDK. The application backend does not expose custom login/logout endpoints — these are handled by `@supabase/supabase-js` calling the Supabase Auth API.

```
GET    /api/v1/auth/me              — current user profile (decoded from JWT)
```

### Initial admin account

The first admin user is created manually via the Supabase dashboard or the Supabase Auth admin API using the `SUPABASE_SERVICE_ROLE_KEY`. Set `app_metadata: { "role": "admin" }` on that user. All subsequent user creation must go through the admin API endpoints.

---

## Getting Started (Local)

### Prerequisites

- Docker 24+ and Docker Compose v2
- A [Supabase](https://supabase.com) project (free tier is sufficient for local dev)
- An OpenAI API key
- (Optional) A GitHub personal access token for private repo ingestion

### 1. Set up Supabase

1. Create a new project at [app.supabase.com](https://app.supabase.com).
2. Run the SQL migrations in `supabase/migrations/` from the Supabase dashboard SQL editor (or via the Supabase CLI).
3. In **Authentication → Settings**, disable public sign-ups — only admins can create users.
4. Create the first admin user via **Authentication → Users → Invite user**, then set `app_metadata: { "role": "admin" }` on that user via the Supabase dashboard.
5. Copy the **Project URL**, **anon key**, and **service role key** from **Project Settings → API**.

### 2. Clone and configure

```bash
git clone https://github.com/your-org/codegraph.git
cd codegraph
cp .env.example .env
# Edit .env — fill in OPENAI_API_KEY, SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY at minimum
```

### 3. Start all services

```bash
docker compose up --build
```

This starts:

- `api` — FastAPI gateway on `http://localhost:8000`
- `indexer` — background indexing worker
- `retrieval` — retrieval service
- `neo4j` — graph DB on `http://localhost:7474` (browser) / `bolt://localhost:7687`
- `redis` — job queue / cache on `localhost:6379`
- `web` — React frontend on `http://localhost:3000`

> Supabase (PostgreSQL + Auth) is an external managed service and is **not** run inside Docker Compose.

### 4. Open the app

Navigate to `http://localhost:3000`. Log in with the admin credentials you created in the Supabase dashboard.

### 4. Install the VS Code extension (optional)

```bash
cd apps/vscode-extension
npm install
npm run package        # builds a .vsix file
code --install-extension codegraph-*.vsix
```

---

## Environment Variables


| Variable                    | Required | Description                                                            |
| --------------------------- | -------- | ---------------------------------------------------------------------- |
| `SUPABASE_URL`              | Yes      | Your Supabase project URL (`https://<ref>.supabase.co`)                |
| `SUPABASE_ANON_KEY`         | Yes      | Supabase anon/public key — used by frontend and for read operations    |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes      | Supabase service role key — used server-side for admin ops (keep secret) |
| `SUPABASE_JWT_SECRET`       | Yes      | JWT secret from Supabase project settings — used by FastAPI to verify tokens |
| `OPENAI_API_KEY`            | Yes      | Used for embeddings and LLM orchestration                              |
| `NEO4J_URI`                 | Yes      | Bolt URI for Neo4j (default: `bolt://neo4j:7687`)                      |
| `NEO4J_USER`                | Yes      | Neo4j username (default: `neo4j`)                                      |
| `NEO4J_PASSWORD`            | Yes      | Neo4j password                                                         |
| `REDIS_URL`                 | Yes      | Redis connection string                                                |
| `GITHUB_TOKEN`              | No       | GitHub PAT for private repository cloning                              |
| `OPENAI_EMBEDDING_MODEL`    | No       | Defaults to `text-embedding-3-small`                                   |
| `OPENAI_LLM_MODEL`          | No       | Defaults to `gpt-4o`                                                   |
| `MAX_REPO_SIZE_MB`          | No       | Max repo size for ingestion (default: `500`)                           |


Copy `.env.example` and fill in the required values before starting services.

---

## Deployment

### Local → AWS EC2

1. Provision an EC2 instance (recommended: `t3.large` or larger for Neo4j).
2. Push images to Amazon ECR:
  ```bash
   ./scripts/push-ecr.sh
  ```
3. SSH into the instance and run:
  ```bash
   docker compose -f docker-compose.prod.yml up -d
  ```

### AWS Lambda (stateless API only)

The `api` and `retrieval` services can be packaged as Lambda functions using the Mangum ASGI adapter. Neo4j remains on EC2 or Neo4j AuraDB. Supabase continues to serve as the managed PostgreSQL and Auth layer in all environments — no migration to Amazon RDS is needed.

Terraform configurations for both topologies are in `infrastructure/terraform/`.

---

## Monorepo Structure

See `[repository_structure.md](repository_structure.md)` for the full annotated directory tree.

---

## Contributing

1. Fork the repository and create a feature branch.
2. Follow the coding conventions in each package's `CONTRIBUTING.md`.
3. All new backend endpoints must have integration tests.
4. All new frontend components must have Storybook stories.
5. Open a pull request against `main`.

