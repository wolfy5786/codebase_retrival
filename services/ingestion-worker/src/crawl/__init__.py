"""
Crawl pipeline for LSP-based code indexing.

Phase 1: ``CodeNode`` (+ optional file-type label), structural properties
including ``kind``/``detail``, and ``CONTAINS`` edges.

Phase 2 Tier 1 (``phase2.crawl_phase2_tier1``): semantic labels, Tier-1
properties, and Java ``INHERITS`` / ``IMPLEMENTS`` candidates (merged in
``graph_writer``).

Phase 2 Tier 3 (``phase2_tier3.crawl_phase2_tier3``): LSP-based ``definition_uri``,
``Object``/``Instance``, ``CALLS`` / ``SETS`` / ``GETS`` (merged in ``graph_writer``).
"""
