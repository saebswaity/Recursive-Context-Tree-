#!/usr/bin/env python3
"""
doc_graph.py — render a Recursive Context Tree as a graph + flag orphans.

Parses every link between .md files under a docs root, resolves relative
paths, computes which files are reachable from the always-loaded entry
file(s) (CLAUDE.md and any backend/ frontend/ CLAUDE.md), and flags:
  - ORPHANS      files no other doc links to
  - UNREACHABLE  files no navigating agent can reach by following links
  - BROKEN       links whose target doesn't exist

Emits two artifacts next to this script:
  - doc_graph.md    Mermaid diagram (renders on GitHub, no tooling needed)
  - doc_graph.html  Interactive force-graph (drag / zoom / click-to-open)

Zero runtime deps for the report — pure stdlib. The HTML pulls d3 from a CDN.

Usage (defaults assume this script lives in <repo>/tools/):
    python3 tools/doc_graph.py                       # auto-detect docs root
    python3 tools/doc_graph.py --docs docs/ai        # explicit docs root
    python3 tools/doc_graph.py --no-html             # skip HTML (faster, CI)
    python3 tools/doc_graph.py --check               # exit 1 on any problem (CI gate)
    python3 tools/doc_graph.py --root /other/repo --docs /other/repo/docs \\
            --entry /other/repo/CLAUDE.md            # run against another repo

Why this exists: the Recursive Context Tree works ONLY if every doc is linked
into the tree. An orphan is invisible to a navigating agent — it cost real
work to write and returns nothing. This makes reachability a glanceable fact
instead of something you must remember to verify, and gives the maintenance
rule ("link new docs from an index") a mechanical enforcer.

Recognized link dialects (a missing dialect = false orphans):
  [label](./file.md)     standard markdown link
  [label](./dir/)        folder-link  -> resolves to dir/README.md
  `path/to/file.md`      inline-backtick path (the Key-Files citation style)
  @path/to/file.md       @import (honored in CLAUDE.md files only)
Links inside fenced code blocks and <!-- comments --> are ignored (examples).

The md->code bridge (additive, never gates this script's --check):
  `path/to/file.py`      inline-backtick CODE path -> a doc->code citation
collect() also returns these as `code_edges` (the cited file exists on disk) and
`code_broken` (a doc cites a code path that resolves nowhere — a stale citation).
This is the raw material the `rct` CLI turns into agent-facing verbs (refs/verify/
stale). It NEVER affects md->md reachability, orphans, or the --check exit code —
those stay byte-identical to before the bridge existed.
"""
import os
import re
import sys
import glob
import json
import argparse
from collections import defaultdict, deque

# --- config (defaults; all overridable via CLI flags) -----------------------
# Default repo root = the parent of the dir holding this script (i.e. assumes
# <repo>/tools/doc_graph.py). Override with --root for any other layout.
DEFAULT_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# Module-level handles, set by main() from args so other repos can point
# the tool at a different docs root / entry file without editing the source.
REPO_ROOT = DEFAULT_REPO_ROOT
DOCS_ROOT = os.path.join(REPO_ROOT, "docs", "ai")
# Always-loaded entry points an agent starts navigation from. Claude Code
# auto-loads the root CLAUDE.md AND any backend/ frontend/ subdir CLAUDE.md,
# so reachability must seed from ALL of them — a doc linked only from
# backend/CLAUDE.md is genuinely findable (Searcher-2 finding #2).
ENTRY_FILES = []  # filled by configure()
OUT_DIR = os.path.dirname(__file__)

# Files that are intentionally not linked (found by convention, not navigation).
# Matched by basename — kept deliberately tiny. NOTE: `_progress.md` is NOT
# whitelisted: the doc-maintenance rule requires deleting it when work
# completes, so a lingering orphaned one is a real signal, not noise
# (Searcher-2 finding #1).
ALLOWED_ORPHANS = {
    "TEMPLATE.md",        # stencil for new module docs
    "doc_graph.md",       # this tool's own generated output
}

