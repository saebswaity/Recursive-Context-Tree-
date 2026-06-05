#!/usr/bin/env python3
"""rct.py - agent-facing verbs over the Recursive Context Tree.

Thin CLI on top of doc_graph.py. It IMPORTS that module's parsing primitives
(configure / collect / analyze, the link + code regexes, reachable_from_entry)
and never reimplements them - doc_graph.py stays the single source of parsing
truth. Every command recomputes its answer from real files on disk + git history
at call time. Nothing is persisted; there is no index to go stale.

Commands
  rct refs <code_file>       reverse lookup: which docs cite this code file.
                             Run this BEFORE editing a file - it tells you which
                             docs you may need to reconcile afterward.
  rct verify [<doc> | --all] the unfakeable hard check: every code path a doc
                             cites must exist on disk. Exits non-zero if any
                             cited path resolves nowhere. (Working-tree truth.)
  rct orphans                md->md reachability - orphans / unreachable / broken
                             md links (delegates to doc_graph.analyze()).
  rct stale  [<doc> | --all] git warning (never a gate): flags docs whose cited
                             code was committed more recently than the doc.
  rct undocumented [<f>|--all] advisory (never a gate): tracked source files that
                             no doc cites. Coarse on purpose - RCT documents
                             modules, not every file.
  rct guard  ...             commit / CI gate. Wired up in Phase 3.

Shared flags (same meaning as doc_graph.py): --root  --docs  --entry

Zero third-party deps: stdlib only (uses `git` via subprocess for stale/
undocumented - committed-history facts, exactly as designed).
"""
import os
import sys
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doc_graph  # noqa: E402  (parsing primitives - never reimplemented here)


# Directories never worth walking/scanning for suggestions or undocumented.
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", "dist", "build", ".venv", "venv",
    ".next", "coverage", ".mypy_cache", ".pytest_cache", ".tox", "vendor",
    "__mocks__", ".idea", ".vscode",
}
# Built-in `undocumented` ignores so the FIRST run on a real repo isn't drowned
# in boilerplate. RCT documents modules, not migrations/tests/generated files.
# A repo-root .rctignore EXTENDS (never replaces) these.
DEFAULT_IGNORE_DIRS = SKIP_DIRS | {"migrations", "tests", "test", "__tests__"}
DEFAULT_IGNORE_GLOBS = [
    "__init__.py", "conftest.py", "setup.py", "manage.py", "wsgi.py", "asgi.py",
    "test_*.py", "*_test.py", "*.test.ts", "*.test.tsx", "*.test.js",
    "*.spec.ts", "*.spec.tsx", "*.spec.js", "*.min.js", "*.d.ts",
]


