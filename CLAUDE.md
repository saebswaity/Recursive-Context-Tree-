<!--
  PORTABLE AGENT INSTRUCTION TEMPLATE
  ───────────────────────────────────
  Copy this file to a new project's ROOT as BOTH `CLAUDE.md` (Claude Code) and
  `AGENTS.md` (Cursor / Codex / other agents), or symlink one to the other.
  Then find-and-replace every {{PLACEHOLDER}} below. Delete this comment block
  and any section that does not apply. Keep the "READ FIRST" gate verbatim —
  it is the part that makes agents actually use your docs.
-->

# {{PROJECT_NAME}}

{{ONE_LINE_PROJECT_DESCRIPTION}}

---

## ⛔ READ FIRST — Mandatory Context Gate (do not skip)

**You may not write, edit, or review code until you have read the docs for the module you are touching.** This is a hard precondition, not advice. The cost of reading two short files is minutes; the cost of guessing wrong in a {{DOMAIN}} system is silent data corruption and a rewrite.

Before your FIRST code action in any task, run this protocol:

1. **Locate the module.** Map the request to a module folder under `docs/ai/`. If unsure which, read `docs/ai/README.md` (the module index) first.
2. **Read that module's `README.md` in full.** It states the current architecture, key files, API surface, and the patterns you must not break.
3. **Read any cross-cutting doc the task touches** — listed in `docs/ai/_conventions/` and `docs/ai/_ux_principles/` (or your project's equivalents). A table change, a form, a money column → read the matching convention first.
4. **Check for `_progress.md`** in the module folder. If present, work was interrupted — read it before continuing so you don't redo or contradict it.
5. **Only now** state your plan and begin.

If you skip this gate, you are operating on assumptions. State explicitly in your first message which doc files you read. If a doc and the code disagree, surface the conflict — do not silently pick one.

> Why this gate exists: generic web/coding defaults are frequently **wrong** for this project. The docs encode {{N_YEARS_OR_DOMAIN}} of hard-won, domain-specific decisions that override those defaults whenever they conflict.

---

## Stack
- Backend: {{BACKEND_STACK}}
- Frontend: {{FRONTEND_STACK}}
- Data / infra: {{DATA_INFRA}}
- {{OTHER_KEY_TECH}}

## Architecture Map
```
{{MODULE_DEPENDENCY_DIAGRAM}}
```

## Where Things Live (non-negotiable placement rules)
- Business logic → `{{SERVICES_LOCATION}}` — NEVER in views, serializers, or components.
- API calls (frontend) → `{{API_CLIENT_FILE}}` — one source of truth, no ad-hoc fetches.
- Server state → {{SERVER_STATE_LIB}} — no manual fetch/useState for API data.
- Shared UI primitives → `{{UI_PRIMITIVES_DIR}}`.
- {{OTHER_PLACEMENT_RULE}}

---

## Code Guidelines (REQUIRED — these are gates, not preferences)

**1. Think before coding.** State assumptions explicitly. If multiple interpretations exist, present them — don't pick silently. If a simpler approach exists, say so. If something is unclear, stop and ask. Don't hide confusion.

**2. Simplicity + No duplication (DRY).** Write the minimum code that solves the problem — nothing speculative, nothing copy-pasted. Before writing logic, grep for an existing helper. If the same logic or the same fact (a column list, a constant, a field map) would live in 2+ places, extract ONE source of truth and derive the rest. The third near-copy is the signal to merge, not to add a fourth.

**3. Surgical changes.** Touch only what the request requires. Don't "improve" adjacent code, comments, or formatting. Match the surrounding style even if you'd do it differently. Remove only the orphans YOUR change creates; mention unrelated dead code, don't delete it. **Every changed line must trace to the request.**

**4. Goal-driven execution.** Turn the task into a verifiable goal before coding ("fix the bug" → "write a test that reproduces it, then make it pass"). State a short numbered plan with a verify-step each, then loop until every check passes.

> Ask yourself before submitting: "Would a senior engineer call this overcomplicated, duplicated, or out of scope?" If yes, cut it back.

---

## ✅ Definition of Done (a task is NOT complete until all hold)

1. The change does what was asked and you verified it ({{HOW_TO_VERIFY — tests / run app / type-check}}).
2. No new duplication; logic reuses existing helpers; one source of truth preserved.
3. Every changed line traces to the request — no scope creep.
4. **Docs updated** (see below). This is part of the task, not a follow-up.

### Doc Maintenance (REQUIRED)
After ANY feature, bug fix, or significant change:
1. Update `docs/ai/{{module}}/README.md` to reflect **what IS now** (current state), not a changelog of what you did.
   - Good: "Supports 6 template types: Standard, Warehouse…"
   - Bad: "Added warehouse support on {{DATE}}"
2. Update the `> Last verified: YYYY-MM-DD` line to today's date.
3. Keep each README short ({{MAX_README_LINES}} lines) — link to deeper files for detail.
4. Cite source files as **repo-root-relative, single-backtick paths with a slash** — `` `backend/...` ``, `` `frontend/src/...` `` — so doc-verification tooling can resolve them. Not bare (`` `models.py` ``) or module-relative paths.
5. If work spans sessions, save state to `docs/ai/{{module}}/_progress.md` and delete it when done.

---

## The Docs Tree (`docs/ai/`) — how it's organized
- `docs/ai/README.md` — module index. **Start here when you don't know where something lives.**
- `docs/ai/{{module}}/README.md` — per-module: current state, key files, API, patterns, related modules.
- `docs/ai/_conventions/` — code-level cross-cutting rules (the "how").
- `docs/ai/_ux_principles/` — product/UX rules (the "why"). Trumps generic defaults on conflict.
- `docs/ai/{{module}}/_progress.md` — present only when work is mid-flight.

Navigate on demand — don't load the whole tree. But for the module you ARE touching, reading is mandatory (see the gate above).

---

## Project-Specific Rules
<!-- Add the handful of rules that bite newcomers: auth model, multi-tenancy, money/rounding,
     migrations, env quirks, "never do X". Keep it short and high-signal. -->
- {{RULE_1}}
- {{RULE_2}}
- {{RULE_3}}
