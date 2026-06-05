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
- **The md→code bridge:** also harvests backtick citations of *source* files
  (the Key-Files style, `` `path/to/file.py` ``) and reports them as
  `code_edges` (the cited file exists) and **stale code citations**
  (`code_broken` — a doc cites a code path that resolves nowhere: a deleted/
  renamed/typo'd file). This is **purely additive** — md→md reachability,
  orphans, and the `--check` exit code are byte-identical to before the bridge.
  The stale-citation list is printed as **information**; the hard gate over it
  lives in the `rct` CLI (`rct verify`), not in `--check` here.
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
`backend/foo.py`          inline-backtick CODE path -> md→code bridge (not an .md edge)
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

## rct.py — agent-facing verbs over the tree

`rct.py` is a thin CLI on top of `doc_graph.py`: it **imports** that module's
parsing primitives (never reimplements them) and turns the md→code bridge into
the commands an agent needs around editing, creating, and deleting code. Every
command recomputes from real files + git at call time — nothing is stored, so
nothing can silently go stale. It writes **no files**.

| Command | What it answers | Gate? |
|---------|-----------------|-------|
| `rct refs <code_file>` | Which docs cite this file? **Run before editing** — these are the docs you may need to reconcile after. | — |
| `rct verify [<doc>\|--all]` | Does every code path a doc cites still exist on disk? | **Hard** — exits 1 on a dead citation (zero false positives: a path resolves or it doesn't). Working-tree truth. |
| `rct orphans` | md→md reachability — orphans / unreachable / broken md links. | Exits 1 on any md problem (same signal as `doc_graph.py --check`). |
| `rct stale [<doc>\|--all]` | Was a doc's cited code **committed** more recently than the doc? | **Warn only** — heuristic; only you know if the change was doc-worthy. Reflects committed history, not the working tree. |
| `rct undocumented [<f>\|--all]` | Which tracked source files does no doc cite? | **Advisory only** — RCT documents modules, not every file. Built-in ignores skip migrations/tests/generated; extend with a `.rctignore`. |
| `rct guard [--staged\|--ci --base <ref>]` | Commit / CI gate. | Implemented in Phase 3. |

```bash
python3 tools/rct.py refs backend/payments/services.py   # before you edit it
python3 tools/rct.py verify --all                        # CI/working-tree hard check
python3 tools/rct.py orphans                             # reachability
python3 tools/rct.py stale --all                         # git-derived staleness (warn)
```

Shared flags `--root` / `--docs` / `--entry` mean exactly what they do for
`doc_graph.py`. The split is deliberate: **hard-block only on what's certain**
(a cited path that doesn't resolve), **warn on everything uncertain** (code
moved but the doc didn't). A gate that's always right when it fires is one nobody
disables.

### `verify` is diagnostic, not just pass/fail

The resolver stays strict (a path that doesn't resolve **as written** is broken),
but the output classifies each failure against the files that actually exist, so
adopting RCT on a repo whose docs aren't yet normalized gives you a fix-list, not
a wall of cryptic errors:

- **LIKELY PATH-STYLE MISMATCH** — a file of that name clearly exists; `verify`
  prints `did you mean → backend/x/y.py`. Usually a module-relative or bare
  citation that should be repo-root-relative. One-click rewrites.
- **AMBIGUOUS** — several files match the name; a human picks.
- **NO MATCHING FILE** — nothing by that name exists anywhere → a genuine
  deleted/renamed/typo'd file. **These are the real doc↔code gaps.**

So "75 failures" becomes "66 style rewrites + N ambiguous + the handful of real
gaps" — and a moved file is no longer indistinguishable from a mis-styled path.

### What RCT does *not* check (by design)

It verifies **existence** (does the cited path resolve?) and **git-time**
staleness — never **semantic** sync. A doc that says "11 ViewSets" when the code
has 13 still passes `verify`: the file exists, so the citation is valid. Prose
accuracy is a human-review concern; RCT keeps the mechanical claims honest so
review can focus on the rest. Also note: **bare-filename citations** (`` `models.py` ``,
no `/`) are intentionally invisible to the tooling — adopt the backtick
repo-root-relative convention (see [`docs/ai/TEMPLATE.md`](../docs/ai/TEMPLATE.md))
to make them checkable.
