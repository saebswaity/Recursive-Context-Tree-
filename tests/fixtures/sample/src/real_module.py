"""A real source file the fixture's module doc cites — proves a code_edge.

The matching `src/deleted_module.py` is deliberately absent so the doc that
cites it produces a code_broken (the unfakeable stale-citation signal).
"""


def hello():
    return "i exist on disk"
