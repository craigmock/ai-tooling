#!/usr/bin/env python3
"""aitooling.py - shared config, first-run wizard, theme and tracking helper for every ai-tooling skill.

One local config file holds everything a skill needs to look like it belongs to your organization:
organization name, author, theme tokens, tracking backend and output folders. Every skill calls
`ensure` first. If there is no valid config the skill runs the wizard (interactively in a terminal,
or by asking you the questions and calling `init`), then continues.

Config location (first match wins):
    $AI_TOOLING_CONFIG                      explicit file path
    %APPDATA%\\ai-tooling\\config.json        Windows
    $XDG_CONFIG_HOME/ai-tooling/config.json
    ~/.config/ai-tooling/config.json

Commands:
    ensure              exit 0 and print the config path when a valid config exists;
                        exit 10 and print the wizard questions as JSON when it does not.
                        With --interactive and a terminal, runs the wizard instead of exiting 10.
    wizard              interactive prompts (needs a terminal)
    init [flags]        non-interactive: write the config from flags or --answers FILE.json
    show                print the config
    get KEY             print one value by dotted key, e.g. theme.primary or folders.docs (~ expanded)
    theme-css           print the theme as CSS custom properties for a :root block
    themes              list bundled theme presets
    log-event ...       record a unit of work through the configured tracking backend
    path                print the config path

Pure standard library; runs the same on macOS, Linux and Windows.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

VERSION = 1
REPO_ROOT = Path(__file__).resolve().parent.parent
THEMES_DIR = REPO_ROOT / "themes"

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_INVALID = 2
EXIT_WIZARD_NEEDED = 10
EXIT_NO_TTY = 11

HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
FONT = re.compile(r"^[A-Za-z0-9 ,'\-]{1,120}$")
SHORT = re.compile(r"^[a-z0-9][a-z0-9\-]{0,23}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BACKENDS = ("none", "file", "webhook")

DEFAULT_FOLDERS = {
    "docs": "~/ai-tooling-output/docs",
    "runbooks": "~/ai-tooling-output/runbooks",
    "worklog": "~/ai-tooling-output/worklog",
    "sessions": "~/ai-tooling-output/sessions",
}

# The wizard, as data. The CLI prompts from this list, and `ensure` prints it so an assistant can ask the
# same questions as question cards and then call `init`. key is a dotted path into the config.
QUESTIONS = [
    {"key": "org.name", "label": "Organization name", "example": "Example Corp", "required": True},
    {"key": "org.short_name", "label": "Short name (lowercase, used in file names)", "example": "example", "required": True},
    {"key": "author.name", "label": "Your name (for authorship lines)", "example": "Alex Doe", "required": True},
    {"key": "author.email", "label": "Your email (optional)", "example": "alex@example.com", "required": False},
    {"key": "theme.preset", "label": "Start from a bundled theme (or 'custom')", "example": "default", "required": False},
    {"key": "theme.primary", "label": "Brand primary color (hex)", "example": "#1f6feb", "required": False},
    {"key": "theme.accent", "label": "Brand accent color (hex)", "example": "#8250df", "required": False},
    {"key": "theme.font_body", "label": "Body font stack", "example": "Segoe UI, Helvetica, Arial, sans-serif", "required": False},
    {"key": "theme.logo_path", "label": "Logo file path (optional, PNG/SVG)", "example": "~/brand/logo.svg", "required": False},
    {"key": "tracking.backend", "label": "Ticket/time tracking: none, file (local log) or webhook", "example": "none", "required": False},
    {"key": "tracking.webhook_url", "label": "Webhook URL (https only, only when backend is webhook)", "example": "https://example.com/hooks/work-log", "required": False},
    {"key": "folders.docs", "label": "Folder for generated documents", "example": DEFAULT_FOLDERS["docs"], "required": False},
]


def config_path() -> Path:
    env = os.environ.get("AI_TOOLING_CONFIG")
    if env:
        return Path(os.path.expanduser(env))
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "ai-tooling" / "config.json"
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "ai-tooling" / "config.json"


def list_presets() -> dict:
    out = {}
    if THEMES_DIR.is_dir():
        for p in sorted(THEMES_DIR.glob("*.json")):
            try:
                out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
    return out


def validate(cfg) -> list:
    """Return a list of problems; empty means valid."""
    errs = []
    if not isinstance(cfg, dict):
        return ["config is not a JSON object"]
    if cfg.get("version") != VERSION:
        errs.append("version must be %d" % VERSION)
    org = cfg.get("org") or {}
    if not str(org.get("name", "")).strip():
        errs.append("org.name is required")
    if not SHORT.match(str(org.get("short_name", ""))):
        errs.append("org.short_name must be lowercase letters, digits and dashes (max 24)")
    au = cfg.get("author") or {}
    if not str(au.get("name", "")).strip():
        errs.append("author.name is required")
    if au.get("email") and not EMAIL.match(au["email"]):
        errs.append("author.email does not look like an email address")
    th = cfg.get("theme") or {}
    for k in ("primary", "accent", "background", "text", "muted", "border"):
        if k in th and not HEX.match(str(th[k])):
            errs.append("theme.%s must be a hex color like #1f6feb" % k)
    for k in ("font_body", "font_mono"):
        if k in th and not FONT.match(str(th[k])):
            errs.append("theme.%s has characters that are not allowed in a font stack" % k)
    tr = cfg.get("tracking") or {}
    be = tr.get("backend", "none")
    if be not in BACKENDS:
        errs.append("tracking.backend must be one of %s" % ", ".join(BACKENDS))
    if be == "webhook" and not str(tr.get("webhook_url", "")).startswith("https://"):
        errs.append("tracking.webhook_url must start with https:// when backend is webhook")
    return errs


def load() -> dict | None:
    p = config_path()
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return cfg


def save(cfg: dict) -> Path:
    errs = validate(cfg)
    if errs:
        raise ValueError("; ".join(errs))
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return p


def build(answers: dict) -> dict:
    """Assemble a full config from flat dotted answers, filling defaults from the chosen preset."""
    def a(key, default=""):
        v = answers.get(key)
        return default if v is None or str(v).strip() == "" else str(v).strip()

    presets = list_presets()
    preset_name = a("theme.preset", "default")
    theme = dict(presets.get("default", {}))
    if preset_name != "custom" and preset_name in presets:
        theme.update(presets[preset_name])
    for k in ("primary", "accent", "background", "text", "muted", "border", "font_body", "font_mono"):
        v = a("theme." + k)
        if v:
            theme[k] = v
    theme.pop("name", None)
    theme["logo_path"] = a("theme.logo_path")
    folders = dict(DEFAULT_FOLDERS)
    for k in folders:
        v = a("folders." + k)
        if v:
            folders[k] = v
    cfg = {
        "version": VERSION,
        "org": {"name": a("org.name"), "short_name": a("org.short_name")},
        "author": {"name": a("author.name"), "email": a("author.email")},
        "theme": theme,
        "tracking": {"backend": a("tracking.backend", "none"),
                     "webhook_url": a("tracking.webhook_url"),
                     "log_file": a("tracking.log_file", str(Path(folders["worklog"]) / "events.jsonl"))},
        "folders": folders,
        "created": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if not cfg["author"]["email"]:
        cfg["author"].pop("email")
    return cfg


def dotted_get(cfg: dict, key: str):
    cur = cfg
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def cmd_ensure(args) -> int:
    cfg = load()
    errs = validate(cfg) if cfg is not None else ["no config file at %s" % config_path()]
    if not errs:
        print(config_path())
        return EXIT_OK
    if args.interactive and sys.stdin.isatty():
        return cmd_wizard(args)
    print(json.dumps({"wizard_needed": True, "config_path": str(config_path()), "problems": errs,
                      "presets": sorted(list_presets()), "questions": QUESTIONS,
                      "next": "ask these, then run: aitooling.py init --answers FILE.json (or flags)"}, indent=2))
    return EXIT_WIZARD_NEEDED


def prompt(q) -> str:
    suffix = " [%s]" % q["example"] if q.get("example") else ""
    while True:
        try:
            v = input("%s%s: " % (q["label"], suffix)).strip()
        except EOFError:
            v = ""
        if v or not q.get("required"):
            return v
        print("  required")


def cmd_wizard(args) -> int:
    if not sys.stdin.isatty():
        print("wizard needs a terminal; use `ensure` to get the questions and `init` to answer them", file=sys.stderr)
        return EXIT_NO_TTY
    print("ai-tooling first-run setup. Press Enter to accept a default shown in brackets.\n"
          "Bundled themes: %s" % ", ".join(sorted(list_presets())))
    answers = {}
    for q in QUESTIONS:
        v = prompt(q)
        if v:
            answers[q["key"]] = v
        elif q["key"] in ("theme.preset", "tracking.backend", "folders.docs") and q.get("example"):
            answers[q["key"]] = q["example"]
    if answers.get("tracking.backend") == "webhook" and not answers.get("tracking.webhook_url"):
        answers["tracking.webhook_url"] = input("Webhook URL (https): ").strip()
    return write_from_answers(answers)


def write_from_answers(answers: dict) -> int:
    cfg = build(answers)
    errs = validate(cfg)
    if errs:
        for e in errs:
            print("invalid: " + e, file=sys.stderr)
        return EXIT_INVALID
    p = save(cfg)
    for d in cfg["folders"].values():
        Path(os.path.expanduser(d)).mkdir(parents=True, exist_ok=True)
    print("wrote %s" % p)
    return EXIT_OK


FLAG_KEYS = {
    "org_name": "org.name", "short_name": "org.short_name", "author_name": "author.name",
    "author_email": "author.email", "preset": "theme.preset", "primary": "theme.primary",
    "accent": "theme.accent", "background": "theme.background", "text": "theme.text",
    "font_body": "theme.font_body", "font_mono": "theme.font_mono", "logo": "theme.logo_path",
    "backend": "tracking.backend", "webhook_url": "tracking.webhook_url", "log_file": "tracking.log_file",
    "docs_dir": "folders.docs", "runbooks_dir": "folders.runbooks", "worklog_dir": "folders.worklog",
    "sessions_dir": "folders.sessions",
}


def cmd_init(args) -> int:
    if load() is not None and not validate(load()) and not args.force:
        print("a valid config already exists at %s (use --force to replace it)" % config_path(), file=sys.stderr)
        return EXIT_USAGE
    answers = {}
    if args.answers:
        try:
            answers.update(json.loads(Path(args.answers).read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:
            print("cannot read --answers: %s" % e, file=sys.stderr)
            return EXIT_USAGE
    for flag, key in FLAG_KEYS.items():
        v = getattr(args, flag, None)
        if v is not None:
            answers[key] = v
    return write_from_answers(answers)


def cmd_show(_args) -> int:
    cfg = load()
    if cfg is None:
        print("no config; run: aitooling.py ensure", file=sys.stderr)
        return EXIT_WIZARD_NEEDED
    print(json.dumps(cfg, indent=2, sort_keys=True))
    return EXIT_OK


def cmd_get(args) -> int:
    cfg = load()
    if cfg is None:
        return EXIT_WIZARD_NEEDED
    v = dotted_get(cfg, args.key)
    if v is None:
        return EXIT_USAGE
    if args.key.startswith("folders.") or args.key in ("theme.logo_path", "tracking.log_file"):
        v = os.path.expanduser(str(v)) if v else ""
    print(v if not isinstance(v, (dict, list)) else json.dumps(v))
    return EXIT_OK


def css_vars(cfg: dict) -> str:
    th = cfg.get("theme", {})
    m = {"brand-primary": th.get("primary"), "brand-accent": th.get("accent"), "bg": th.get("background"),
         "text": th.get("text"), "muted": th.get("muted"), "border": th.get("border"),
         "font-body": th.get("font_body"), "font-mono": th.get("font_mono")}
    return "\n".join("  --%s: %s;" % (k, v) for k, v in m.items() if v)


def cmd_theme_css(_args) -> int:
    cfg = load()
    if cfg is None:
        return EXIT_WIZARD_NEEDED
    print(css_vars(cfg))
    return EXIT_OK


def cmd_themes(_args) -> int:
    for name, t in list_presets().items():
        print("%s\t%s" % (name, t.get("name", name)))
    return EXIT_OK


def cmd_log_event(args) -> int:
    """Record one unit of work. Backend none: do nothing. file: append a JSON line. webhook: POST JSON."""
    cfg = load()
    if cfg is None or validate(cfg):
        return EXIT_WIZARD_NEEDED
    tr = cfg.get("tracking", {})
    event = {"time": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "org": cfg["org"]["short_name"], "author": cfg["author"]["name"], "kind": args.kind,
             "summary": args.summary, "minutes": args.minutes, "ref": args.ref}
    be = tr.get("backend", "none")
    if be == "none":
        print("tracking backend is none; nothing recorded")
        return EXIT_OK
    if be == "file":
        p = Path(os.path.expanduser(tr["log_file"]))
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")
        print("recorded in %s" % p)
        return EXIT_OK
    req = urllib.request.Request(tr["webhook_url"], data=json.dumps(event).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            print("webhook answered %s" % r.status)
        return EXIT_OK
    except (urllib.error.URLError, OSError) as e:
        print("webhook failed: %s" % e, file=sys.stderr)
        return EXIT_INVALID


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="aitooling.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("ensure")
    e.add_argument("--interactive", action="store_true")
    sub.add_parser("wizard")
    i = sub.add_parser("init")
    i.add_argument("--answers", help="JSON file of dotted answers, e.g. {\"org.name\": \"Example Corp\"}")
    i.add_argument("--force", action="store_true")
    for flag in FLAG_KEYS:
        i.add_argument("--" + flag.replace("_", "-"), dest=flag)
    sub.add_parser("show")
    g = sub.add_parser("get")
    g.add_argument("key")
    sub.add_parser("theme-css")
    sub.add_parser("themes")
    sub.add_parser("path")
    le = sub.add_parser("log-event")
    le.add_argument("--kind", default="session")
    le.add_argument("--summary", required=True)
    le.add_argument("--minutes", type=int, default=0)
    le.add_argument("--ref", default="")
    a = ap.parse_args(argv)
    if a.cmd == "path":
        print(config_path())
        return EXIT_OK
    return {"ensure": cmd_ensure, "wizard": cmd_wizard, "init": cmd_init, "show": cmd_show, "get": cmd_get,
            "theme-css": cmd_theme_css, "themes": cmd_themes, "log-event": cmd_log_event}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