# Standard markdown link to a .md file:  [label](../foo/bar.md#anchor "title")
LINK_RE = re.compile(r'\]\(\s*<?([^)\s>]+?\.md)(?:#[^)\s>]*)?>?(?:\s+"[^"]*")?\s*\)')
# Folder-style link (resolves to that folder's README.md):  [Items](./items/)
FOLDER_LINK_RE = re.compile(r'\]\(\s*<?(\.{1,2}/[^)\s>]*?/)(?:#[^)\s>]*)?>?\s*\)')
# Claude Code @import syntax (only honored in CLAUDE.md files): @docs/ai/README.md
IMPORT_RE = re.compile(r'(?:^|\s)@([\w./-]+\.md)\b')
# Inline-backtick path citation:  `docs/ai/pot/foo.md`  — the DOMINANT citation
# style in module Key-Files tables. A navigating agent reads these and opens
# them, so they ARE navigation edges (Searcher-1 + Searcher-3 CRITICAL finding).
# Only single-backtick inline spans; fenced ``` blocks are stripped first.
BACKTICK_PATH_RE = re.compile(r'`([^`\n]*?\.md)(?:#[^`\n]*)?`')
# Fenced code blocks (``` or ~~~). Stripped before parsing so EXAMPLE links
# inside fences don't become phantom edges (Searcher-1 finding #2).
FENCE_RE = re.compile(r'(^|\n)(```|~~~).*?(\n\2|\Z)', re.DOTALL)
# HTML comments — also stripped (illustrative links live here too).
COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
# Any inline single-backtick span. Used to strip code-shown link syntax like
# `[x](./dir/)` so prose EXAMPLES of link syntax aren't counted as real edges.
INLINE_CODE_RE = re.compile(r'`[^`\n]*`')

# --- md->code bridge ---------------------------------------------------------
# Source-file extensions RCT users actually cite in Key-Files tables. NOT
# exhaustive on purpose: the goal is "looks like a code path", and the `/`
# heuristic below catches anything with a directory component regardless of
# extension. Extend freely — a missing extension just means a bare-filename
# citation (no slash) won't be harvested, never a wrong edge.
CODE_EXT = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue",
    ".svelte", ".go", ".rs", ".java", ".kt", ".kts", ".scala", ".rb", ".php",
    ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".swift", ".m", ".mm", ".sql",
    ".sh", ".bash", ".ps1", ".lua", ".dart", ".ex", ".exs", ".clj", ".r",
    ".html", ".css", ".scss", ".json", ".yaml", ".yml", ".toml", ".proto",
}
# Any inline single-backtick span — the candidate text for a code-path citation.
# The same span style as BACKTICK_PATH_RE, but here we KEEP non-.md hits and
# decide path-ness with _is_code_citation() rather than a hard-coded suffix.
BACKTICK_SPAN_RE = re.compile(r'`([^`\n]+?)`')
# A trailing :line / :line:col location suffix on a citation (e.g. `foo.py:42`).
LOC_SUFFIX_RE = re.compile(r':\d+(?::\d+)?$')


def _is_code_citation(raw: str) -> bool:
    """Conservative: is this backtick span a concrete repo path to a CODE file?

    Requires a PATH COMPONENT ("/") — which the locked Key-Files convention
    guarantees (citations are backtick, repo-root-relative). That single rule
    drops the false positives a looser heuristic invites: bare-filename prose
    ("rename `services.py` to `domain.py`"), globs (`.cursor/rules/*.mdc`), and
    call syntax (`useState()`). It is the conservatism that lets the derived
    `code_broken` signal hard-gate without firing on prose (invariant 5).

    Whether a NON-resolving candidate is reported broken is decided at the call
    site by its extension (must be in CODE_EXT); existence on disk proves an
    edge regardless of extension.
    """
    if not raw or raw.endswith(".md"):
        return False  # .md is the md->md harvester's job
    if raw.startswith(("http://", "https://", "//")):
        return False
    if any(c in raw for c in "*?()[]<> {}"):
        return False  # glob / call / prose / {placeholder} noise — not a concrete path
    return "/" in raw


def strip_fences(text: str) -> str:
    """Remove fenced code blocks + HTML comments. Inline backtick spans are
    KEPT here so backtick PATH citations can still be harvested first."""
    text = FENCE_RE.sub("\n", text)
    text = COMMENT_RE.sub("", text)
    return text


def rel(path: str) -> str:
    """Repo-relative path for display."""
    return os.path.relpath(path, REPO_ROOT)


