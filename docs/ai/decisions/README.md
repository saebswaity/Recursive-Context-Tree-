# Decisions (ADRs)

"Considered & rejected" knowledge — the highest-value, most-orphaned context the
pattern preserves. Indexed here so every record is **reachable by construction**
from the docs root (an unlinked decision doc is invisible — worse than no doc).

One file per decision, numbered. Status: `accepted` · `superseded` · `rejected`.

| # | Decision | Status |
|---|----------|--------|
| [0001](./0001-md-to-code-bridge.md) | Harvest md→code citations additively; gate only on certain breaks | accepted |

## Writing a new ADR

Copy the shape of an existing one: **Context → Decision → Alternatives considered
→ Consequences**. Add a row above and link it. Keep it short; link the code or
proposal it concerns with a backtick repo-root-relative path so the citation is
checkable.
