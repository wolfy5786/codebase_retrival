# External API Lists for Call Classification

This document describes the per-language API lists used by the **External Call Classifier** during ingestion. When an outgoing call is classified as **external** (target not in project), the classifier cross-checks it against these lists. On match, the caller file is sent to an LLM for label assignment.

---

## Purpose

APIs in these lists initiate:

- **Database access** — SQL drivers, ORMs, NoSQL clients
- **Network I/O** — HTTP, gRPC, WebSocket, raw sockets
- **Messaging / communication frameworks** — message queues (RabbitMQ, SQS), event streaming (Kafka), bridges, pub/sub (Redis, NATS), MQTT
- **Inter-process communication (IPC)** — pipes, shared memory, Unix domain sockets
- **Thread communication** — mutex, semaphore, condition variable, thread-safe queue
- **Thread/process spawning** — fork, pthread_create, threading.Thread, multiprocessing.Process

---

## JSON Schema

Each language has a file `{language}.json` in `config/external_apis/` with this structure:

```json
{
  "language": "python",
  "categories": {
    "database": {
      "description": "APIs that access databases",
      "entries": [
        { "module": "sqlite3", "symbol": "connect", "label": "Database" },
        { "module": "psycopg2", "symbol": "connect", "label": "Database" }
      ]
    },
    "network_send": {
      "description": "APIs that send data over the network",
      "entries": [
        { "module": "urllib.request", "symbol": "urlopen", "label": "Sends_data_over_network" },
        { "module": "requests", "symbol": "get", "label": "Sends_data_over_network" }
      ]
    },
    "network_accept": {
      "description": "APIs that accept calls over the network",
      "entries": [
        { "module": "http.server", "symbol": "HTTPServer", "label": "Accept_call_over_network" }
      ]
    },
    "messaging": {
      "description": "Message queues, Kafka, SQS/SNS, Redis pub/sub, NATS, MQTT, bridges",
      "entries": [
        { "module": "kafka", "symbol": "*", "label": "InterProcess Communication" }
      ]
    },
    "ipc": {
      "description": "Inter-process communication",
      "entries": [
        { "module": "multiprocessing", "symbol": "Pipe", "label": "InterProcess Communication" }
      ]
    },
    "thread_comm": {
      "description": "Thread synchronization/communication",
      "entries": [
        { "module": "threading", "symbol": "Lock", "label": "Thread Communication" }
      ]
    },
    "fork_spawn": {
      "description": "Thread/process spawning",
      "entries": [
        { "module": "threading", "symbol": "Thread", "label": "Forks Threads / Process" }
      ]
    }
  }
}
```

### Entry Fields

- **module** — Package/module/namespace (e.g. `java.net`, `net/http`, `std::thread`)
- **symbol** — Function, class, or method name (supports prefix match or exact)
- **label** — Neo4j label to attach when LLM confirms (optional; LLM can override)

### Matching Rules

- Match is **hierarchical**: `module` + `symbol` (e.g. `requests.get` in Python, `java.net.Socket` in Java).
- If the external call resolves to a symbol within a listed `module` and matches `symbol`, it triggers LLM classification.
- `symbol` can be `"*"` to match any symbol in that module (e.g. entire `socket` module).

---

## LLM Classification Flow

1. External call matches an entry in the API list.
2. Fetch caller file from Storage.
3. Build **signature-only view**:
   - Import statements
   - Global variables with definitions
   - Class names and attributes
   - Function names and signatures
   - Annotations (decorators, `@Override`, etc.)
4. Send to LLM with list of nodes in the file.
5. LLM returns label assignments: `Interprocess Communication`, `Thread Communication`, `Forks Threads / Process`, `Thread`, `Accept_call_over_network`, `Sends_data_over_network`, `Testing`, or `None`.
6. Apply labels and attributes to nodes in Neo4j.

---

## Adding or Updating API Lists

1. Edit the appropriate `{language}.json` in `config/external_apis/`.
2. Add entries under the relevant category (`database`, `network_send`, `network_accept`, `ipc`, `thread_comm`, `fork_spawn`).
3. Use the canonical module/symbol for the language (e.g. Java: `java.net.http.HttpClient`, Python: `asyncio`).
4. Run tests to ensure matching logic still works.
