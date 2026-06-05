#!/usr/bin/env python3
"""Tests for doc_graph.py — md->md behavior AND the md->code bridge.

Zero deps (no pytest): plain asserts, run directly. Matches doc_graph.py's
own stdlib-only constraint for the report path.

    python3 tests/test_doc_graph.py        # exits 0 on pass, 1 on failure

The fixture under tests/fixtures/sample/ encodes the four cases from the plan:
  - a reachable module doc          (docs/ai/module/README.md)
  - an orphan doc                   (docs/ai/orphan.md — nothing links to it)
  - a doc citing a REAL code file   (-> src/real_module.py, a code_edge)
  - a doc citing a DELETED code path (-> src/deleted_module.py, a code_broken)
"""
import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))

import doc_graph  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "sample")
DOCS = os.path.join(FIXTURE, "docs", "ai")
ENTRY = os.path.join(DOCS, "README.md")

_fail = []


def check(cond, msg):
    print(("  ok  " if cond else "FAIL  ") + msg)
    if not cond:
        _fail.append(msg)


def bases(paths):
    """Map abs paths to a repo-relative-ish basename for stable assertions."""
    return sorted(os.path.basename(p) for p in paths)


def configure_fixture():
    doc_graph.configure(SimpleNamespace(root=FIXTURE, docs=DOCS, entry=[ENTRY]))


def main():
    configure_fixture()
    (files, edges, broken, orphans, unreachable, reachable, incoming,
     code_edges, code_broken) = doc_graph.analyze()

    print("md->md (must be unchanged by the bridge):")
    check(len(files) == 3, f"3 docs found (got {len(files)})")
    check(len(edges) == 1, f"1 md->md edge: index -> module (got {len(edges)})")
    check(len(broken) == 0, f"0 broken md links (got {len(broken)})")
    check(bases(orphans) == ["orphan.md"],
          f"orphan.md is the only orphan (got {bases(orphans)})")
    check(bases(unreachable) == ["orphan.md"],
          f"orphan.md is the only unreachable (got {bases(unreachable)})")

    print("md->code bridge:")
    check(len(code_edges) == 1,
          f"exactly 1 code_edge (got {len(code_edges)}: {bases(p for _, p in code_edges)})")
    if code_edges:
        _, dst = code_edges[0]
        check(os.path.basename(dst) == "real_module.py",
              f"the code_edge points at real_module.py (got {os.path.basename(dst)})")

    check(len(code_broken) == 1,
          f"exactly 1 code_broken (got {len(code_broken)}: {[c for _, c in code_broken]})")
    if code_broken:
        _, raw = code_broken[0]
        check(raw == "src/deleted_module.py",
              f"the code_broken cites src/deleted_module.py (got {raw})")

    print()
    if _fail:
        print(f"{len(_fail)} FAILURE(S)")
        sys.exit(1)
    print("ALL PASSED")


if __name__ == "__main__":
    main()
