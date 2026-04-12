"""
Crawl pipeline for LSP-based code indexing.

Phase 1: ``CodeNode`` (+ optional file-type label), structural properties
including ``kind``/``detail``, and ``CONTAINS`` edges.

Phase 2 Tier 1 (``phase2.crawl_phase2_tier1``): semantic labels and Tier-1
properties on existing nodes; relationships are handled in later tiers.
"""
