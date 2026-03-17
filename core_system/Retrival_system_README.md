## Code Graph Retrieval System

> **Source of truth:** The main project README (`README.md`) is the authoritative source for system design. This document provides detailed retrieval-system documentation and should be kept in sync with it.

### Overview

This project is a **semantic retrieval system for codebases** that combines:

- **Graph structure** (nodes + relationships in Neo4j) to capture code semantics and navigation paths.
- **Vector embeddings** on nodes for semantic search over code and documentation.
- **LLM orchestration** to receive natural-language queries, generate Neo4j (Cypher) queries, and return results (context only or context with explanation) via MCP.

The primary goals are:

- **Low latency**: fast indexing and query execution.
- **High relevancy**: results that match developer intent, not just text.
- **Low token usage**: retrieve only the most relevant, compact context for LLMs.

Given a folder path, the system:

1. Walks the codebase, skipping binary, auto-generated, and non-textual files (see [File Filtering](#file-filtering)).
2. Uses **LSP** to analyze supported source files (Java, Python, Go, JS, TS, C/C++, Rust) and identifies semantic **nodes** and **relationships**.
3. Embeds each node using OpenAI (code + comments + docstrings).
4. Stores the graph and embeddings in **Neo4j**.
5. Exposes a node-based query API; queries are executed via MCP to Neo4j.

---

### Core Concepts

#### Nodes

Nodes represent semantic code entities, aligned with the labels in `documentation/Nodes.txt`. Each node has one or more labels. **All constraints (mutual exclusivity, relationship validity) are enforced at the application level** — not by the database.

**Node labels and levels** (each label maps to a hierarchical level for retrieval):


| Label                        | Level | Description                                                                                          |
| ---------------------------- | ----- | ---------------------------------------------------------------------------------------------------- |
| CodeUnit / Function / Method | 3     | Callable function in code                                                                            |
| Container / Class            | 2     | User-defined data type encapsulating attributes and functions                                        |
| StaticMember                 | 3     | Static/global variable or static function                                                            |
| Interface                    | 2     | Blueprint of class                                                                                   |
| Module / File                | 1     | File containing code                                                                                 |
| External                     | *     | Node not implemented by user or not part of project (library, framework); additive with other labels |
| Internal                     | *     | Node part of project, implemented by user                                                            |
| Lambda                       | 4     | Lambda functions                                                                                     |
| Database                     | 2     | Represents a database                                                                                |
| try                          | 4     | Try block (no implementation yet)                                                                    |
| except / catch               | 4     | Except/catch block (future work)                                                                     |
| Instantiator / Constructor   | 3     | Constructor                                                                                          |
| Destructor                   | 3     | Destructor                                                                                           |
| InnerClass                   | 3     | Class within a class                                                                                 |
| Object / Instance            | 3     | Instance of a class                                                                                  |
| Abstract                     | *     | Abstract method or class                                                                             |
| Accept_call_over_network     | *     | Node that accepts a request/call over network                                                        |
| Sends_data_over_network      | *     | Node that sends a request/call over network                                                          |
| Enum                         | 2     | Enumeration type                                                                                     |
| Event                        | 3     | Event handler                                                                                        |
| Testing                      | 2     | Test-related node                                                                                    |
| Container (Dockerfile)       | 2     | Dockerfile image *(skip for now; implement later)*                                                   |
| Markup Lang file             | 1     | Markup file (.json, .yaml, etc.)                                                                     |
| SQL / NoSQL script           | 1     | SQL or NoSQL script file *(skip for now; implement later)*                                           |
| Documentation                | 1     | .md, .txt files *(skip for now; implement later)*                                                    |
| CI/CD                        | 1     | CI/CD pipeline configuration                                                                         |
| InterProcess Communication   | *     | Node that performs IPC (pipes, shared memory, message queues); additive label                        |
| Thread Communication         | *     | Node that performs thread sync/comm (mutex, semaphore, condition var); additive label                |
| Forks Threads / Process      | *     | Node that spawns threads or processes (fork, pthread_create, threading.Thread); additive label       |
| Thread                       | 3     | Thread entry point or runnable (target of threading.Thread, Runnable.run())                          |


**Label hierarchy:**

- **Primary (core) labels** — CodeUnit/Function/Method, Container/Class, StaticMember, Interface, Module/File, External, Lambda, Database, try, except/catch, Instantiator/Constructor, Destructor, InnerClass, Object/Instance, Internal, Abstract, Enum. These are created in Phase 1.
- **Secondary labels** — Accept_call_over_network, Sends_data_over_network, Event, Testing, InterProcess Communication, Thread Communication, Forks Threads/Process, Thread, etc. Added in Phase 2. **A node must have a primary label before it can receive any secondary label.**
- **Tertiary labels** — Container (Dockerfile), Markup Lang file, SQL/NoSQL script, Documentation, CI/CD. Added by file extension. These files are ingested differently: the entire file is a single node and is **not embedded**.

To support multiple languages, each node has:

- A **shared base label**: e.g. `:CodeNode` plus semantic labels from the table above.
- Optional **language-specific labels**: e.g. `:JavaClass`, `:PythonModule`, `:CSharpPartialClass` where needed.
- A `**language` property**: e.g. `"python"`, `"java"`, `"typescript"`, etc.
- A `**level` property (int)** — derived from the primary label as shown above.

**Common node properties (illustrative):**

- `id` – Stable internal identifier.
- `codebase_id` – UUID of the codebase this node belongs to. **Present on every node. All queries filter by this property first.**
- `name` – Symbol name, file name, or logical identifier.
- `language` – Source language string.
- `level` – Hierarchical level (derived from labels).
- `path` – Relative file path from the repository root.
- `storage_ref` – Object key pointing to the raw source file in Supabase Storage (e.g. `codebases/{codebase_id}/files/{relative_path}`). Combined with `start_line` / `end_line`, this is how raw code is retrieved at query time. **Raw code is never stored directly on the node.**
- `start_line`, `end_line` – Source range within the file at `storage_ref`.
- `signature` – Function/method/class signature or declaration line (compact, metadata-only).
- `annotations` – Decorators/annotations associated with the node (e.g. `@cache`, `@Override`), when present; captured from LSP (e.g. `textDocument/hover`).
- `docstring` / `documentation` – Docstring or leading comments (compact, metadata-only).
- `properties` – Variables whose scope is within the node (e.g. as a list of names or a structured map).
- `embedding` – Vector embedding of the node content (stored as a vector property in Neo4j).

> **Redundant properties removed:** Properties like `kind` are not stored on nodes — the node's semantic type is fully defined by its labels.

> **What nodes do NOT store:**
>
> - Raw code body — stored in Supabase Storage; retrieved on demand via `storage_ref`.
> - File content hash — stored in the Supabase `file_manifest` table for change-detection purposes only. Not needed on the node itself.

#### Chunking and Embeddings

Indexing is **node-based**. Each source file is parsed into semantic chunks corresponding to nodes:

- A **chunk** can be:
  - A class or interface.
  - A function or method.
  - A `try` or `except` / `catch` block.
  - A file/module or other container-like structure.

When a node contains other nodes (e.g. a class with multiple methods, or a try block with inner lambdas), we:

- **Create explicit relationships** between the outer node and inner nodes (e.g. a `CONTAINS` edge).
- For the **outer node's embedding**, we **only include definitions of the inner nodes**, not their full bodies. This prevents:
  - Large outer nodes from duplicating full inner content.
  - Token blow-up and over-weighted large classes.

Each node's embedding input is constructed **at indexing time** from LSP-derived metadata — not from stored raw code, since raw code is not persisted on the node:

- **Code body** (extracted via LSP; nested node bodies replaced by their signatures only).
- **Comments** immediately associated with the node.
- **Docstrings** or documentation blocks.

The embedding input text is used transiently to call the OpenAI API. Only the resulting **vector** is persisted — stored directly on the node as the `embedding` property and indexed with Neo4j's vector index. The input text itself is discarded after the vector is produced.

#### Relationships

Relationships correspond to the semantic edges in `documentation/Relationships.txt`. **All relationship constraints (valid From/To label pairs) are enforced at the application level.**

**Orphan CALLS targets:** After Phase 2, some `CALLS` relationships point to target node IDs that do not exist in the crawled graph. These represent calls to external APIs, standard-library functions, or third-party packages outside the scanned repository.


| Relationship   | From                                                             | To                                                                    |
| -------------- | ---------------------------------------------------------------- | --------------------------------------------------------------------- |
| CALLS          | CodeUnit/Function, Module/File, Lambda, Instantiator/Constructor | CodeUnit/Function, Module/File, Database                              |
| SETS           | CodeUnit/Function, Module (future work)                          | StaticMember                                                          |
| GETS           | CodeUnit/Function, Module (future work)                          | StaticMember                                                          |
| CONTAINS       | Module/File, Class/Container, Interface                          | CodeUnit/Function, InnerClass (from Class only), Object, StaticMember |
| INHERITS       | Class, Interface                                                 | Class, Interface                                                      |
| IMPLEMENTS     | Interface                                                        | Class                                                                 |
| BELONGS_TO     | Object                                                           | Class                                                                 |
| OVERRIDES      | Function                                                         | Function                                                              |
| INSTANTIATES   | Constructor                                                      | Class                                                                 |
| EXCEPTION_FLOW | (future work)                                                    | (future work)                                                         |
| SPAWNS         | Forks Threads/Process                                            | Thread, Function                                                      |


Relationships are structured hierarchically:

- Edges like `CONTAINS` and `BELONGS_TO` typically go from **lower level to higher level context** or vice versa, depending on direction:
  - `(:File)-[:CONTAINS]->(:Container)`
  - `(:Container)-[:CONTAINS]->(:Function)`
  - `(:Object)-[:BELONGS_TO]->(:Class)`
  - `(:ForksThreadsProcess)-[:SPAWNS]->(:Thread)` — spawner (e.g. `threading.Thread(target=worker)`) to thread entry point (`worker`)
- The `level` property on nodes makes it easy to reason about **graph traversals by abstraction level**, e.g.:
  - High-level queries use **level 1–2 nodes** (files, modules, containers) and only edges like `CONTAINS`, `INHERITS`, `IMPLEMENTS`.
  - More detailed queries drop to **level 3+ nodes** (methods, lambdas, try/except blocks).

**Relationship attributes (examples):**

- Common attributes:
  - `source_level`, `target_level` – Redundant but convenient for query optimization.
  - `line` – Primary line number of the relationship (e.g. call site).
  - `column` (optional) – Column for more precise location.
- `CONTAINS`
  - `order` – Declaration order for stable presentation.
- `CALLS`
  - `direct` – Boolean for direct vs indirect/dispatch calls (when detectable).
  - `static_resolution` – Whether the callee is resolved statically.
  - `call_site_id` – Internal ID if multiple call sites to the same target.
- `SETS` / `GETS`
  - `member_name`, `line`.
- `INHERITS` / `IMPLEMENTS`
  - `is_abstract` – Whether the parent is abstract.
  - `line` – Declaration location.
- `BELONGS_TO`
  - `namespace` – e.g. package/module namespace.
  - `is_primary` – Whether this is the primary owner (vs. aliases).
- `OVERRIDES`
  - `line` – Override declaration line.
- `SPAWNS`
  - `line` – Spawn site (e.g. `threading.Thread(target=foo)` call).
  - `kind` (optional) – `"thread"` or `"process"` when detectable.

Data-flow (`DATA_FLOW`) and exception-flow (`EXCEPTION_FLOW`) edges are **planned for later**; the initial version focuses on structural and call/dependency relationships for simplicity and performance.

---

### Hierarchical Logical Levels

The `**level` property** on nodes and the selective use of relationships at each level allow us to implement **hierarchical retrieval**:

- **High-level queries** (architecture, components, modules):
  - Operate primarily on:
    - Nodes: `File`, `Module`, `Container` (levels 1–2).
    - Edges: `CONTAINS`, `INHERITS`, `IMPLEMENTS`, `BELONGS_TO`.
  - Output tends to be module-level or class-level results.
- **Mid-level queries** (APIs, methods, specific behaviors):
  - Operate on:
    - Nodes: `Container`, `Function`, `Method` (levels 2–3).
    - Edges: `CALLS`, `OVERRIDES`, `SETS`, `GETS`.
- **Low-level queries** (specific control flow, debugging):
  - Operate on:
    - Nodes: `Function`, `Lambda`, `TryBlock`, `ExceptBlock` (levels 3–4+).
    - Edges: `CALLS`, `SETS`, `GETS`, (future) `EXCEPTION_FLOW`.

This hierarchy also supports **token-efficient retrieval**, because high-level questions can be answered from a small set of high-level nodes and summaries, without pulling in fine-grained details unless needed.

---

### Parsing and Indexing Strategy

#### Supported Languages

The ingestion pipeline supports the following languages via **LSP (Language Server Protocol)**:

- **Java**
- **Python**
- **Go**
- **JavaScript**
- **TypeScript**
- **C / C++**
- **Rust**

Each language uses its corresponding LSP server (e.g., jdtls for Java, pyright/pylsp for Python, gopls for Go, typescript-language-server for JS/TS, clangd for C/C++, rust-analyzer for Rust).

#### LSP API Surface

The pipeline uses the following LSP methods to extract nodes and relationships:


| LSP Method                          | Purpose                                                                             |
| ----------------------------------- | ----------------------------------------------------------------------------------- |
| `textDocument/documentSymbol`       | Get all classes, functions, variables in a file — primary source for node discovery |
| `textDocument/prepareCallHierarchy` | Prepare for call analysis                                                           |
| `callHierarchy/outgoingCalls`       | Find what functions a function calls → `CALLS` relationships                        |
| `callHierarchy/incomingCalls`       | Find what calls a function → reverse `CALLS`                                        |
| `textDocument/definition`           | Resolve where symbols are defined — cross-file resolution                           |
| `textDocument/references`           | Find all usages of a symbol                                                         |
| `textDocument/typeDefinition`       | Get type information                                                                |
| `textDocument/implementation`       | Find implementations of interfaces → `IMPLEMENTS`                                   |
| `textDocument/hover`                | Get detailed type/documentation info → `docstring`, `signature`                     |
| `typeHierarchy/supertypes`          | Class inheritance → `INHERITS`                                                      |
| `typeHierarchy/subtypes`            | Class inheritance → `INHERITS`                                                      |


#### Two-Phase Crawl Strategy

Graph construction follows a **two-phase crawl** to ensure all nodes exist before cross-file relationships are created:

**Phase 1 — Nodes and `CONTAINS` only:**

1. Crawl each **new** file (one pass per file).
2. For each file:
  - Call `textDocument/documentSymbol` to get all top-level and nested symbols (classes, functions, variables, etc.).
  - Build **nodes** for each symbol (File, Container, Function, StaticMember, etc.).
  - Build **only `CONTAINS` relationships** (parent → child containment within the same file).
3. When **all** new files have been crawled once, all nodes are present in the graph.

**Phase 2 — Remaining labels and relationships:**

1. Crawl all files a **second time** (or all files that had new/modified dependencies).
2. For each file:
  - Use `callHierarchy/`*, `textDocument/definition`, `textDocument/implementation`, `typeHierarchy/*` to derive:
    - `CALLS`, `INHERITS`, `IMPLEMENTS`, `OVERRIDES`, `INSTANTIATES`, `BELONGS_TO`, `SETS`, `GETS`, `SPAWNS`
  - Add secondary labels (External, Internal, Abstract, etc.) to existing nodes. Only nodes that already have a primary label receive secondary labels.
  - Add semantic labels based on LSP responses and cross-reference resolution.

**Identifying the External label:** A node receives the **External** label when it is *not implemented by the user* and *not part of the project* — e.g. library functions, framework APIs, or third-party package symbols. Identification is done during LSP analysis: the symbol's definition resolves to a file path or module outside the scanned repository (stdlib, installed packages, or dependency imports). External is mutually exclusive with Internal.

**Modified file handling:**

If a file has been **updated** (hash differs in manifest):

1. **Delete** all existing nodes and all relationships incident to those nodes for this file path from Neo4j.
2. Treat the file as **new** and proceed to **Phase 1**.
3. After Phase 1 completes for all modified files, run **Phase 2** for the full affected set.

#### Tertiary Labels (File-Extension Based)

The following are **tertiary labels** applied by file extension. They are ingested differently from code files:

- **Container (Dockerfile)** — Dockerfile images
- **Markup Lang file** — `.json`, `.yaml`, and similar markup files
- **SQL / NoSQL script** — `.sql` and similar script files
- **Documentation** — `.md`, `.txt` files
- **CI/CD** — CI/CD pipeline configuration files

For tertiary types: the **entire file is treated as a single node**. These nodes are **not embedded**. Files matching these types are uploaded to Storage and a node is created, but no LSP parsing or embedding is performed.

#### File Filtering

When ingesting file by file, the pipeline **ignores** all files that are not textual. Only files with textual content are ingested. Specifically, the following are **skipped**:

- `**.env`** — environment/config files (may contain secrets; not useful for code search)
- **Image files** — e.g. `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.svg`, `.webp`, `.ico`
- **Audio files** — e.g. `.mp3`, `.wav`, `.ogg`, `.flac`, `.aac`, `.m4a`
- **Video files** — e.g. `.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`, `.wmv`
- **Executables** — `.exe` and other binary executables
- **Binary files** — by extension + simple content checks
- **Known auto-generated files** — e.g. based on file name patterns or headers

Only files with textual content (source code, config, markup, documentation) are ingested.

#### File Scanning & Upload

- Walk the target folder path recursively.
- **Skip** (see [File Filtering](#file-filtering) above).
- For every accepted source file:
  - Compute its **SHA-256 hash** and compare against the Supabase `file_manifest`. Skip unchanged files.
  - Upload the raw file to **Supabase Storage** at the key `codebases/{codebase_id}/files/{relative_path}`.
  - Update the `file_manifest` row with the new hash and `storage_ref`.

#### Chunk and Node Construction (from LSP)

For each symbol returned by `textDocument/documentSymbol` (and augmented by hover/typeDefinition):

1. Map LSP symbol kind to **labels** (e.g., Class → Container, Function → CodeUnit, etc.), **language**, **level**, file path, and source range.
2. Identify **child symbols** (nested classes, methods, lambdas) from the hierarchical symbol list; connect parent and children with `CONTAINS`.
3. Use `textDocument/hover` for **signature**, **docstring**, **annotations**.
4. Record `storage_ref`, `start_line`, `end_line` on each node.
5. Create or update the node in Neo4j with metadata + `storage_ref`. **Do not write raw code body to the node.**

#### Embeddings

For each node, construct the embedding input **from LSP-derived metadata** (signature, annotations from hover, docstring, and a structural outline of nested symbols as signatures only):

- Call an **OpenAI embedding model** (e.g. `text-embedding-3-small`) to generate a vector.
- Store the resulting vector in a Neo4j `embedding` property and index it.
- **Discard the embedding input text** — it is not written persistently.

#### Async Background Step — External Call Classification

For **outgoing calls** classified as **external** (target not in project), an additional async background step runs:

1. **Maintain a per-language list** of libraries, tools, frameworks, and annotations aligned with secondary labels (see `config/external_apis/` and `documentation/ExternalAPILists.md`). For each External node, cross-check against this list; if a match is found, add the corresponding secondary label to the node.

2. **API list** of known calls (per language) that initiate:
  - Database access
  - Network I/O (HTTP, gRPC, sockets, etc.)
  - Inter-process communication (IPC)
  - Thread communication (mutex, semaphore, condition variable, etc.)
  - Thread/process spawning (fork, pthread_create, threading.Thread, etc.)
3. For each external call, **cross-check** against this list. If there is a **match**:
  - Fetch the **caller file** from Storage.
  - Build a **signature-only view** of the file:
    - Import statements
    - Global variables with definitions
    - Class names and attributes
    - Function names and signatures
    - Annotations (e.g., decorators, `@Override`)
  - Send this view to an **LLM**, along with the list of nodes present in the file.
  - Ask the LLM to **classify and assign** the following labels (if applicable) to each node:
    - `Interprocess Communication`
    - `Thread Communication`
    - `Forks Threads / Process`
    - `Thread`
    - `Accept_call_over_network`
    - `Sends_data_over_network`
    - `Testing`
    - `None`
  - Attach the labels to the respective nodes in Neo4j and fill attributes accordingly.

This step runs **asynchronously** and does not block the main indexing pipeline. Labels are applied incrementally as the LLM responds.

#### Incremental Updates

Every upload to an existing codebase is a **patch**, not a full rebuild. The system maintains a **file manifest** in PostgreSQL.

**New file:** Phase 1 → Phase 2 → embed → add manifest entry.

**Modified file:** Delete nodes/edges for this path → Phase 1 → Phase 2 → embed → update manifest.

**Deleted file:** Delete nodes/edges from Neo4j, delete from Storage, remove from manifest.

**Unchanged file:** Skip entirely.

Cross-file relationships are re-evaluated in Phase 2 whenever participating files change.

---

### Query Behavior

#### Codebase Isolation

Every node in Neo4j carries a `codebase_id` property. **All queries — both vector similarity searches and Cypher graph traversals — include a mandatory `codebase_id` filter.** This filter is applied at the retrieval service layer, not just at the API boundary, making it impossible for a query to return nodes from a different codebase even if multiple codebases share the same Neo4j instance.

This means:

- A query against codebase A never touches nodes belonging to codebase B.
- Two users each having a "backend" codebase do not see each other's results.
- A user with multiple codebases must select a target codebase before querying; no cross-codebase search is offered.

#### Search and Retrieval Modes

Queries originate as **natural-language questions**. The LLM receives the query, **generates Neo4j (Cypher) query or queries**, and selects the appropriate strategy. There are two retrieval modes:

| Mode | Flow |
|------|------|
| **Context only** | Natural-language query → LLM generates Neo4j query → execute via MCP to Neo4j → return results directly to user. |
| **Context with explanation** | Natural-language query → LLM generates Neo4j query → execute via MCP to Neo4j → LLM parses question(s), may run 1+ queries until satisfied with retrieved context → LLM writes explanation → return to user. |

#### Query Strategy

The LLM chooses between:

- **Graph-only queries** — pure Cypher on Neo4j; result count depends on the question.
- **Embedding-with-graph queries** — combine vector similarity and graph constraints; fetch the **three most relevant nodes**.

#### Result Diversification

The system is designed to **prefer diversity** in results:

- After initial scoring (vector similarity + graph-based signals), apply **diversification**:
  - Avoid multiple near-duplicate results from the same file or node.
  - Spread results across different files/modules/containers when possible.

#### Snippet Retrieval

Neo4j nodes do not store raw code. After the result nodes are selected, the Snippet Fetcher retrieves the code snippet for each result from **Supabase Storage**:

1. Read `storage_ref` and `start_line` / `end_line` from the node.
2. Download the source file from Supabase Storage (`codebases/{codebase_id}/files/{path}`).
3. Slice lines `start_line` to `end_line` from the downloaded content.
4. Return the slice as the `snippet` field in the query response.

Files can be cached in-process or in Redis during a single query to avoid re-downloading the same file for multiple results that share a source file.

#### LLM Integration and Interaction

- The LLM:
  - Receives the natural-language query and **writes Neo4j (Cypher) query or queries**.
  - Chooses strategy per question: graph-only or embedding-with-graph.
  - In **context with explanation** mode: parses the question(s) in the prompt, may run one or more queries until satisfied with the retrieved context, then writes an explanation before returning.
  - Results are executed **via MCP** to the Neo4j database.

---

### Component Diagram (Textual)

High-level components and their interactions:

- **Indexing Pipeline**
  - `Repository Scanner`
    - Walks directory tree; filters out non-textual files. See [File Filtering](#file-filtering).
    - Hashes each file; compares against Supabase `file_manifest` to skip unchanged files.
    - Uploads accepted source files to **Supabase Storage** (`codebases/{id}/files/{path}`); updates manifest.
  - `LSP Client & Server Manager`
    - Manages LSP server processes per language (Java, Python, Go, JS, TS, C/C++, Rust).
    - Opens documents, sends LSP requests, receives symbol/call/definition/hover/typeHierarchy responses.
  - `Phase 1 Crawler` (nodes + CONTAINS)
    - For each new/modified file: calls `textDocument/documentSymbol`; builds nodes and `CONTAINS` relationships only.
  - `Phase 2 Crawler` (remaining relationships)
    - After all new files crawled: uses `callHierarchy/`*, `definition`, `implementation`, `typeHierarchy/*` to add `CALLS`, `INHERITS`, `IMPLEMENTS`, `OVERRIDES`, etc.
  - `Node & Relationship Extractor`
    - Maps LSP responses to nodes and edges; records `storage_ref`, `start_line`, `end_line` on each node.
  - `Embedding Generator`
    - Constructs embedding input from LSP-derived metadata (signature + body outline + docstring + comments).
    - Calls OpenAI embedding API; discards the input text after receiving the vector.
  - `Graph Writer`
    - Persists nodes (metadata + `storage_ref` + `embedding`), relationships into Neo4j.
  - `External Call Classifier` (async background)
    - Cross-checks external calls against per-language API lists (DB, network, IPC, threads).
    - On match: builds signature-only view, sends to LLM, applies labels (Interprocess Communication, Thread, Accept_call_over_network, etc.).
- **Query Pipeline**
  - `Client / Coding Agent`
    - Issues natural-language questions and receives answers (context only or context with explanation).
  - `Query API`
    - HTTP/gRPC API surface that accepts queries and returns results.
  - `LLM Orchestrator`
    - Receives natural-language query; writes Neo4j (Cypher) query or queries; chooses strategy (graph-only or embedding-with-graph). In context-with-explanation mode, may run 1+ queries until satisfied, then writes explanation.
  - `MCP`
    - Executes queries against Neo4j database.
  - `Graph & Vector Engine (Neo4j)`
    - Stores graph and embeddings; receives Cypher queries via MCP.
  - `Snippet Fetcher`
    - After result nodes are selected, downloads source files from Supabase Storage and slices `start_line`–`end_line` per node.
    - Caches file downloads within a single query to avoid redundant fetches.
  - `Result Aggregator`
    - Merges, ranks, and diversifies results.
    - Constructs compact code/context snippets for downstream LLM use (minimizing token usage).

Textual flow:

1. **Indexing time**
  - Repository Scanner (hash check + Storage upload + manifest update) → LSP Client opens files → **Phase 1 Crawler** (documentSymbol → nodes + CONTAINS) → **Phase 2 Crawler** (callHierarchy, definition, typeHierarchy → remaining relationships) → Node & Relationship Extractor → Embedding Generator → Graph Writer.
  - **Async:** External Call Classifier (cross-check external calls → LLM classification → apply labels).
2. **Query time**
  - Client/Agent → Query API → LLM Orchestrator (writes Cypher) → MCP → Neo4j → results back. For context-with-explanation: LLM may run multiple queries until satisfied, then writes explanation. Snippet Fetcher retrieves raw code from Storage when applicable.

---

### Tech Stack

**Core technologies:**

- **Language**: Python (indexing pipeline, APIs, and orchestration).
- **Graph Database**: Neo4j (primary store for nodes, relationships, and embeddings).
  - Nodes store metadata + `storage_ref` + `embedding` vector. **No raw code bodies.**
  - Uses **vector indexes** for fast similarity search over node embeddings.
- **Object Storage**: Supabase Storage — stores raw source files at `codebases/{codebase_id}/files/{path}`. Snippets are fetched from here at query time using `storage_ref` + line range from the node.
- **Relational DB**: Supabase (PostgreSQL) — stores `file_manifest` (path + hash + `storage_ref`) for change detection, plus all application tables (query logs, feedback, ingestion history).
- **LLM & Embeddings**: OpenAI
  - LLM model (e.g. GPT family) for query interpretation and answer synthesis.
  - Embedding model (e.g. `text-embedding-3-small`) for node vectors.

**Parsing / Analysis:**

- **LSP (Language Server Protocol)** — each supported language uses its LSP server:
  - **Java** — jdtls (Eclipse JDT Language Server)
  - **Python** — pyright, pylsp, or pyright
  - **Go** — gopls
  - **JavaScript / TypeScript** — typescript-language-server (or tsserver)
  - **C / C++** — clangd
  - **Rust** — rust-analyzer

**API & Services:**

- **FastAPI** (or similar Python framework) for:
  - Indexing commands (e.g. trigger reindex of a path).
  - Query endpoints for coding agents and tools.

**Infrastructure & Operations:**

- Deployable in a **local dev environment** (for private repo analysis) or as a service.
- Incremental indexing to keep cost and latency low.
- Designed to integrate directly into coding agents for **LLM-enhanced code search and reasoning**.

---

### Future Enhancements

- Add **DATA_FLOW** and **EXCEPTION_FLOW** edges for deeper debugging and analysis.
- Expand language support and better handle language-specific features (mixins, traits, partials).
- Improve query planning logic for more sophisticated combinations of graph constraints and semantic similarity.

