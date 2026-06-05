#!/usr/bin/env python3
"""Tests for the rct CLI — exercises the verbs end-to-end via subprocess.

Zero deps (no pytest). Runs the real CLI against tests/fixtures/sample/ and
asserts exit codes + output, so the agent-facing contract (verify exits non-zero
on a dead citation; refs reverse-lookup finds the citing doc) is locked.

    python3 tests/test_rct.py        # exits 0 on pass, 1 on failure
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RCT = os.path.join(REPO, "tools", "rct.py")
FX = os.path.join(HERE, "fixtures", "sample")
DOCS = os.path.join(FX, "docs", "ai")
ENTRY = os.path.join(DOCS, "README.md")
FXARGS = ["--root", FX, "--docs", DOCS, "--entry", ENTRY]

_fail = []


def run(*argv):
    r = subprocess.run([sys.executable, RCT, *argv, *FXARGS],
                       capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def check(cond, msg):
    print(("  ok  " if cond else "FAIL  ") + msg)
    if not cond:
        _fail.append(msg)


def main():
    print("verify (the unfakeable hard check):")
    code, out = run("verify", "--all")
    check(code == 1, f"exits non-zero on a dead citation (got {code})")
    check("src/deleted_module.py" in out, "names the dead path src/deleted_module.py")

    print("refs (reverse lookup):")
    code, out = run("refs", "src/real_module.py")
    check(code == 0, f"exits zero (got {code})")
    check("module/README.md" in out.replace(os.sep, "/"),
          "finds the citing doc module/README.md")

    code, out = run("refs", "src/deleted_module.py")
    check("No docs cite" in out,
          "a path with no code_edge (only a broken citation) has no refs")

    print("orphans (md reachability):")
    code, out = run("orphans")
    check(code == 1, f"exits non-zero when an orphan exists (got {code})")
    check("orphan.md" in out, "names orphan.md")

    print()
    if _fail:
        print(f"{len(_fail)} FAILURE(S)")
        sys.exit(1)
    print("ALL PASSED")


if __name__ == "__main__":
    main()
