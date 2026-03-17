# CodeGraph — Backend API

> REST API surface that the CodeGraph backend must support. All endpoints are served by the FastAPI gateway (`services/api`).

---

## Overview

| Concern | Details |
|---------|---------|
| **Base path** | `/api/v1` |
| **Auth** | Supabase JWT validated on every protected request |
| **Middleware** | JWT verification, rate limiting, latency tracking |
| **Codebase scope** | All query and ingestion endpoints require a `codebase_id`; no global queries |

---

## 1. Codebase Management

All codebase operations are scoped to the current user; admins can access all codebases.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/codebases` | Create a new codebase (name, optional description) |
| `GET` | `/api/v1/codebases` | List codebases accessible to the current user |
| `GET` | `/api/v1/codebases/{id}` | Codebase detail and version history |
| `DELETE` | `/api/v1/codebases/{id}` | Delete codebase and all its graph data |

---

## 2. Ingestion

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/codebases/{id}/ingest` | Upload ZIP archive or provide GitHub URL; triggers incremental indexing via SSE |
| `GET` | `/api/v1/codebases/{id}/manifest` | List all indexed files with hashes |
| `GET` | `/api/v1/codebases/{id}/versions` | Ingestion version history |

### Ingest Request Body (for GitHub URL)

```json
{
  "source": "github",
  "url": "https://github.com/owner/repo",
  "token": "optional_github_pat"
}
```

### Ingest Request (ZIP Upload)

- Content-Type: `multipart/form-data`
- Streams progress via Server-Sent Events (SSE)

---

## 3. Query

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/codebases/{id}/query` | Run a natural-language query (scoped to this codebase) |

### Query Request Body

```json
{
  "query": "where is JWT token validation handled?",
  "explain": false
}
```

- `query` — Natural-language search string
- `explain` — Optional; `true` for context-with-explanation mode (LLM writes an explanation after retrieval)

### Query Response

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

| Field | Description |
|-------|-------------|
| `query_id` | Stable UUID; used for feedback and telemetry |
| `query` | Original query string |
| `backend_latency_ms` | Server request-to-response time (ms) |
| `results` | Top 5 ranked results (rank, score, unit, labels, language, file, start_line, end_line, snippet) |

---

## 4. Query Telemetry & Feedback

| Method | Endpoint | Description |
|--------|----------|-------------|
| `PATCH` | `/api/v1/query/{query_id}/telemetry` | Patch client-side latency after results are rendered |
| `POST` | `/api/v1/query/{query_id}/feedback` | Submit relevancy rating and optional comment |

### Telemetry Request Body

```json
{
  "client_latency_ms": 145
}
```

- `client_latency_ms` — Time from submit click to first result paint (measured in the browser)

### Feedback Request Body

```json
{
  "rating": 7,
  "comment": "Found the right class but missed the method"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `rating` | 1–10 | Relevancy score |
| `comment` | string | Optional free-text comment |

---

## 5. Auth (All Users)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/auth/me` | Current user profile (decoded from JWT) |

> Login, logout, and session management are handled by Supabase Auth via `@supabase/supabase-js`. The backend does not expose custom login/logout endpoints.

---

## 6. Admin-Only Operations

> Requires `app_metadata.role: "admin"`. Uses Supabase service role key server-side.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/admin/users` | List all users from Supabase Auth admin API |
| `POST` | `/api/v1/admin/users` | Create a new Supabase auth user and set role in `app_metadata` |
| `DELETE` | `/api/v1/admin/users/{id}` | Delete user from Supabase Auth |
| `PATCH` | `/api/v1/admin/users/{id}/role` | Update `app_metadata.role` via service role key |
| `POST` | `/api/v1/admin/codebases/{id}/grant` | Grant a user access to a codebase |

---

## Summary Table

| Category | Endpoints |
|----------|-----------|
| **Codebases** | `POST/GET/GET/DELETE` `/api/v1/codebases` and `/api/v1/codebases/{id}` |
| **Ingestion** | `POST` ingest, `GET` manifest, `GET` versions |
| **Query** | `POST` query |
| **Query follow-up** | `PATCH` telemetry, `POST` feedback |
| **Auth** | `GET` me |
| **Admin** | `GET/POST/DELETE/PATCH` users, `POST` codebase grant |

---

## Auth & Isolation

- **JWT verification** — FastAPI middleware validates Supabase JWT on every protected request.
- **Row Level Security (RLS)** — All Supabase tables enforce that users can only access their own rows.
- **Codebase isolation** — Every Neo4j node has `codebase_id`; all queries filter by it. Cross-codebase results are impossible.
- **Access control** — Users can only query codebases they own or have been granted access to via `POST /api/v1/admin/codebases/{id}/grant`.
