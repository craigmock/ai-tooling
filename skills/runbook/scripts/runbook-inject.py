#!/usr/bin/env python3
"""Turn a freshly scaffolded /docs file into a runbook skeleton.

  runbook-inject.py <stable.html> [<snapshot.html> ...] [--body runbook-body.html]

For each file:
  - sets data-doc-kind="runbook" on <html>, so validate-runbook.py and any
    diagram validator both classify it without relying on the file name;
  - replaces the scaffold's "Detail" and "Build journal" sections (from <h2 id="body">
    up to the recreation prompt, references or revision history, whichever comes first)
    with the runbook body template;
  - rebuilds <nav class="toc"> from the <h2 id> headings, in order.

The stable file and its snapshot are written identically. It refuses a file that has no
<h2 id="body"> (already injected, or not a scaffold) rather than guessing where to write.
"""
from __future__ import annotations

import argparse
import html as htmlmod
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def default_body() -> Path:
    for c in (HERE.parent / "templates" / "runbook-body.html", HERE / "runbook-body.html"):
        if c.is_file():
            return c
    raise SystemExit("runbook-body.html not found beside this script or in ../templates")


def inject(text: str, body: str) -> str:
    start = re.search(r'<h2 id="body"[^>]*>', text)
    if not start:
        raise ValueError('no <h2 id="body"> (already a runbook, or not a fresh scaffold)')
    end = None
    for anchor in ("recreate", "references", "revision-history"):
        m = re.search(rf'<h2 id="{anchor}"', text[start.end():])
        if m:
            end = start.end() + m.start()
            break
    if end is None:
        raise ValueError("no recreation prompt, references or revision-history heading after the body")
    body = re.sub(r"^\s*<!--.*?-->", "", body, count=1, flags=re.S)   # the template's own header note
    text = text[:start.start()] + body.strip() + "\n\n" + text[end:]
    # The real root carries lang=; the templates also mention "<html data-...>" in comments.
    root = re.search(r"<html\b(?=[^>]*\blang=)[^>]*>", text)
    if not root:
        raise ValueError('no <html lang=...> root element')
    tag = root.group(0)
    new = (re.sub(r'data-doc-kind="[^"]*"', 'data-doc-kind="runbook"', tag) if "data-doc-kind=" in tag
           else tag.replace("<html", '<html data-doc-kind="runbook"', 1))
    text = text[:root.start()] + new + text[root.end():]
    # Headings carry their id either on the <h2> (scaffold) or on the enclosing <section> (runbook body).
    heads = [(m.group(1) or m.group(3), m.group(2) if m.group(1) else m.group(4)) for m in re.finditer(
        r'<section id="([^"]+)"[^>]*>\s*<h2[^>]*>(.*?)</h2>|<h2 id="([^"]+)"[^>]*>(.*?)</h2>', text, flags=re.S)]
    links = " ".join(
        f'<a href="#{i}">{htmlmod.escape(re.sub(r"<[^>]+>", "", t).strip())}</a>' for i, t in heads)
    return re.sub(r'<nav class="toc">.*?</nav>', f'<nav class="toc">{links}</nav>', text, count=1, flags=re.S)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--body", type=Path)
    a = ap.parse_args()
    body = (a.body or default_body()).read_text(encoding="utf-8")
    rc = 0
    for f in a.files:
        try:
            f.write_text(inject(f.read_text(encoding="utf-8"), body), encoding="utf-8")
            print(f"injected: {f}")
        except ValueError as e:
            print(f"REFUSED {f}: {e}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
