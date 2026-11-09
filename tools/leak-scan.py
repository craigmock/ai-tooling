#!/usr/bin/env python3
"""leak-scan.py - fail when a file in this repository names a private organization, person, host,
path, credential or tool vendor attribution. Required check before any publish.

  leak-scan.py [ROOT]            scan every file under ROOT (default: the repository root)
  leak-scan.py --commits [ROOT]  also scan commit messages and author fields of the git history

Terms are assembled from fragments so this file does not trip its own scan. Findings print as
  path:line: [rule] text
and the exit status is 1 when there is at least one, 0 when clean, 2 on a usage error.

Vendor attribution: the plain word for the assistant tool is allowed only as the documented dependency name
and only in the files listed in .attribution-allow (format: `path-glob | reason`). Co-author trailers,
tool-credit footers and vendor noreply addresses are never allowed.
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path


def j(*parts: str) -> str:
    return "".join(parts)


# (rule, compiled regex). Case-insensitive unless noted.
WORDS = [
    j("m5", "so"), j("vend", "source"), j("p", "vt"), j("prime", "vector"), j("mc", "10"), j("bas", "tion"),
    j("tele", "port"), j("craig", "mock"), j("c", "mock"), j("congru", "ex"), j("fra", "ppe"), j("ki", "mai"),
    j("forti", "gate"), j("forti", "net"), j("t", "bot"), j("defense", "claw"), j("for", "gejo"),
]
BOUNDED = [j("ha", "lo"), j("tan", "ner"), j("dus", "tin"), j("mic", "ah"), j("co", "rey"), j("gr", "eg")]

RULES = [("name:" + w, re.compile(re.escape(w), re.I)) for w in WORDS]
RULES += [("name:" + w, re.compile(r"\b" + re.escape(w) + r"\b", re.I)) for w in BOUNDED]
RULES += [
    ("path:users", re.compile(r"/" + j("Us", "ers") + r"/")),
    ("path:home", re.compile(r"/" + j("ho", "me") + r"/")),
    ("path:windows-users", re.compile(r"[A-Za-z]:[\\/]{1,2}" + j("Us", "ers"), re.I)),
    ("ip:private", re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@(?!(?:[A-Za-z0-9-]+\.)*example\.(?:com|org|net)\b)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b")),
    ("token:age", re.compile(j("a", "ge1") + r"[0-9a-z]{58}")),
    ("token:github", re.compile(j("gh", "p_") + r"[A-Za-z0-9]{30,}")),
    ("token:github-pat", re.compile(j("github", "_pat_") + r"[A-Za-z0-9_]{20,}")),
    ("token:aws", re.compile(j("AK", "IA") + r"[0-9A-Z]{16}")),
    ("token:private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("attribution:coauthor", re.compile(j("co-authored", "-by"), re.I)),
    ("attribution:generated", re.compile(j("generated ", "with"), re.I)),
    ("attribution:noreply", re.compile(j("noreply@", "anthro", "pic"), re.I)),
]
# The plugin host requires a directory named after it (".<name>-plugin"); that path is not attribution.
VENDOR = re.compile(r"(?<!\.)\b(" + j("cla", "ude") + "|" + j("anthro", "pic") + r")\b(?!-plugin)(\s+\w+)?", re.I)
DEPENDENCY_NAME = j("cla", "ude") + " code"
# The host's command line as typed in a terminal: its plugin subcommand, or the bare command in backticks.
HOST_CMD = re.compile(r"\b" + j("cla", "ude") + r" plugin\b|`" + j("cla", "ude") + "`", re.I)
# Third-party tools the README may name when recommending them (only in files listed in .attribution-allow).
THIRD_PARTY = re.compile(j("defense", "claw") + r"(?:-ai-defense)?", re.I)
# The one personal-account reference that may appear: this repository's own published name, in install lines.
PUBLIC_REPO = j("craig", "mock") + "/ai-tooling"

SKIP_DIRS = {".git", "__pycache__", "node_modules"}
ALLOW_FILE = ".attribution-allow"
MAX_BYTES = 2_000_000


def load_allow(root: Path) -> list:
    p = root / ALLOW_FILE
    out = []
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "|" in line:
                glob, reason = [x.strip() for x in line.split("|", 1)]
                if glob and reason:
                    out.append(glob)
    return out


def files(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        yield p


def scan_text(label: str, text: str, vendor_ok: bool, out: list) -> None:
    for n, line in enumerate(text.splitlines(), 1):
        rline = line.replace(PUBLIC_REPO, "")
        if vendor_ok:
            rline = THIRD_PARTY.sub("", rline)
        for rule, rx in RULES:
            for m in rx.finditer(rline):
                out.append("%s:%d: [%s] %s" % (label, n, rule, line.strip()[:120]))
                break
        # In an allowed file the host's real plugin command line is a dependency reference too.
        vline = HOST_CMD.sub("", line) if vendor_ok else line
        for m in VENDOR.finditer(vline):
            if vendor_ok and m.group(0).strip().lower() == DEPENDENCY_NAME:
                continue
            out.append("%s:%d: [attribution:vendor-name] %s" % (label, n, line.strip()[:120]))
            break


def scan_commits(root: Path, out: list) -> None:
    r = subprocess.run(["git", "-C", str(root), "log", "--all", "--format=%an <%ae>%n%cn <%ce>%n%B%x00"],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        return
    for i, chunk in enumerate(r.stdout.split("\x00")):
        if chunk.strip():
            scan_text("commit#%d" % i, chunk, False, out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root", nargs="?", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--commits", action="store_true")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    if not root.is_dir():
        print("not a directory: %s" % root, file=sys.stderr)
        return 2
    allow = load_allow(root)
    findings: list = []
    scanned = 0
    for p in files(root):
        rel = p.relative_to(root).as_posix()
        if p.stat().st_size > MAX_BYTES:
            continue
        data = p.read_bytes()
        if b"\x00" in data:
            continue
        scanned += 1
        text = data.decode("utf-8", errors="replace")
        if rel == ALLOW_FILE:
            continue  # the allow list names the dependency by design; its globs are validated above
        scan_text(rel, text, any(fnmatch.fnmatch(rel, g) for g in allow), findings)
    if a.commits:
        scan_commits(root, findings)
    for f in findings:
        print(f)
    print("leak-scan: %d file(s) scanned, %d finding(s)" % (scanned, len(findings)))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
