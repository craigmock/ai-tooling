#!/usr/bin/env python3
"""eos-wrapup.py - the mechanical half of an end-of-session wrap-up.

  eos-wrapup.py context [--repo DIR]
        JSON: branch, uncommitted paths, commits not on any remote, last 10 commits. Read-only.
  eos-wrapup.py record --summary TEXT [--minutes N] [--ref REF] [--repo DIR]
        append a dated entry to the worklog folder from the config, then send the same unit of work
        through the configured tracking backend (none, file or webhook) via lib/aitooling.py.

The wrap-up never commits, pushes or deletes anything by itself. `context` tells the assistant what is
unsaved; the person decides what to do with it.

Exit: 0 ok, 10 no config yet (run lib/aitooling.py ensure), 2 usage error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "lib"))
import aitooling  # noqa: E402


def git(repo: str, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def cmd_context(a) -> int:
    repo = a.repo
    info = {
        "repo": git(repo, "rev-parse", "--show-toplevel"),
        "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "uncommitted": git(repo, "status", "--porcelain").splitlines(),
        "unpushed": git(repo, "log", "--branches", "--not", "--remotes", "--oneline").splitlines(),
        "recent": git(repo, "log", "-10", "--oneline").splitlines(),
    }
    print(json.dumps(info, indent=2))
    return 0


def cmd_record(a) -> int:
    cfg = aitooling.load()
    if cfg is None or aitooling.validate(cfg):
        print("no valid config yet; run: python3 %s ensure" % (ROOT / "lib" / "aitooling.py"), file=sys.stderr)
        return aitooling.EXIT_WIZARD_NEEDED
    now = dt.datetime.now()
    folder = Path(os.path.expanduser(cfg["folders"]["worklog"]))
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / ("worklog-%s.md" % now.strftime("%Y-%m"))
    new = not f.exists()
    with open(f, "a", encoding="utf-8") as fh:
        if new:
            fh.write("# Worklog %s - %s\n\n" % (now.strftime("%Y-%m"), cfg["org"]["name"]))
        fh.write("## %s - %s\n\n%s\n\n" % (now.strftime("%Y-%m-%d %H:%M"), cfg["author"]["name"], a.summary))
        if a.minutes:
            fh.write("- Time: %d min\n" % a.minutes)
        if a.ref:
            fh.write("- Reference: %s\n" % a.ref)
        fh.write("\n")
    print("worklog: %s" % f)
    return aitooling.main(["log-event", "--kind", "session", "--summary", a.summary,
                           "--minutes", str(a.minutes), "--ref", a.ref])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("context")
    c.add_argument("--repo", default=".")
    r = sub.add_parser("record")
    r.add_argument("--summary", required=True)
    r.add_argument("--minutes", type=int, default=0)
    r.add_argument("--ref", default="")
    r.add_argument("--repo", default=".")
    a = ap.parse_args()
    return {"context": cmd_context, "record": cmd_record}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