def collect():
    """Return (files, edges, broken, code_edges, code_broken).

    files: list of abs paths to every .md under DOCS_ROOT (+ the entry files)
    edges: list of UNIQUE (src_abs, dst_abs) for every resolvable .md reference
    broken: list of (src_abs, raw_link, resolved_missing_abs)
    code_edges: UNIQUE (doc_abs, code_abs) — a doc cites a CODE file that exists
    code_broken: list of (doc_abs, raw_path) — a doc cites a code path that
                 resolves NOWHERE (a deleted/renamed/typo'd source file)

    A "reference" is a standard [](.md) link, a folder-link ([](./dir/) →
    dir/README.md), an inline-backtick `path.md` citation, or — in CLAUDE.md
    files only — an @import. Fenced code blocks + HTML comments are stripped
    first so example links inside them aren't counted.

    The md->code bridge (code_edges / code_broken) is purely additive: it does
    NOT influence files/edges/broken, reachability, or orphans. The first three
    return values are byte-identical to before the bridge existed.
    """
    files = sorted(glob.glob(os.path.join(DOCS_ROOT, "**", "*.md"), recursive=True))
    for entry in ENTRY_FILES:
        if os.path.exists(entry) and entry not in files:
            files = [entry] + files

    edge_set, broken = set(), []
    code_edge_set, code_broken = set(), []
    fileset = set(files)

    def add(f, raw, resolved):
        """Record an edge or a broken link for a resolved target path."""
        if os.path.exists(resolved):
            if resolved in fileset:
                edge_set.add((f, resolved))
            # links to real files outside the doc set (e.g. source code) are
            # neither edges-in-graph nor broken — silently ignore.
        else:
            broken.append((f, raw, resolved))

    for f in files:
        base = os.path.dirname(f)
        try:
            raw_text = open(f, encoding="utf-8").read()
        except Exception:
            continue
        # Strip fenced blocks + comments. Keep inline backticks for now so
        # backtick PATH citations can be harvested before we strip them.
        text = strip_fences(raw_text)
        is_claude_md = os.path.basename(f) == "CLAUDE.md"

        # 1. inline-backtick `path.md` citations (Key-Files style) — harvested
        #    FIRST, from text that still has its backticks. Resolve relative to
        #    base, then repo-root (docs often cite full repo-relative paths).
        for raw in BACKTICK_PATH_RE.findall(text):
            if raw.startswith(("http://", "https://", "//")):
                continue
            cand_base = os.path.normpath(os.path.join(base, raw))
            cand_repo = os.path.normpath(os.path.join(REPO_ROOT, raw))
            if os.path.exists(cand_base) and cand_base in fileset:
                edge_set.add((f, cand_base))
            elif os.path.exists(cand_repo) and cand_repo in fileset:
                edge_set.add((f, cand_repo))
            # Bare path that doesn't resolve → NOT reported broken: backtick
            # spans are also used for illustrative paths, so only count hits.

        # 1b. inline-backtick `path.ext` citations of SOURCE CODE (non-.md) —
        #     the md->code bridge. Harvested here (alongside the .md backtick
        #     pass, before INLINE_CODE_RE strips the spans) using the SAME
        #     two-step resolution: doc dir first, then repo-root-relative.
        for raw in BACKTICK_SPAN_RE.findall(text):
            cite = LOC_SUFFIX_RE.sub("", raw.split("#", 1)[0]).strip()
            if not _is_code_citation(cite):
                continue
            cand_base = os.path.normpath(os.path.join(base, cite))
            cand_repo = os.path.normpath(os.path.join(REPO_ROOT, cite))
            if os.path.isfile(cand_base):
                code_edge_set.add((f, cand_base))
            elif os.path.isfile(cand_repo):
                code_edge_set.add((f, cand_repo))
            elif os.path.splitext(cite)[1].lower() in CODE_EXT:
                # A recognized code path that resolves NOWHERE → a stale
                # citation: the unfakeable signal of a doc pointing at a
                # deleted/renamed/typo'd source file. Extensionless slash-paths
                # that don't resolve are left unreported (could be a dir ref).
                code_broken.append((f, cite))

        # Now strip ALL inline-code spans, so link syntax shown as code in
        # prose — e.g. `[Items](./items/)` documenting the syntax — is not
        # mistaken for a real link/folder edge (the example-link false positive).
        text = INLINE_CODE_RE.sub(" ", text)

        # 2. standard [label](path.md) links
        for raw in LINK_RE.findall(text):
            if raw.startswith(("http://", "https://", "//", "mailto:")):
                continue
            add(f, raw, os.path.normpath(os.path.join(base, raw)))

        # 3. folder-style [label](./items/) → that folder's README.md
        for raw in FOLDER_LINK_RE.findall(text):
            if raw.startswith(("http://", "https://", "//")):
                continue
            add(f, raw, os.path.normpath(os.path.join(base, raw, "README.md")))

        # 4. @import paths — ONLY in CLAUDE.md files, resolved from REPO_ROOT
        if is_claude_md:
            for raw in IMPORT_RE.findall(text):
                add(f, raw, os.path.normpath(os.path.join(REPO_ROOT, raw)))

    return files, sorted(edge_set), broken, sorted(code_edge_set), code_broken


