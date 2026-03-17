"""
Test script: runs a query on Neo4j and returns node/relationship counts for a codebase.
Use to confirm the graph was written for a specific ingestion.

Run: python -m src.test_graph <codebase_id>
Or:  docker compose run --rm ingestion-worker python -m src.test_graph <codebase_id>
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env for local runs (Docker injects env via compose)
_candidates = [Path.cwd() / ".env", Path.cwd().parent / ".env"]
try:
    _me = Path(__file__).resolve()
    if len(_me.parents) >= 3:
        _candidates.insert(0, _me.parents[2] / ".env")
except (IndexError, AttributeError):
    pass
for p in _candidates:
    if p.exists():
        load_dotenv(p, override=True)
        break
else:
    load_dotenv()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m src.test_graph <codebase_id>", file=sys.stderr)
        sys.exit(1)

    codebase_id = sys.argv[1]

    from .graph_writer import GraphWriter

    try:
        writer = GraphWriter()
        try:
            stats = writer.get_graph_stats_for_codebase(codebase_id)
            print(
                f"Neo4j graph stats for codebase_id={codebase_id}: "
                f"nodes={stats['node_count']}, relationships={stats['relationship_count']}"
            )
        finally:
            writer.close()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
