#!/usr/bin/env python3
"""doc-new.py - create a themed HTML document from the organization config.

  doc-new.py "Title" [--kind doc|runbook] [--md FILE.md] [--out-dir DIR]

Reads the config written by the first-run wizard (lib/aitooling.py): organization name, author,
theme tokens and logo. Writes a stable file <slug>.html and a dated snapshot <slug>-YYYYMMDD.html
into the configured docs folder (runbooks folder for --kind runbook). With --md the Markdown body is
converted by md-to-html.py; without it the body is a TODO placeholder. For --kind runbook the body is
replaced by the runbook skeleton through runbook-inject.py.

Exit: 0 written, 2 usage error, 10 no config yet (run the wizard: aitooling.py ensure).
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import mimetypes
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "lib"))
import aitooling  # noqa: E402


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:60] or "document"


def logo_html(path: str) -> str:
    if not path:
        return ""
    p = Path(os.path.expanduser(path))
    if not p.is_file() or p.stat().st_size > 512_000:
        return ""
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    if not mime.startswith("image/"):
        return ""
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return '<img alt="" src="data:%s;base64,%s">' % (mime, data)


def render(cfg: dict, title: str, kind: str, body: str) -> str:
    tpl = (HERE.parent / "templates" / "doc.template.html").read_text(encoding="utf-8")
    today = dt.date.today().isoformat()
    subs = {
        "{{THEME_CSS}}": aitooling.css_vars(cfg),
        "{{TITLE}}": html.escape(title),
        "{{ORG}}": html.escape(cfg["org"]["name"]),
        "{{AUTHOR}}": html.escape(cfg["author"]["name"]),
        "{{DATE}}": today,
        "{{KIND}}": html.escape(kind),
        "{{LOGO}}": logo_html(cfg.get("theme", {}).get("logo_path", "")),
        "{{BODY}}": body,
    }
    for k, v in subs.items():
        tpl = tpl.replace(k, v)
    return tpl


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("title")
    ap.add_argument("--kind", choices=("doc", "runbook"), default="doc")
    ap.add_argument("--md", type=Path)
    ap.add_argument("--out-dir", type=Path)
    a = ap.parse_args()

    cfg = aitooling.load()
    if cfg is None or aitooling.validate(cfg):
        print("no valid config yet; run: python3 %s ensure" % (ROOT / "lib" / "aitooling.py"), file=sys.stderr)
        return aitooling.EXIT_WIZARD_NEEDED

    if a.md:
        r = subprocess.run([sys.executable, str(HERE / "md-to-html.py"), "--emit", "body", str(a.md)],
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            print(r.stderr, file=sys.stderr)
            return 2
        body = r.stdout
    else:
        body = "<p>TODO: write the body.</p>"

    folder = cfg["folders"]["runbooks" if a.kind == "runbook" else "docs"]
    out = a.out_dir or Path(os.path.expanduser(folder))
    out.mkdir(parents=True, exist_ok=True)
    slug = slugify(a.title)
    stable = out / (slug + ".html")
    snap = out / ("%s-%s.html" % (slug, dt.date.today().strftime("%Y%m%d")))
    text = render(cfg, a.title, a.kind, body)
    stable.write_text(text, encoding="utf-8")
    snap.write_text(text, encoding="utf-8")

    if a.kind == "runbook":
        inj = ROOT / "skills" / "runbook" / "scripts" / "runbook-inject.py"
        r = subprocess.run([sys.executable, str(inj), str(stable), str(snap)], capture_output=True, text=True,
                           encoding="utf-8")
        if r.returncode != 0:
            print(r.stderr, file=sys.stderr)
            return 2
    print(stable)
    print(snap)
    return 0


if __name__ == "__main__":
    sys.exit(main())
