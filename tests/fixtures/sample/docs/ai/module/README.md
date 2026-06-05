# Module

> A documented module used by the fixture. Reachable from the docs index.

## Key Files

| File | Purpose |
|------|---------|
| `src/real_module.py` | Exists on disk → expected to be a `code_edge`. |
| `src/deleted_module.py` | Does NOT exist → expected to be a `code_broken`. |

## Critical Patterns

- Intent prose. The tools never read this for content — only for reachability.
