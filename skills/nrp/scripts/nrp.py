#!/usr/bin/env python3
"""nrp.py - find the "next resume prompt" a previous session left in this repository.

  nrp.py find [--repo DIR]     list NEXT-SESSION-PROMPT.md files across every worktree of the repository,
                               newest first, with branch, age and the commit the prompt claims to start from
  nrp.py check FILE            re-check the prompt's git claims: the commit it names must exist, and the
                               working tree it describes must match (prints one line per claim)

A resume prompt is trusted only after its claims are re-checked: a prompt that says "branch X is clean at
abc1234" is a statement about a moment in the past, not about now.

Exit: 0 ok, 1 nothing found or a claim failed, 2 usage error. Pure standard library.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

NAME = "NEXT-SESSION-PROMPT.md"
SHA = re.compile(r"\b[0-9a-f]{7,40}\b")


def git(repo: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                           timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def worktrees(repo: Path) -> list:
    out = git(repo, "worktree", "list", "--porcelain")
    paths = [Path(line[9:]) for line in out.splitlines() if line.startswith("worktree ")]
    return paths or [repo]


def age(path: Path) -> str:
    secs = max(0, time.time() - path.stat().st_mtime)
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= n:
            return "%d%s" % (secs // n, unit)
    return "now"


def cmd_find(a) -> int:
    repo = Path(a.repo).resolve()
    found = []
    for wt in worktrees(repo):
        p = wt / NAME
        if p.is_file():
            found.append((p.stat().st_mtime, p, git(wt, "rev-parse", "--abbrev-ref", "HEAD")))
    if not found:
        print("no %s in %s or its worktrees" % (NAME, repo))
        return 1
    for _, p, branch in sorted(found, reverse=True):
        print("%s\tbranch=%s\tage=%s" % (p, branch or "?", age(p)))
    return 0


def cmd_check(a) -> int:
    p = Path(a.file).resolve()
    if not p.is_file():
        print("no such file: %s" % p, file=sys.stderr)
        return 2
    repo = p.parent
    text = p.read_text(encoding="utf-8", errors="replace")
    bad = 0
    for sha in sorted(set(SHA.findall(text))):
        if not re.search(r"[0-9]", sha):
            continue
        ok = bool(git(repo, "cat-file", "-t", sha))
        print("%s  commit %s" % ("ok  " if ok else "GONE", sha))
        bad += 0 if ok else 1
    dirty = git(repo, "status", "--porcelain")
    print("tree  %s" % ("dirty: %d path(s) changed since the prompt was written?" % len(dirty.splitlines())
                        if dirty else "clean"))
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find")
    f.add_argument("--repo", default=".")
    c = sub.add_parser("check")
    c.add_argument("file")
    a = ap.parse_args()
    return {"find": cmd_find, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
