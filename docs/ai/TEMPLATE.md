# Module-README Template

Copy the fenced stencil below into `docs/ai/{module}/README.md` and fill it in.
It separates two kinds of claim so the tooling can check the mechanical ones and
stay out of the human ones.

## The two regions (this separation is the whole point)

| Region | Section(s) | Who owns it | What the tools do |
|--------|------------|-------------|-------------------|
| **Checkable** | **Key Files** | author picks; disk decides | `doc_graph.py` / `rct verify` confirm every cited path exists; `rct refs` reverse-looks-up |
| **Intent** | **Critical Patterns**, **Decisions** | the human/agent author | tools check **reachability only** — never the content, never auto-authored |

A tool may **verify** a Key-Files path and **suggest** candidates, but a human
**picks** what goes in the table. The choosing is the value — never auto-fill it
from an AST.

## The one hard format rule

Every code-file reference in the **Key Files** table is a **single-backtick,
repo-root-relative path**, one per row:

- ✅ `` `backend/payments/services.py` `` — has a directory component; resolvable.
- ❌ `services.py` in prose — a bare filename is not a citation; tools ignore it.
- ❌ a path inside a fenced ``` block — stripped before parsing (it's an example).

That single rule is what lets the checker resolve and verify citations without
guessing at prose.

## Freshness: `Last verified` is optional and NOT a gate

Keep `Last verified:` only as an honest human annotation if you find it useful.
It is **never** gate-enforced and is **not** the authoritative staleness signal —
a forced timestamp just trains a meaningless edit. Git-derived staleness
(`rct stale`, which compares the commit times of a doc and the code it cites) is
the real signal. (See the root README's "Keeping Docs Fresh".)

---

## The stencil (copy from here)

```markdown
# Module Name

> One-line description of what this module does.
> Last verified: YYYY-MM-DD   (optional, honest-only — never gate-enforced)

## Current State
- What exists right now (3-5 bullets). "What IS", not "what was done".

## Key Files
<!-- CHECKABLE REGION. Backtick, repo-root-relative paths, one per row.
     Every path here is verified to exist on disk by the tooling. -->

| File | Purpose |
|------|---------|
| `backend/module/models.py` | Models and relationships |
| `backend/module/services.py` | Business logic |
| `frontend/src/components/module/MainComponent.tsx` | Primary UI |

## How It Works
Brief explanation of the main flow — 5-10 lines max.

## Critical Patterns
<!-- INTENT REGION. Human-owned. Tools never read this for content. -->
- Things an agent MUST know to not break this module.
- "Never do X directly, always go through Y."

## Decisions
<!-- INTENT REGION. What was considered and rejected, and why.
     For anything substantial, write a full ADR under docs/ai/decisions/
     and link it here so it is reachable by construction. -->
- Chose A over B because ... (link to docs/ai/decisions/NNNN-... if it's a big one)

## Related Modules
- [other-module](../other-module/) — how they connect
```
