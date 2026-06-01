# tools

Maintenance scripts for a Recursive Context Tree. Zero-dependency Python (stdlib only).

## doc_graph.py — reachability / orphan / broken-link checker

The Recursive Context Tree works **only if every doc is reachable by following links
from an always-loaded entry point** (the root `CLAUDE.md`, plus any auto-loaded
`backend/`/`frontend/` `CLAUDE.md`). A doc nothing links to is invisible to a
navigating agent — see [The Reachability Problem](../README.md#the-reachability-problem-the-patterns-biggest-blind-spot)
in the main README.

This script makes reachability a one-command fact.

### What it does
- Parses every link between `.md` files under the docs root.
- Computes which docs are **reachable** from the entry file(s) via BFS.
- Flags **orphans** (nothing links in), **unreachable** (island clusters), and
  **broken links** (target missing).
- Emits a **Mermaid** graph (`doc_graph.md` — renders on GitHub, commit it) and an
  **interactive D3 HTML** (`doc_graph.html` — git-ignore it, regenerate locally).

### Usage
```bash
# from repo root (defaults assume <repo>/tools/doc_graph.py and auto-detect docs/)
python3 tools/doc_graph.py                  # regenerate graph + orphan report
python3 tools/doc_graph.py --no-html        # skip the HTML (faster, for CI)
python3 tools/doc_graph.py --check          # exit 1 if any orphan/unreachable/broken

# point at a specific layout / another repo:
python3 tools/doc_graph.py --root /path/to/repo --docs /path/to/repo/docs/ai \
        --entry /path/to/repo/CLAUDE.md
```

### Link dialects it understands
Examples shown fenced so the checker doesn't count them as real edges:

```
[label](./file.md)        standard markdown link
[label](./dir/)           folder-link -> resolves to dir/README.md
`docs/ai/foo.md`          inline-backtick path citation (Key-Files style)
@docs/ai/README.md        @import (honored in CLAUDE.md files only)
```

Links inside fenced code blocks and `<!-- comments -->` are **ignored** — they're
examples, not navigation. A checker that misses a dialect your docs actually use will
manufacture false orphans, so extend the regexes if your tree uses others.

### CI note
`--check` exits 1 on **any** orphan/unreachable/broken (absolute count, not a delta).
Only wire it to CI **after** the tree is clean, or it fails every PR and gets disabled.
A delta-gate (fail only on *new* problems vs a committed baseline) is the durable form.

### Outputs
- `doc_graph.md` — commit it (renders on GitHub).
- `doc_graph.html` — git-ignore it (large, stale-on-change, needs a CDN for d3).