def reachable_from_entry(files, edges):
    """Multi-root BFS over the edge set from EVERY always-loaded entry file
    (root CLAUDE.md + backend/ + frontend/ CLAUDE.md). Returns reachable set."""
    adj = defaultdict(list)
    for s, t in edges:
        adj[s].append(t)
    seen = set()
    q = deque()
    for entry in ENTRY_FILES:
        if os.path.exists(entry) and entry not in seen:
            seen.add(entry)
            q.append(entry)
    while q:
        n = q.popleft()
        for m in adj[n]:
            if m not in seen:
                seen.add(m)
                q.append(m)
    return seen


def analyze():
    files, edges, broken, code_edges, code_broken = collect()
    incoming = defaultdict(int)
    for _, t in edges:
        incoming[t] += 1
    reachable = reachable_from_entry(files, edges)

    entry_set = set(ENTRY_FILES)
    orphans = []          # no incoming link AND not an entry file
    for f in files:
        if f in entry_set:
            continue
        if incoming[f] == 0 and os.path.basename(f) not in ALLOWED_ORPHANS:
            orphans.append(f)

    unreachable = [f for f in files if f not in reachable and f not in entry_set
                   and os.path.basename(f) not in ALLOWED_ORPHANS]
    return (files, edges, broken, orphans, unreachable, reachable, incoming,
            code_edges, code_broken)


# --- mermaid output ---------------------------------------------------------
def node_id(path, files):
    return "n%d" % files.index(path)


def short_label(path):
    r = rel(path)
    # collapse docs/ai/ prefix for readability
    return r.replace("docs/ai/", "").replace("CLAUDE.md", "CLAUDE.md (root)")


def write_mermaid(files, edges, orphans, unreachable, reachable):
    orphan_set = set(orphans) | set(unreachable)
    lines = [
        "# docs/ai knowledge graph",
        "",
        "> Auto-generated by `tools/doc_graph.py` — do not edit by hand.",
        "> Green = reachable from CLAUDE.md. Red = orphan / unreachable (a navigating agent can't find it).",
        "",
        "```mermaid",
        "graph LR",
    ]
    for f in files:
        nid = node_id(f, files)
        label = short_label(f).replace('"', "'")
        lines.append(f'    {nid}["{label}"]')
    lines.append("")
    for s, t in edges:
        lines.append(f"    {node_id(s, files)} --> {node_id(t, files)}")
    lines.append("")
    # styling
    lines.append("    classDef root fill:#2a9d8f,stroke:#1b6d63,color:#fff;")
    lines.append("    classDef ok fill:#e8f4e8,stroke:#49a,color:#123;")
    lines.append("    classDef orphan fill:#fde2e2,stroke:#c0392b,color:#7a1f17,stroke-width:2px;")
    entry_set = set(ENTRY_FILES)
    for f in files:
        nid = node_id(f, files)
        if f in entry_set:
            cls = "root"
        elif f in orphan_set:
            cls = "orphan"
        else:
            cls = "ok"
        lines.append(f"    class {nid} {cls};")
    lines.append("```")
    lines.append("")
    lines.append("## Orphans & unreachable")
    if orphan_set:
        for f in sorted(orphan_set):
            lines.append(f"- ⚠️ `{rel(f)}`")
    else:
        lines.append("- ✅ none — every doc is reachable from the root.")
    out = os.path.join(OUT_DIR, "doc_graph.md")
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return out