# --- shared helpers ---------------------------------------------------------
def _resolve(arg):
    """Resolve a user-supplied path (CWD-relative or repo-root-relative) to an
    absolute path. Returns the first candidate that exists, else the CWD one."""
    cands = [
        os.path.normpath(os.path.abspath(arg)),
        os.path.normpath(os.path.join(doc_graph.REPO_ROOT, arg)),
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[0]


def _same(a, b):
    """Case/sep-insensitive path equality (Windows-safe)."""
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def _relposix(abs_path):
    """Repo-root-relative path with forward slashes (display + git args)."""
    return os.path.relpath(abs_path, doc_graph.REPO_ROOT).replace(os.sep, "/")


def _git(*a):
    """Run git in the repo root. Returns stdout (str) or None on any failure
    (git missing, not a repo, nonzero exit) - callers degrade gracefully."""
    try:
        r = subprocess.run(["git", *a], cwd=doc_graph.REPO_ROOT,
                            capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        return None
    return r.stdout if r.returncode == 0 else None


def _commit_time(relposix):
    """Unix commit time of the last commit touching a path, or None if the path
    has no committed history (new / untracked) or git is unavailable."""
    out = _git("log", "-1", "--format=%ct", "--", relposix)
    if not out:
        return None
    out = out.strip()
    return int(out) if out.isdigit() else None


def _cite_lines(doc_abs, raw_path):
    """Cheap line numbers: which lines of the doc mention this cited path.
    A best-effort convenience for `refs` output, not a parser."""
    try:
        lines = open(doc_abs, encoding="utf-8").read().splitlines()
    except OSError:
        return []
    base = os.path.basename(raw_path)
    return [i + 1 for i, ln in enumerate(lines) if raw_path in ln or base in ln]


def _all_repo_files():
    """Repo-root-relative posix paths of every file on disk (heavy dirs skipped).
    Used to answer 'does a file by this name exist anywhere?' for verify's
    suggestions - a filesystem walk, so it works pre-commit and without git."""
    out = []
    for root, dirs, files in os.walk(doc_graph.REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            out.append(_relposix(os.path.join(root, fn)))
    return out


def _suggest(raw, all_files):
    """Classify a non-resolving citation against the files that DO exist.

    Returns (kind, suggestion, candidates):
      'style'     -> the path is written wrong but a file clearly exists; the
                     suggestion is the repo-root-relative path to use. Most
                     likely a module-relative citation that should be repo-root.
      'ambiguous' -> several files match; can't pick one - a human must.
      'missing'   -> no file by this name exists anywhere -> a genuine gap
                     (deleted / renamed / typo). THIS is the true finding.

    Match precedence: exact path-suffix first (precise), then basename."""
    raw_n = raw.lstrip("./").lower()
    base = os.path.basename(raw_n)
    suffix = [f for f in all_files
              if f.lower() == raw_n or f.lower().endswith("/" + raw_n)]
    if len(suffix) == 1:
        return "style", suffix[0], suffix
    if len(suffix) > 1:
        return "ambiguous", None, suffix
    bm = [f for f in all_files if os.path.basename(f).lower() == base]
    if len(bm) == 1:
        return "style", bm[0], bm
    if len(bm) > 1:
        return "ambiguous", None, bm
    return "missing", None, []


def _setup(args):
    """Point doc_graph's module globals at the requested repo/docs/entry."""
    doc_graph.configure(args)


# --- commands ---------------------------------------------------------------
def cmd_refs(args):
    """Which docs cite <code_file>? (from code_edges)."""
    target = _resolve(args.code_file)
    _, _, _, code_edges, _ = doc_graph.collect()
    hits = sorted({doc for doc, code in code_edges if _same(code, target)})
    rel_target = _relposix(target)
    if not hits:
        exists = os.path.isfile(target)
        note = "" if exists else "  (note: that file does not exist on disk)"
        print(f"No docs cite {rel_target}.{note}")
        print("  -> a code file no doc references may be undocumented "
              "(see `rct undocumented`), which is fine for non-module files.")
        return 0
    print(f"{len(hits)} doc(s) cite {rel_target}:")
    for doc in hits:
        lines = _cite_lines(doc, rel_target)
        where = f"  (line {', '.join(map(str, lines))})" if lines else ""
        print(f"  - {_relposix(doc)}{where}")
    print("\nIf your edit changes what these docs claim, reconcile them, "
          "then run `rct verify`.")
    return 0


def cmd_verify(args):
    """Hard check: every cited code path must exist on disk (from code_broken).
    Exit non-zero if any stale citation is found in scope.

    The resolver stays STRICT (a path that doesn't resolve as written is broken)
    but the OUTPUT is diagnostic: each failure is classified against the files
    that actually exist, so a wrong-style citation ('did you mean ...?') is
    visibly distinct from a genuinely missing/renamed file. This is the
    difference between 'N cryptic failures' and 'N-k one-click fixes + k real
    gaps' on a repo that hasn't yet normalized its citations."""
    _, _, _, _, code_broken = doc_graph.collect()
    scope = code_broken
    if args.doc and not args.all:
        doc_abs = _resolve(args.doc)
        scope = [(d, raw) for (d, raw) in code_broken if _same(d, doc_abs)]
        label = _relposix(doc_abs)
    else:
        label = "all docs"
    if not scope:
        print(f"OK: every code path cited by {label} exists on disk.")
        return 0

    all_files = _all_repo_files()
    buckets = {"style": [], "ambiguous": [], "missing": []}
    for doc, raw in scope:
        kind, sugg, cands = _suggest(raw, all_files)
        buckets[kind].append((doc, raw, sugg, cands))

    print(f"STALE CITATIONS in {label} "
          f"(a doc cites a code path that does not resolve as written):\n")
    if buckets["style"]:
        print("LIKELY PATH-STYLE MISMATCH - a file clearly exists; rewrite the "
              "citation to the repo-root-relative path shown:")
        for doc, raw, sugg, _ in buckets["style"]:
            print(f"  - {_relposix(doc)}:  `{raw}`  ->  did you mean  `{sugg}`")
        print()
    if buckets["ambiguous"]:
        print("AMBIGUOUS - several files match this name; a human must pick:")
        for doc, raw, _, cands in buckets["ambiguous"]:
            preview = ", ".join(cands[:3]) + (" ..." if len(cands) > 3 else "")
            print(f"  - {_relposix(doc)}:  `{raw}`  ->  candidates: {preview}")
        print()
    if buckets["missing"]:
        print("NO MATCHING FILE - nothing by this name exists anywhere. Likely a "
              "deleted/renamed/typo'd file (a REAL doc<->code gap):")
        for doc, raw, _, _ in buckets["missing"]:
            print(f"  - {_relposix(doc)}:  `{raw}`")
        print()

    s, a, m = len(buckets["style"]), len(buckets["ambiguous"]), len(buckets["missing"])
    print(f"{len(scope)} stale citation(s): {s} likely style mismatch (fix shown), "
          f"{a} ambiguous, {m} with no matching file (likely real gaps).")
    if s or a:
        print("Tip: normalize Key-Files citations to single-backtick, "
              "repo-root-relative paths (see docs/ai/TEMPLATE.md).")
    return 1


def cmd_orphans(args):
    """md->md reachability - delegates entirely to doc_graph.analyze()."""
    (files, edges, broken, orphans, unreachable, reachable, incoming,
     code_edges, code_broken) = doc_graph.analyze()
    problems = sorted(set(orphans) | set(unreachable))
    print(f"docs={len(files)}  md_edges={len(edges)}  reachable={len(reachable)}  "
          f"orphans={len(orphans)}  unreachable={len(unreachable)}  "
          f"broken_md={len(broken)}")
    if problems:
        print("\nORPHANS / UNREACHABLE (a navigating agent can't reach these):")
        for f in problems:
            print(f"  - {_relposix(f)}")
    if broken:
        print("\nBROKEN MD LINKS:")
        for s, raw, _ in broken:
            print(f"  - {_relposix(s)}  ->  {raw}")
    if not problems and not broken:
        print("\nOK: every doc is reachable and every md link resolves.")
    return 1 if (problems or broken) else 0


def cmd_stale(args):
    """git warning (never a gate): cited code committed more recently than the
    doc that cites it. Reflects COMMITTED history - uncommitted edits aren't
    seen here on purpose; the working-tree hard check is `rct verify`."""
    _, _, _, code_edges, _ = doc_graph.collect()
    if _git("rev-parse", "--git-dir") is None:
        print("stale: no git history available here (not a git repo, or git "
              "missing). stale is git-derived; skipping.", file=sys.stderr)
        return 0
    scope = code_edges
    if args.doc and not args.all:
        doc_abs = _resolve(args.doc)
        scope = [(d, c) for (d, c) in code_edges if _same(d, doc_abs)]

    flagged = {}     # doc_rel -> list of (code_rel, doc_time, code_time)
    skipped = 0
    for doc, code in scope:
        drel, crel = _relposix(doc), _relposix(code)
        dt, ct = _commit_time(drel), _commit_time(crel)
        if dt is None or ct is None:
            skipped += 1
            continue
        if ct > dt:
            flagged.setdefault(drel, []).append((crel, dt, ct))

    if not flagged:
        extra = f" ({skipped} citation(s) skipped - no committed history)" if skipped else ""
        print(f"OK: no doc is older than the code it cites.{extra}")
        return 0
    print("STALE (warning only) - cited code committed more recently than the doc:")
    for drel in sorted(flagged):
        print(f"  {drel}")
        for crel, dt, ct in flagged[drel]:
            print(f"      cites {crel}  (code is {ct - dt}s newer)")
    print("\nThis is a heuristic, not a gate: only you know if the code change "
          "was doc-worthy. If it was, update the doc.")
    return 0


def _load_rctignore():
    """Optional .rctignore at repo root: one fnmatch pattern per line, '#' = comment."""
    path = os.path.join(doc_graph.REPO_ROOT, ".rctignore")
    pats = []
    if os.path.isfile(path):
        for ln in open(path, encoding="utf-8").read().splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                pats.append(ln)
    return pats


def cmd_undocumented(args):
    """Advisory (never a gate): tracked source files (git ls-files ∩ CODE_EXT)
    that no doc cites, minus BUILT-IN ignores (migrations/tests/__init__/
    generated/min/spec) and any repo-root .rctignore. Coarse by design - RCT
    documents modules, not every file - so the first run isn't drowned in
    boilerplate."""
    import fnmatch
    ls = _git("ls-files")
    if ls is None:
        print("undocumented: needs git (git ls-files). Skipping.", file=sys.stderr)
        return 0
    tracked = [p for p in ls.splitlines() if p]
    code_files = [p for p in tracked
                  if os.path.splitext(p)[1].lower() in doc_graph.CODE_EXT]

    _, _, _, code_edges, _ = doc_graph.collect()
    cited = {os.path.normcase(_relposix(code)) for _, code in code_edges}
    user_ignore = _load_rctignore()

    def is_ignored(p):
        segs = p.split("/")
        if any(s in DEFAULT_IGNORE_DIRS for s in segs):
            return True
        base = os.path.basename(p)
        if any(fnmatch.fnmatch(base, g) for g in DEFAULT_IGNORE_GLOBS):
            return True
        return any(fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(base, pat)
                   or p.startswith(pat.rstrip("/") + "/") for pat in user_ignore)

    if args.code_file and not args.all:
        rel = _relposix(_resolve(args.code_file))
        key = os.path.normcase(rel)
        if key in cited:
            print(f"{rel} IS cited by at least one doc.")
        elif is_ignored(rel):
            print(f"{rel} is undocumented but ignored (boilerplate/test/generated "
                  "or .rctignore) - intentional.")
        else:
            print(f"{rel} is NOT cited by any doc (advisory).")
        return 0

    not_cited = [p for p in code_files if os.path.normcase(p) not in cited]
    ignored = [p for p in not_cited if is_ignored(p)]
    undoc = [p for p in not_cited if not is_ignored(p)]
    if not undoc:
        print(f"OK: every tracked source file ({len(code_files)} scanned, "
              f"{len(ignored)} ignored as boilerplate/test/generated) is cited "
              "by some doc (or ignored).")
        return 0
    print(f"UNDOCUMENTED (advisory) - {len(undoc)} of {len(code_files)} tracked "
          f"source files are cited by no doc "
          f"({len(ignored)} boilerplate/test/generated files already excluded):")
    for p in sorted(undoc):
        print(f"  - {p}")
    print("\nThis is advisory, never a gate. RCT documents modules that matter - "
          "many of these may not need a doc. Extend the built-in ignores with a "
          "repo-root `.rctignore` (one fnmatch pattern per line).")
    return 0


def cmd_guard(args):
    """Phase 3 entry - the commit/CI gate. Not yet implemented."""
    print("rct guard: implemented in Phase 3 (git enforcement).", file=sys.stderr)
    print("  Meanwhile: `rct verify --all` is the working-tree hard check, and "
          "`rct orphans` is the md reachability check.", file=sys.stderr)
    return 0


# --- argument parsing -------------------------------------------------------
def _common(p):
    """Attach doc_graph's repo/docs/entry flags so configure() can read them."""
    p.add_argument("--root", help="repo root (default: parent of tools/)")
    p.add_argument("--docs", help="docs root to scan (default: auto-detect docs/ai)")
    p.add_argument("--entry", nargs="*",
                   help="entry .md file(s) reachability is measured from")


def main():
    ap = argparse.ArgumentParser(
        prog="rct",
        description="Agent-facing verbs over the Recursive Context Tree "
                    "(reverse lookup, citation verification, staleness).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("refs", help="which docs cite a given code file")
    p.add_argument("code_file"); _common(p); p.set_defaults(func=cmd_refs)

    p = sub.add_parser("verify", help="every cited code path must exist on disk")
    p.add_argument("doc", nargs="?"); p.add_argument("--all", action="store_true")
    _common(p); p.set_defaults(func=cmd_verify)

    p = sub.add_parser("orphans", help="md->md reachability / orphans / broken links")
    _common(p); p.set_defaults(func=cmd_orphans)

    p = sub.add_parser("stale", help="git warning: cited code newer than the doc")
    p.add_argument("doc", nargs="?"); p.add_argument("--all", action="store_true")
    _common(p); p.set_defaults(func=cmd_stale)

    p = sub.add_parser("undocumented", help="advisory: tracked source files no doc cites")
    p.add_argument("code_file", nargs="?"); p.add_argument("--all", action="store_true")
    _common(p); p.set_defaults(func=cmd_undocumented)

    p = sub.add_parser("guard", help="commit/CI gate (Phase 3)")
    p.add_argument("--staged", action="store_true")
    p.add_argument("--ci", action="store_true")
    p.add_argument("--base")
    _common(p); p.set_defaults(func=cmd_guard)

    args = ap.parse_args()
    _setup(args)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
