# 0001 — Harvest md→code citations additively; gate only on certain breaks

**Status:** accepted

## Context

`tools/doc_graph.py` already resolves every backtick path a doc cites. For `.md`
targets it records navigation edges; for paths that resolve to **source code**
outside the doc set it used to *silently discard* the result (the old `add()`
comment literally said "silently ignore"). That discarded edge is the one piece
of information that ties a slowly-changing doc to the fast-changing code it
describes — the staleness signal the pattern most needs and least had.

## Decision

Capture those code citations as two new outputs of `collect()` —
`code_edges` (the cited file exists) and `code_broken` (it resolves nowhere) —
**purely additively**: the existing `files` / `edges` / `broken` md→md outputs,
reachability, orphans, and the `--check` exit code are byte-identical to before.

A citation counts only if it is a concrete path (contains a `/`), matching the
locked Key-Files convention. A non-resolving citation is reported `code_broken`
only when it carries a recognized code extension. Bare-filename prose, globs, and
call syntax are ignored.

The hard gate lives in the forthcoming rct CLI (tools/rct.py), not here:
`doc_graph.py` only *surfaces* `code_broken` as informational output.

## Alternatives considered

- **Build an AST / code→code extractor in RCT.** Rejected: that is graphify's job
  (33 languages, per-language resolution). RCT's unique contribution is exactly
  the md→code bridge graphify can't produce; duplicating the AST layer would make
  RCT a worse graphify clone. RCT *imports* graphify's graph if present.
- **Store a persisted doc↔code index.** Rejected: a stored index that isn't
  rebuilt is the orphan disease wearing a new hat. Every command recomputes from
  real files + git at call time (derive, never store).
- **Hard-block whenever cited code is merely *modified*.** Rejected: only the
  human knows if an edit was doc-worthy; forcing a doc edit on every code change
  trains fake edits. Modified-but-undocumented is a **warning**; only a deleted/
  renamed cited file (provably dead) is a block.

## Consequences

- A doc that cites a deleted/renamed/typo'd code path is now mechanically
  detectable — the unfakeable staleness signal.
- The signal is zero-false-positive by construction (path must resolve or not),
  which is what makes it safe to hard-gate later.
- Docs must follow the backtick repo-root-relative Key-Files convention to be
  seen; bare-filename citations are invisible to the bridge by design.
