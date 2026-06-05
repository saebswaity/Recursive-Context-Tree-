# Recursive Context Tree — AI Context (this repo's own tree)

This repo **dogfoods the pattern it documents.** This file is the universal,
on-demand entry point: an AI tool told "read `docs/ai/README.md`" navigates from
here. (There is no `CLAUDE.md` in this repo, so `tools/doc_graph.py` also treats
this file as the reachability root.)

## What lives here

| Doc | What it is |
|-----|------------|
| [TEMPLATE.md](./TEMPLATE.md) | The module-README stencil. Two regions: **checkable** Key Files (tool-verified) and **intent** prose (human-owned). |
| [decisions/](./decisions/) | ADR-style "considered & rejected" records — reachable by construction. |

## The conventions the tooling depends on

Two rules make the docs machine-checkable without a parser ever guessing at prose:

1. **Key-Files citation format — a hard convention.** Every code-file reference
   in a Key Files table is a **single-backtick, repo-root-relative path**, one
   per row — e.g. `` `tools/doc_graph.py` ``. The leading directory component
   (the `/`) is what lets `doc_graph.py` resolve and check it. A bare filename
   in prose is *not* a citation and is deliberately ignored.
2. **Checkable vs. intent, kept separate.** The Key Files table holds claims the
   tools verify against disk. Critical Patterns and Decisions hold the human's
   "why" — the tools check only that the doc is *reachable*, never its content.

See [TEMPLATE.md](./TEMPLATE.md) for the full layout, and the root
[README](../../README.md) for the pattern and the division of labor.

## How this repo's own code is documented

| File | Purpose |
|------|---------|
| `tools/doc_graph.py` | Reachability / orphan / broken-link checker + the md→code citation harvester. |
| `tools/rct.py` | Agent-facing verbs (refs / verify / orphans / stale / undocumented) over the bridge. |

Both are documented in [tools/README.md](../../tools/README.md).

## Maintaining this tree

```bash
python3 tools/doc_graph.py            # regenerate the graph + orphan/citation report
python3 tools/doc_graph.py --check    # CI gate: exit 1 on any orphan/unreachable/broken md

python3 tools/rct.py refs <file>      # which docs cite a code file (run before editing)
python3 tools/rct.py verify --all     # hard check: every cited code path exists on disk
python3 tools/rct.py stale --all      # git-derived staleness (warning only)
```
