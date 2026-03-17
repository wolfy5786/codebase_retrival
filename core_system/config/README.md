# External API Lists — Configuration

This directory contains per-language JSON files listing external APIs that trigger LLM-based node classification when an external call matches.

## Structure

```
config/
├── README.md           # This file
└── external_apis/
    ├── python.json
    ├── java.json
    ├── go.json
    ├── javascript.json
    ├── typescript.json
    ├── cpp.json
    └── rust.json
```

## Usage

The **External Call Classifier** (async background step in the ingestion pipeline) loads these files and cross-checks outgoing external calls. When a call targets a symbol in one of these lists, the caller file is sent to an LLM to assign labels such as:

- `Interprocess Communication`
- `Thread Communication`
- `Forks Threads / Process`
- `Thread`
- `Accept_call_over_network`
- `Sends_data_over_network`
- `Testing`

See [ExternalAPILists.md](../documentation/ExternalAPILists.md) for the full schema and matching rules.

## Adding APIs

1. Choose the language file (e.g. `external_apis/python.json`).
2. Add an entry under the appropriate category: `database`, `network_send`, `network_accept`, `messaging`, `ipc`, `thread_comm`, `fork_spawn`.
3. Use the format: `{ "module": "...", "symbol": "...", "label": "..." }`.

## Path Resolution

At runtime, the indexer resolves these config files relative to the project root or via the `EXTERNAL_API_CONFIG_PATH` environment variable.
