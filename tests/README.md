# tests

Zero-dependency tests (stdlib only, no pytest) — matching `tools/doc_graph.py`'s
own constraint. Run directly:

```bash
python3 tests/test_doc_graph.py     # parsing layer: md→md + md→code bridge
python3 tests/test_rct.py           # the rct CLI verbs, end-to-end via subprocess
```

Each exits 0 on pass, 1 on failure.

## What's covered

`test_doc_graph.py` runs `doc_graph.py` against `fixtures/sample/`, a tiny tree
encoding the four cases from the plan:

| Fixture | Asserts |
|---------|---------|
| `fixtures/sample/docs/ai/module/README.md` (reachable, cited from the index) | counts as a reachable doc, not an orphan |
| `fixtures/sample/docs/ai/orphan.md` (nothing links to it) | flagged as the one orphan / unreachable |
| a Key-Files row citing `src/real_module.py` (exists) | yields exactly one `code_edge` |
| a Key-Files row citing `src/deleted_module.py` (absent) | yields exactly one `code_broken` |

The md→md assertions are the regression guard: they must stay identical as the
md→code bridge evolves.

> Note: the fixtures live under `tests/`, not `docs/ai/`, so a normal
> `python3 tools/doc_graph.py` run (which auto-detects `docs/ai/`) never scans
> them. The test points the tool at the fixture explicitly via `--root`/`--docs`.