# --- html output ------------------------------------------------------------
def write_html(files, edges, orphans, unreachable, reachable, incoming,
               code_edges=(), code_broken=()):
    orphan_set = set(orphans) | set(unreachable)

    def folder_of(path):
        r = rel(path)
        if r == "CLAUDE.md":
            return "root"
        parts = r.split("/")
        # docs/ai/<folder>/...
        return parts[2] if len(parts) > 3 else "(top)"

    nodes = []
    for f in files:
        nodes.append({
            "id": rel(f),
            "label": short_label(f),
            "type": "doc",
            "module": folder_of(f),
            "orphan": f in orphan_set,
            "root": f in set(ENTRY_FILES),
            "incoming": incoming.get(f, 0),
        })
    links = [{"source": rel(s), "target": rel(t), "kind": "doc"} for s, t in edges]

    # --- md->code bridge: add code files as nodes + the citing links ---------
    seen_code = set()

    def add_code_node(node_id, label, broken):
        if node_id in seen_code:
            return
        seen_code.add(node_id)
        area = ("backend" if label.startswith("backend/") or "/backend/" in node_id
                else "frontend" if label.startswith("frontend/") or "/frontend/" in node_id
                else "other")
        nodes.append({
            "id": node_id, "label": os.path.basename(node_id.split(":", 1)[-1]),
            "type": "code", "module": area, "broken": broken,
            "orphan": False, "root": False, "incoming": 0,
        })

    for doc, code in code_edges:
        cid = rel(code)
        add_code_node(cid, cid, False)
        links.append({"source": rel(doc), "target": cid, "kind": "code"})
    for doc, raw in code_broken:
        mid = "missing:" + raw            # raw doesn't resolve — keep distinct
        add_code_node(mid, raw, True)
        links.append({"source": rel(doc), "target": mid, "kind": "broken"})

    modules = sorted({folder_of(f) for f in files})
    data = {"nodes": nodes, "links": links, "modules": modules}

    html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>docs/ai knowledge graph</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<style>
  html,body{margin:0;height:100%;background:#0f172a;color:#e2e8f0;overflow:hidden;
    font:13px/1.4 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
  #hud{position:fixed;top:0;left:0;right:0;padding:9px 14px;z-index:10;
    background:linear-gradient(#0f172af2,#0f172acc 70%,#0f172a00);
    display:flex;gap:14px;align-items:center;flex-wrap:wrap}
  #hud h1{font-size:14px;margin:0 6px 0 0;font-weight:700;white-space:nowrap}
  .stat{font-size:12px;color:#94a3b8}
  .stat b{color:#e2e8f0}
  select,input,button{background:#1e293b;color:#e2e8f0;border:1px solid #334155;
    border-radius:6px;padding:4px 8px;font:inherit;font-size:12px;outline:none}
  select:focus,input:focus{border-color:#38bdf8}
  button{cursor:pointer}
  button:hover{background:#334155}
  input{min-width:230px}
  label.ctl{font-size:11px;color:#94a3b8;display:inline-flex;gap:5px;align-items:center}
  .pill{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:#cbd5e1}
  .dot{width:9px;height:9px;border-radius:9px;display:inline-block}
  .sq{width:9px;height:9px;display:inline-block}
  svg{width:100vw;height:100vh;display:block;cursor:grab}
  .link{stroke:#334155;stroke-width:1.1px}
  .link.code{stroke:#3f6212;stroke-dasharray:none}
  .link.broken{stroke:#7f1d1d;stroke-dasharray:3 3}
  .link.dim{stroke-opacity:.12}
  .node text{fill:#cbd5e1;font-size:10px;pointer-events:none}
  .node:hover text{fill:#fff;font-weight:600}
  .node.dim{opacity:.18}
  .node .shape{stroke:#0f172a;stroke-width:1.5px;cursor:pointer}
  #legend{position:fixed;bottom:10px;left:14px;display:flex;gap:14px;flex-wrap:wrap;
    align-items:center;background:#0f172abb;padding:6px 10px;border-radius:8px}
  #foot{position:fixed;bottom:10px;right:14px;color:#64748b;font-size:11px;text-align:right}
  #foot b{color:#cbd5e1}
</style></head>
<body>
<div id="hud">
  <h1>docs/ai graph</h1>
  <label class="ctl">view
    <select id="mode">
      <option value="all">All md + code</option>
      <option value="mdonly">All md only</option>
      <option value="focus">Focus one md + its code</option>
      <option value="module">Per-module subgraph</option>
    </select>
  </label>
  <label class="ctl" id="modWrap" style="display:none">module
    <select id="module"></select>
  </label>
  <input id="search" list="ids" placeholder="search a doc/file, Enter to focus…"/>
  <datalist id="ids"></datalist>
  <button id="reset">Reset</button>
  <span class="stat"><b id="nf">0</b> nodes</span>
  <span class="stat"><b id="ne">0</b> links</span>
  <span class="stat" style="color:#f87171"><b id="no">0</b> broken</span>
</div>
<svg></svg>
<div id="legend">
  <span class="pill"><span class="dot" style="background:#2dd4bf"></span>root doc</span>
  <span class="pill"><span class="dot" style="background:#7dd3fc"></span>doc</span>
  <span class="pill"><span class="dot" style="background:#f87171"></span>orphan doc</span>
  <span class="pill"><span class="sq" style="background:#84cc16"></span>code file</span>
  <span class="pill"><span class="sq" style="background:#ef4444;outline:1px dashed #ef4444"></span>missing code</span>
</div>
<div id="foot">drag node · scroll zoom · <b>click</b> node = focus + copy path</div>
<script>
const DATA = __DATA__;
const allNodes = DATA.nodes, allLinks = DATA.links;
const byId = new Map(allNodes.map(n => [n.id, n]));

// adjacency over RAW string ids (d3 later rewrites link.source/target to objects,
// so we keep our own copy and hand d3 fresh link objects on every render).
const nbr = new Map(allNodes.map(n => [n.id, []]));
allLinks.forEach(l => { nbr.get(l.source).push({id:l.target, kind:l.kind, dir:"out"});
                        nbr.get(l.target).push({id:l.source, kind:l.kind, dir:"in"}); });

// datalist + module dropdown
const ids = document.getElementById("ids");
allNodes.filter(n=>n.type==="doc").forEach(n=>{ const o=document.createElement("option"); o.value=n.id; ids.appendChild(o); });
const modSel = document.getElementById("module");
DATA.modules.forEach(m=>{ const o=document.createElement("option"); o.value=m; o.textContent=m; modSel.appendChild(o); });

const svg = d3.select("svg");
const W = () => window.innerWidth, H = () => window.innerHeight;
const g = svg.append("g");
svg.call(d3.zoom().scaleExtent([0.15,4]).on("zoom", e => g.attr("transform", e.transform)));
svg.append("defs").append("marker").attr("id","arrow").attr("viewBox","0 -5 10 10")
  .attr("refX",16).attr("refY",0).attr("markerWidth",6).attr("markerHeight",6)
  .attr("orient","auto").append("path").attr("d","M0,-5L10,0L0,5").attr("fill","#475569");

function fill(n){ if(n.type==="code") return n.broken ? "#ef4444" : "#84cc16";
                  if(n.root) return "#2dd4bf"; if(n.orphan) return "#f87171"; return "#7dd3fc"; }
function radius(n){ return n.root ? 11 : Math.min(4 + n.incoming*2.2, 15); }

let sim, linkSel, nodeSel;
const state = { mode:"all", module:DATA.modules[0]||"", focus:null };

// ---- which nodes/links are visible for the current state ----
function visible(){
  let keep;
  if(state.mode==="mdonly"){
    keep = new Set(allNodes.filter(n=>n.type==="doc").map(n=>n.id));
  } else if(state.mode==="focus" && state.focus && byId.has(state.focus)){
    keep = new Set([state.focus]);
    nbr.get(state.focus).forEach(e=>{
      if(e.kind==="doc") keep.add(e.id);                 // md neighbours (either dir)
      else if(e.dir==="out") keep.add(e.id);             // code this doc cites
    });
  } else if(state.mode==="module"){
    const docs = allNodes.filter(n=>n.type==="doc" && n.module===state.module).map(n=>n.id);
    keep = new Set(docs);
    docs.forEach(d => nbr.get(d).forEach(e=>{
      if(e.dir==="out" && e.kind!=="doc") keep.add(e.id); // code cited by module docs
      if(e.kind==="doc") keep.add(e.id);                  // 1-hop md neighbours (context)
    }));
  } else {
    keep = new Set(allNodes.map(n=>n.id));               // all
  }
  const nodes = allNodes.filter(n=>keep.has(n.id));
  const links = allLinks.filter(l=>keep.has(l.source) && keep.has(l.target))
                        .map(l=>({source:l.source, target:l.target, kind:l.kind}));
  return {nodes, links};
}

function render(){
  const {nodes, links} = visible();
  document.getElementById("nf").textContent = nodes.length;
  document.getElementById("ne").textContent = links.length;
  document.getElementById("no").textContent = nodes.filter(n=>n.type==="code"&&n.broken).length;

  if(sim) sim.stop();
  g.selectAll("g.layer").remove();
  const lg = g.append("g").attr("class","layer");
  const ng = g.append("g").attr("class","layer");

  linkSel = lg.selectAll("line").data(links).join("line")
    .attr("class",d=>"link "+d.kind).attr("marker-end","url(#arrow)");

  nodeSel = ng.selectAll("g").data(nodes, d=>d.id).join("g").attr("class","node")
    .call(d3.drag()
      .on("start",(e,d)=>{if(!e.active)sim.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y;})
      .on("drag",(e,d)=>{d.fx=e.x;d.fy=e.y;})
      .on("end",(e,d)=>{if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null;}));

  nodeSel.each(function(d){
    const s = d3.select(this);
    if(d.type==="code"){
      const z = d.broken ? 9 : 8;
      s.append("rect").attr("class","shape").attr("width",z).attr("height",z)
        .attr("x",-z/2).attr("y",-z/2).attr("rx",1.5).attr("fill",fill(d))
        .attr("stroke-dasharray", d.broken ? "2 2" : null);
    } else {
      s.append("circle").attr("class","shape").attr("r",radius(d)).attr("fill",fill(d));
    }
  });
  nodeSel.append("title").text(d=> d.type==="code"
      ? (d.broken ? "MISSING — "+d.id.replace(/^missing:/,"") : d.id)
      : d.id+"  ("+d.incoming+" incoming)");
  nodeSel.append("text").attr("x",d=>(d.type==="code"?7:radius(d)+4)).attr("y",3).text(d=>d.label);
  nodeSel.on("click",(e,d)=>{
    if(d.type==="doc"){ state.focus=d.id; state.mode="focus"; syncControls(); render(); }
    navigator.clipboard?.writeText(d.id.replace(/^missing:/,""));
  });

  sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d=>d.id).distance(d=>d.kind==="doc"?80:46).strength(.55))
    .force("charge", d3.forceManyBody().strength(-240))
    .force("center", d3.forceCenter(W()/2, H()/2))
    .force("collide", d3.forceCollide().radius(d=>(d.type==="code"?10:radius(d)+12)))
    .on("tick",()=>{
      linkSel.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y)
             .attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);
      nodeSel.attr("transform",d=>`translate(${d.x},${d.y})`);
    });
  sim.alpha(.9).restart();
}

function syncControls(){
  document.getElementById("mode").value = state.mode;
  document.getElementById("modWrap").style.display = state.mode==="module" ? "" : "none";
  if(state.mode==="module") modSel.value = state.module;
}

document.getElementById("mode").addEventListener("change", e=>{ state.mode=e.target.value; syncControls(); render(); });
modSel.addEventListener("change", e=>{ state.module=e.target.value; render(); });
document.getElementById("search").addEventListener("change", e=>{
  const v=e.target.value.trim(); if(byId.has(v)){ state.focus=v; state.mode="focus"; syncControls(); render(); }
});
document.getElementById("reset").addEventListener("click", ()=>{
  state.mode="all"; state.focus=null; document.getElementById("search").value=""; syncControls(); render();
});

syncControls(); render();
</script></body></html>"""
    html = html.replace("__DATA__", json.dumps(data))
    out = os.path.join(OUT_DIR, "doc_graph.html")
    open(out, "w", encoding="utf-8").write(html)
    return out


def _autodetect_docs(repo_root):
    """Pick a sensible docs root when --docs isn't given. Prefers docs/ai,
    then docs/, else the repo root itself (small projects with docs at top)."""
    for cand in (os.path.join(repo_root, "docs", "ai"),
                 os.path.join(repo_root, "docs")):
        if os.path.isdir(cand) and glob.glob(os.path.join(cand, "**", "*.md"), recursive=True):
            return cand
    return repo_root


def configure(args):
    """Set module-level roots from CLI args so the tool is repo-agnostic.
    Defaults assume <repo>/tools/doc_graph.py and auto-detect the docs root;
    --root/--docs/--entry override for any other layout."""
    global REPO_ROOT, DOCS_ROOT, ENTRY_FILES
    REPO_ROOT = os.path.abspath(args.root) if args.root else DEFAULT_REPO_ROOT
    DOCS_ROOT = (os.path.abspath(args.docs) if args.docs
                 else _autodetect_docs(REPO_ROOT))
    if args.entry:
        ENTRY_FILES = [os.path.abspath(e) for e in args.entry]
    else:
        # Default entry points = every always-loaded CLAUDE.md that exists.
        ENTRY_FILES = [p for p in (
            os.path.join(REPO_ROOT, "CLAUDE.md"),
            os.path.join(REPO_ROOT, "backend", "CLAUDE.md"),
            os.path.join(REPO_ROOT, "frontend", "CLAUDE.md"),
        ) if os.path.exists(p)]
        # Fallback: if no CLAUDE.md, seed reachability from the docs index
        # (README.md at the docs root) so the tool still works tool-agnostically.
        if not ENTRY_FILES:
            idx = os.path.join(DOCS_ROOT, "README.md")
            if os.path.exists(idx):
                ENTRY_FILES = [idx]


def main():
    ap = argparse.ArgumentParser(
        description="Render the docs knowledge tree as a graph + flag orphans/broken links.")
    ap.add_argument("--root", help="repo root (default: 3 levels up from this script)")
    ap.add_argument("--docs", help="docs root to scan (default: <root>/docs/ai)")
    ap.add_argument("--entry", nargs="*",
                    help="entry .md file(s) reachability is measured from "
                         "(default: root + backend + frontend CLAUDE.md)")
    ap.add_argument("--no-html", action="store_true",
                    help="skip the interactive HTML (e.g. in CI)")
    ap.add_argument("--check", action="store_true",
                    help="CI mode: exit 1 if any orphan/unreachable/broken exists. "
                         "NOTE: gates on ABSOLUTE count, not a delta baseline — "
                         "only wire to CI AFTER the tree is clean.")
    args = ap.parse_args()
    configure(args)

    # Guard: an empty docs root almost always means a misconfigured --docs/--root.
    # Reporting "0 orphans" on an empty tree is a silent false-negative — the
    # worst failure for a checker (Searcher-3 finding #5). Fail loudly instead.
    probe = glob.glob(os.path.join(DOCS_ROOT, "**", "*.md"), recursive=True)
    if not probe:
        print(f"ERROR: no .md files found under docs root: {DOCS_ROOT}", file=sys.stderr)
        print("       pass --docs / --root to point at the right tree.", file=sys.stderr)
        sys.exit(2)
    if not ENTRY_FILES:
        print("ERROR: no entry file found (looked for CLAUDE.md). "
              "Pass --entry <file.md>.", file=sys.stderr)
        sys.exit(2)

    (files, edges, broken, orphans, unreachable, reachable, incoming,
     code_edges, code_broken) = analyze()
    md = write_mermaid(files, edges, orphans, unreachable, reachable)
    print(f"files={len(files)}  edges={len(edges)}  "
          f"reachable={len(reachable)}  orphans={len(orphans)}  "
          f"unreachable={len(unreachable)}  broken={len(broken)}")
    print(f"code_edges={len(code_edges)}  code_broken={len(code_broken)}  "
          f"(md->code bridge - informational; the hard gate is `rct verify`)")
    print(f"wrote: {rel(md)}")
    if not args.no_html:
        html = write_html(files, edges, orphans, unreachable, reachable, incoming,
                           code_edges, code_broken)
        print(f"wrote: {rel(html)}")

    problems = set(orphans) | set(unreachable)
    if problems:
        print("\nORPHANS / UNREACHABLE (a navigating agent can't reach these):")
        for f in sorted(problems):
            print(f"  - {rel(f)}")
    if broken:
        print("\nBROKEN LINKS:")
        for s, raw, t in broken:
            print(f"  - {rel(s)}  ->  {raw}")
    if code_broken:
        # Informational here (a doc cites a code path that resolves nowhere).
        # NOT part of --check: the md->md gate stays byte-identical, and the
        # unfakeable code-citation gate lives in `rct verify` (Phase 2).
        print("\nSTALE CODE CITATIONS (doc cites a code path that doesn't exist):")
        for s, raw in code_broken:
            print(f"  - {rel(s)}  ->  {raw}")

    if args.check and (problems or broken):
        sys.exit(1)


if __name__ == "__main__":
    main()
