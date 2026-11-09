#!/usr/bin/env python3
"""answers-render.py - render an interactive HTML answer sheet from a spec JSON.

/answers hands this script a spec that the assistant authored from the session's
outstanding decisions. The script owns everything that must not drift:

  * global question numbering (Q1..Qn) that survives grouping,
  * an "Other:" free-text escape hatch on EVERY question,
  * HTML escaping of every caller-supplied string (a sibling /docs port once
    shipped a stored-XSS through an unescaped title; do not repeat it),
  * the copy-to-clipboard payload, numbered to match the questions exactly.

Spec shape (all fields optional unless marked):

  {
    "title":    "Bootstrap rollout decisions",        # required
    "subtitle": "one line under the title",
    "intro":    "how to use this sheet",
    "date":     "2026-08-18",                         # defaults to today
    "groups": [                                       # required, >= 1
      {
        "title": "Secrets distribution",              # required
        "note":  "why these belong together",
        "questions": [                                # required, >= 1
          {
            "title":   "Where does the join token come from?",   # required
            "context": "2-4 sentences of seed context. Inline "
                       "<code>markup</code>, <strong>, <em>, <kbd>, <br> ok.",
            "multi":   false,                         # true -> checkboxes
            "options": [                              # required, >= 1
              {"label": "Mint per device",
               "detail": "one token per machine, 1h TTL",
               "recommended": true},
              {"label": "One shared long-lived token"}
            ]
          }
        ]
      }
    ]
  }

Usage:
    python3 answers-render.py spec.json --out sheet.html
    cat spec.json | python3 answers-render.py - --out sheet.html
    python3 answers-render.py --self-test
"""

from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import html
import os
import json
import re
import shlex
import subprocess
import sys

# Inline markup a spec author may use inside `context` / `detail`. Everything is
# escaped first, then ONLY these exact tokens are restored. Because escaping
# happens first, a tag carrying attributes (`<code onclick=...>`) can never
# match, so no attribute injection is possible through this allowlist.
_INLINE_ALLOW = (
    "code", "strong", "em", "b", "i", "kbd", "small",
)


def esc(text: object) -> str:
    """Escape a value for HTML text or attribute context. No exceptions."""
    return html.escape("" if text is None else str(text), quote=True)


_TOKEN_RE = re.compile(
    r"&lt;(/?)(%s)&gt;|&lt;br/?&gt;" % "|".join(_INLINE_ALLOW)
)


def rich(text: object) -> str:
    """Escape, then restore the tiny inline-markup allowlist, balanced.

    Restoring blindly lets a lone `</b>` through, and a spec author writing
    `<b onclick=...>x</b>` gets the opener escaped (correct) while the closer
    is restored (unbalanced markup in the page). So closers are only honored
    when their opener was restored, and anything left open is closed at the end.
    """
    escaped = esc(text)
    out = []
    stack = []
    pos = 0
    for m in _TOKEN_RE.finditer(escaped):
        out.append(escaped[pos:m.start()])
        pos = m.end()
        if m.group(2) is None:          # <br> / <br/>
            out.append("<br>")
            continue
        closing, tag = m.group(1), m.group(2)
        if not closing:
            stack.append(tag)
            out.append("<%s>" % tag)
        elif tag in stack:
            # Close everything opened inside it too, so nesting stays well formed.
            while stack:
                top = stack.pop()
                out.append("</%s>" % top)
                if top == tag:
                    break
        else:
            out.append(m.group(0))      # stray closer: leave it escaped
    out.append(escaped[pos:])
    while stack:
        out.append("</%s>" % stack.pop())
    return "".join(out)


def plain(text: object) -> str:
    """Attribute-safe PLAIN text: escaped, with the inline-markup allowlist REMOVED.

    The clipboard payload is contractually plain text, and it is built in JS from
    `data-qtitle` / option `value`. A browser hands a data attribute back to JS already
    un-escaped, so writing `&lt;code&gt;` there produces a literal `<code>` in the pasted
    answers. Caught on the first live run: a user pasted back
    `Q1. Purge the rest of <code>~/.cache/example/</code>?`. Strip here, in Python, so the
    markup never reaches the attribute at all. The visible card still uses rich().
    """
    out = re.sub(r"</?(?:%s)>" % "|".join(_INLINE_ALLOW), "", str("" if text is None else text))
    out = re.sub(r"<br\s*/?>", " ", out)
    return esc(out)


def _git(args: list, cwd=None) -> str:
    """One git command, or "" for any failure. Never raises, never blocks."""
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                             text=True, timeout=5)
    except Exception:
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _provenance() -> dict:
    """Where this sheet was written: repo, worktree, branch.

    A user ran six sheets from five sessions in one day and could not tell which was
    which. The scratchpad path is `<repo>/<session-uuid>/scratchpad/...`, so a linked
    worktree and the main checkout of the same repo produce IDENTICAL-looking paths and
    only the UUID separates them — a UUID tells a human nothing. So the sheet says on
    its face where it came from.

    Detected here rather than passed in by the skill on purpose: a step the skill prose
    has to remember is a step that gets skipped, and this is exactly the metadata that
    goes missing precisely when several sessions are running at once.

    Worktree detection is git-dir != git-common-dir, NOT the presence of a `.git` file:
    a submodule checkout has a `.git` file rather than a directory, so a
    file/dir test reports every submodule as a worktree.
    """
    top = _git(["rev-parse", "--show-toplevel"])
    if not top:
        return {}
    gd = _git(["rev-parse", "--absolute-git-dir"])
    cd = _git(["rev-parse", "--path-format=absolute", "--git-common-dir"])
    is_wt = bool(gd and cd and os.path.normpath(gd) != os.path.normpath(cd))

    # The REPO name must come from the common dir, not from the checkout dir. In a linked
    # worktree the checkout is named for the worktree ("feature-response"), and reporting
    # that as the repo reproduces the exact mix-up this is here to end.
    #   normal repo :  <repo>/.git                  -> parent basename
    #   submodule   :  <super>/.git/modules/<repo>  -> own basename
    repo = os.path.basename(top)
    if cd:
        base = os.path.basename(os.path.normpath(cd))
        repo = os.path.basename(os.path.dirname(os.path.normpath(cd))) if base == ".git" else base
    prov = {"repo": repo}
    if is_wt:
        prov["worktree"] = os.path.basename(top)
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])
    if branch and branch != "HEAD":
        prov["branch"] = branch
    return prov


def _sheet_key(title: str, date: str, prov: dict, numbered: list) -> str:
    """A stable per-sheet id for browser-local autosave.

    Must be stable across reloads of the SAME sheet and distinct between different
    sheets, because Chrome hands every file:// page one shared localStorage — without a
    per-sheet key, six sheets in six scratchpads would overwrite each other's answers,
    which is the failure this autosave exists to prevent.
    """
    seed = "\u0000".join([
        title, date, prov.get("repo", ""), prov.get("worktree", ""),
        *[plain(q.get("title", "")) for _, _, q in numbered],
    ])
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


_RECEIPT_PREFIX = "::answers-receipt:: "


def verify_receipt_line(line: str) -> tuple:
    """Is this pasted `::answers-receipt::` line safe to run? -> (ok, reason).

    The marker rides back inside a payload, and a payload is a DATA channel. It exists so
    the receipt step cannot be forgotten, not so pasted text can run arbitrary commands —
    so this refuses anything that is not the exact shape this renderer emits.

    Executable rather than a paragraph of prose in SKILL.md, because a check the model is
    merely asked to perform is a check that gets skipped on a busy turn. Run it; trust the
    exit code.
    """
    line = (line or "").strip()
    if not line.startswith(_RECEIPT_PREFIX):
        return (False, "not an ::answers-receipt:: line")
    cmd = line[len(_RECEIPT_PREFIX):]
    for ch in (";", "|", "&", "`", "$(", ">", "<", "\n"):
        if ch in cmd:
            return (False, "contains shell metacharacter %r — refusing" % ch)
    try:
        parts = shlex.split(cmd)
    except ValueError as exc:
        return (False, "unparseable: %s" % exc)
    if len(parts) != 6:
        return (False, "expected 6 tokens, got %d" % len(parts))
    py, renderer, spec_p, out_flag, out_p, receipt_flag = parts
    if py != "python3":
        return (False, "interpreter is %r, expected python3" % py)
    if os.path.basename(renderer) != "answers-render.py":
        return (False, "renderer is %r, not answers-render.py" % os.path.basename(renderer))
    if out_flag != "--out" or receipt_flag != "--receipt-now":
        return (False, "flags are not exactly --out <path> --receipt-now")
    for label, path in (("renderer", renderer), ("spec", spec_p), ("sheet", out_p)):
        if not os.path.exists(path):
            return (False, "%s path does not exist: %s" % (label, path))
    return (True, cmd)


def _stamp() -> str:
    """Local wall-clock stamp for the top of the sheet: date, time, and zone.

    A sheet gets answered hours or days after it is written, and re-rendered from
    the same spec more than once. Without the time on the page, two renders of the
    same batch are indistinguishable and the answers file cannot say which one it
    came from. Local time with the zone, not UTC — it is read by the person the
    zone belongs to. %Z is empty on some builds, so fall back to the offset.
    """
    now = datetime.datetime.now().astimezone()
    zone = now.strftime("%Z") or now.strftime("%z")
    return ("%s %s" % (now.strftime("%Y-%m-%d %H:%M"), zone)).strip()


def _flatten(spec: dict) -> list:
    """Assign global question numbers across all groups. Numbering is owned
    here so a regrouped spec can never renumber inconsistently."""
    numbered = []
    n = 0
    for group in spec.get("groups") or []:
        for question in group.get("questions") or []:
            n += 1
            numbered.append((n, group, question))
    return numbered


# A question that cannot be answered from the sheet alone is worse than an absent
# question: it costs the reader the time to work out that it is unanswerable, and
# it looks like it was thought about. All three shapes below shipped in a live
# /nrp sheet on 2026-08-23 and are now refused rather than rendered.
_FRAGMENT_RE = re.compile(r"^\s*(?:[,;:.]|and\b|or\b|but\b)", re.I)


def _validate(numbered: list) -> None:
    """Refuse a spec whose questions cannot be answered from the page.

    Deliberately at RENDER time, not in either caller: /answers questions are
    authored by a model and /nrp questions are derived by a parser, and both have
    produced these shapes. A guard in one caller leaves the other free.
    """
    problems = []
    for qnum, _group, q in numbered:
        title = plain(q.get("title", "")) or "(untitled)"
        where = "Q%d %r" % (qnum, title[:60])

        # .strip(): plain() escapes but does not trim, so a whitespace-only
        # context is truthy and would sail past the emptiness check.
        ctx = plain(q.get("context") or "").strip()
        if not ctx:
            problems.append("%s has no context. A question the reader cannot "
                            "answer without scrolling elsewhere is not finished."
                            % where)
        elif _FRAGMENT_RE.match(ctx):
            problems.append(
                "%s has a FRAGMENT for context: %r. It begins mid-sentence, so it "
                "has lost its own subject — usually a title that was sliced out of "
                "the middle of the source text. Give the whole sentence."
                % (where, ctx[:70]))

        opts = q.get("options") or []
        rec = [o for o in opts if o.get("recommended")]
        if q.get("unauthored"):
            if rec:
                problems.append("%s is marked unauthored but still recommends an "
                                "option. Unauthored means no position was taken."
                                % where)
        elif q.get("multi"):
            # A multi-select can legitimately recommend several — "which repos",
            # "which platforms" — so the rule is at least one, not exactly one.
            if not rec:
                problems.append(
                    "%s is multi-select and recommends nothing. Say which set you "
                    "would pick, or set \"unauthored\": true." % where)
        elif len(rec) != 1:
            problems.append(
                "%s has %d recommended options, expected exactly 1. Take a "
                "position, or set \"unauthored\": true to say plainly that this "
                "one was derived and nobody has." % (where, len(rec)))

    if problems:
        raise ValueError(
            "spec has %d unanswerable question(s):\n  - %s"
            % (len(problems), "\n  - ".join(problems)))


def _options_html(qnum: int, question: dict) -> str:
    multi = bool(question.get("multi"))
    kind = "checkbox" if multi else "radio"
    name = "q%d" % qnum
    options = question.get("options") or []

    # Pre-select the recommended option (single-select only). If the author
    # marked none, the first option is the default so the sheet is never blank.
    default_idx = None
    if not multi and options:
        default_idx = 0
        for i, opt in enumerate(options):
            if opt.get("recommended"):
                default_idx = i
                break

    rows = []
    for i, opt in enumerate(options):
        label = str(opt.get("label", "")).strip()
        detail = opt.get("detail")
        recommended = bool(opt.get("recommended"))
        # The clipboard payload reads this input's value, so it carries the
        # PLAIN label text (attribute-escaped), never the rich-markup version.
        checked = " checked" if (not multi and i == default_idx) else ""
        badge = '<span class="rec">recommended</span>' if recommended else ""
        det = '<span class="det">%s</span>' % rich(detail) if detail else ""
        rows.append(
            '<label class="o">'
            '<input class="opt" type="%s" name="%s" value="%s"%s>'
            '<span class="otxt"><span class="olab">%s%s</span>%s</span>'
            "</label>" % (kind, esc(name), plain(label), checked, rich(label), badge, det)
        )

    # Every question ends with Other + a free-text box. Non-negotiable: it is
    # the escape hatch for when none of the authored options actually fit.
    rows.append(
        '<label class="o other">'
        '<input class="opt" type="%s" name="%s" value="__other__">'
        '<span class="otxt"><span class="olab">Other:</span>'
        '<input class="other-input" type="text" '
        'placeholder="type your own instruction here" '
        'aria-label="Other answer for question %d"></span>'
        "</label>" % (kind, esc(name), qnum)
    )
    return "\n".join(rows)


def render(spec: dict, spec_path: str = "", out_path: str = "") -> str:
    title = str(spec.get("title") or "Answer sheet")
    subtitle = spec.get("subtitle") or ""
    intro = spec.get("intro") or (
        "Pick an answer for each question, add anything else in the notes box, "
        "then press Copy my answers and paste the result back into the session."
    )
    date = str(spec.get("date") or datetime.date.today().isoformat())
    generated = str(spec.get("generated") or _stamp())
    # Spec wins when it says something; otherwise detect. A re-render of an OLD spec
    # in a different checkout must not silently relabel where the questions came from.
    prov = dict(_provenance())
    # A receipt is written by the skill at Phase 5, when the pasted payload actually
    # reaches the session. The PAGE cannot know this — it can prove you answered and
    # that you pressed Copy, but a clipboard is not a delivery. Anything claiming
    # "pasted" from inside the browser would be a guess, and the whole point of this
    # banner is that the operator can trust it enough to close the tab.
    receipt = spec.get("receipt") or {}
    receipt_at = str(receipt.get("at") or "")

    # The receipt command, carried back to the session INSIDE the copied payload.
    #
    # a reviewer's idea, and it fixes the weak link in the previous design: the green
    # "safe to close" state depended on the skill remembering to issue a receipt, and a
    # step that lives only in prose is a step that gets skipped — which leaves him holding
    # a sheet he already answered with no way to tell. Shipping the instruction WITH the
    # data means the paste itself is what proves delivery. It cannot arrive without it.
    #
    # Emitted only when both paths are known (rendering to stdout, or from a stdin spec,
    # has nothing to point at). Note this puts local paths into a published Artifact —
    # a private one, and they reveal no more than the repo name already does.
    rcmd = ""
    if spec_path and out_path and spec_path != "-":
        rcmd = "python3 %s %s --out %s --receipt-now" % (
            shlex.quote(os.path.abspath(__file__)),
            shlex.quote(os.path.abspath(spec_path)),
            shlex.quote(os.path.abspath(out_path)),
        )
    for k in ("repo", "worktree", "branch"):
        if spec.get(k):
            prov[k] = str(spec[k])

    numbered = _flatten(spec)
    if not numbered:
        raise ValueError("spec contains no questions")
    _validate(numbered)
    skey = _sheet_key(title, date, prov, numbered)

    bits = []
    if prov.get("repo"):
        bits.append('<strong>%s</strong>' % esc(prov["repo"]))
    if prov.get("worktree"):
        bits.append('worktree <strong>%s</strong>' % esc(prov["worktree"]))
    elif prov.get("repo"):
        bits.append("main checkout")
    if prov.get("branch"):
        bits.append('branch <code>%s</code>' % esc(prov["branch"]))
    origin_html = ('<div class="origin">%s</div>' % " &middot; ".join(bits)) if bits else ""
    # The same line, flattened, for the pasted-back payload.
    origin_txt = " / ".join(filter(None, [
        prov.get("repo", ""),
        ("worktree " + prov["worktree"]) if prov.get("worktree") else
        ("main checkout" if prov.get("repo") else ""),
        ("branch " + prov["branch"]) if prov.get("branch") else "",
    ]))

    body = []
    seen_groups = []
    for qnum, group, question in numbered:
        if id(group) not in seen_groups:
            seen_groups.append(id(group))
            count = len(group.get("questions") or [])
            note = group.get("note")
            body.append(
                '<h2>%s <span class="cnt">%d</span></h2>'
                % (rich(group.get("title") or "Questions"), count)
            )
            if note:
                body.append('<p class="gd">%s</p>' % rich(note))
        ctx = question.get("context")
        # Say so on the page when nobody took a position. The reader is otherwise
        # left to assume the options were considered and the absence of a
        # recommendation was itself a judgement.
        derived = (
            '  <div class="derived">Derived from the source text — nobody has '
            'authored these options or taken a position. The Other box is the '
            'real answer if none of them fit.</div>\n'
            if question.get("unauthored") else ""
        )
        body.append(
            '<div class="q" data-qn="%d" data-qtitle="%s">\n'
            '  <div class="qh"><span class="qn">Q%d</span>'
            '<strong class="qt">%s</strong></div>\n'
            "%s%s"
            '  <div class="opts">\n%s\n  </div>\n'
            "</div>"
            % (
                qnum,
                plain(question.get("title", "")),
                qnum,
                rich(question.get("title", "")),
                '  <div class="desc">%s</div>\n' % rich(ctx) if ctx else "",
                derived,
                _options_html(qnum, question),
            )
        )

    return _PAGE.format(
        title=esc(title),
        subtitle=('<div class="sub">%s</div>' % rich(subtitle)) if subtitle else "",
        intro=rich(intro),
        date=esc(date),
        generated=esc(generated),
        origin=origin_html,
        origin_txt=esc(origin_txt),
        skey=esc(skey),
        receipt_at=esc(receipt_at),
        rcmd=esc(rcmd),
        total=len(numbered),
        body="\n".join(body),
        css=_CSS + _theme_override(),
        js=_JS,
    )


_CSS = """
:root{--bg:#0d1117;--surf:#161b22;--surf2:#1c2128;--bd:#30363d;--tx:#e6edf3;
--mut:#8b949e;--acc:#28c3ef;--ok:#3fb950;--warn:#d29922;--navy:#00003c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
font:15px/1.6 Inter,-apple-system,Segoe UI,sans-serif;padding:0 0 40px}
.wrap{max-width:1000px;margin:0 auto;padding:0 24px}
header{background:linear-gradient(135deg,var(--navy),#123);
border-bottom:2px solid var(--acc);padding:26px 0;margin-bottom:26px}
h1{margin:0 0 6px;font-size:25px}
.stamp{color:var(--mut);font:12px ui-monospace,Menlo,monospace;letter-spacing:.02em;margin-bottom:2px}
.origin{color:#c9d1d9;font-size:12.5px;margin-bottom:9px}
.origin strong{color:var(--acc);font-weight:600}
.origin code{font:12px ui-monospace,Menlo,monospace;background:rgba(255,255,255,.07);padding:1px 5px;border-radius:4px}
.restored{background:rgba(63,185,80,.11);border:1px solid var(--ok);border-radius:7px;padding:9px 13px;margin:18px 0 0;font-size:13px;color:var(--tx)}
.restored b{color:var(--ok)}
.restored a{color:var(--acc);text-decoration:underline}
.saved{color:var(--ok)}
.status{margin:18px 0 0;padding:11px 14px;border-radius:7px;font-size:13.5px;
border:1px solid var(--bd);background:var(--surf);display:flex;gap:10px;align-items:baseline}
.status .dot{flex:0 0 auto;font-size:15px;line-height:1}
.status b{font-weight:600}
.status .sub2{color:var(--mut);font-size:12.5px}
.st-todo{border-color:var(--bd)}
.st-todo b{color:var(--mut)}
.st-ready{border-color:var(--warn);background:rgba(210,153,34,.10)}
.st-ready b{color:var(--warn)}
.st-copied{border-color:var(--acc);background:rgba(40,195,239,.10)}
.st-copied b{color:var(--acc)}
.st-done{border-color:var(--ok);background:rgba(63,185,80,.12)}
.st-done b{color:var(--ok)}
.st-stale{border-color:var(--warn);background:rgba(210,153,34,.10)}
.st-stale b{color:var(--warn)}
.sub{color:#c9d1d9;font-size:14px;margin-bottom:6px}
.intro{color:var(--mut);font-size:13px;max-width:78ch}
h2{font-size:16px;margin:34px 0 4px;padding-bottom:7px;
border-bottom:1px solid var(--bd);color:var(--acc)}
.cnt{background:var(--surf2);border:1px solid var(--bd);border-radius:11px;
padding:1px 9px;font-size:12px;color:var(--mut)}
.gd{color:var(--mut);font-size:13px;margin:0 0 14px}
.q{background:var(--surf);border:1px solid var(--bd);border-radius:8px;
padding:13px 15px;margin-bottom:11px}
.q.unanswered{border-color:var(--warn)}
.qh{display:flex;gap:9px;align-items:baseline;margin-bottom:6px}
.qn{background:var(--surf2);border:1px solid var(--bd);border-radius:5px;
padding:1px 8px;font:12px ui-monospace,Menlo,monospace;color:var(--acc);
flex:0 0 auto}
.qt{font-size:15px}
.desc{color:#c9d1d9;font-size:13.5px;margin:0 0 10px;max-width:82ch}
.derived{color:var(--mut);font-size:12.5px;margin:0 0 10px;max-width:82ch;
  border-left:2px solid #6e7681;padding-left:9px}
code{background:var(--surf2);border:1px solid var(--bd);border-radius:5px;
padding:1px 6px;font:12.5px ui-monospace,Menlo,monospace;color:var(--acc)}
.opts{display:flex;flex-direction:column;gap:6px}
.o{display:flex;align-items:flex-start;gap:9px;background:var(--surf2);
border:1px solid var(--bd);border-radius:6px;padding:8px 11px;font-size:13.5px;
cursor:pointer;user-select:none}
.o:hover{border-color:var(--acc)}
.o input.opt{accent-color:var(--acc);margin:4px 0 0}
.o:has(input.opt:checked){border-color:var(--acc);background:rgba(40,195,239,.12)}
.otxt{display:flex;flex-direction:column;gap:2px;flex:1 1 auto;min-width:0}
.olab{font-weight:500}
.rec{margin-left:8px;font-size:11px;color:var(--ok);border:1px solid var(--ok);
border-radius:10px;padding:0 7px;font-weight:600;white-space:nowrap}
.det{color:var(--mut);font-size:12.5px}
.other-input{width:100%;background:var(--bg);color:var(--tx);
border:1px solid var(--bd);border-radius:5px;padding:6px 9px;margin-top:4px;
font:13px ui-monospace,Menlo,monospace}
.other-input:focus{outline:none;border-color:var(--acc)}
.bar{position:sticky;bottom:0;background:rgba(13,17,23,.97);
border-top:2px solid var(--acc);padding:14px 0;margin-top:34px;
backdrop-filter:blur(8px)}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
button{background:var(--acc);color:#04121a;border:0;border-radius:7px;
padding:10px 20px;font-size:14px;font-weight:700;cursor:pointer;
font-family:inherit}
button:hover{filter:brightness(1.12)}
button.sec{background:var(--surf2);color:var(--tx);border:1px solid var(--bd)}
textarea{width:100%;height:96px;background:var(--surf);color:var(--tx);
border:1px solid var(--bd);border-radius:7px;padding:10px;
font:13px ui-monospace,Menlo,monospace;margin-top:10px}
#fallback{display:none;height:220px}
.tally{color:var(--mut);font-size:12.5px}
.ok{color:var(--ok);font-weight:600}
.warnt{color:var(--warn);font-weight:600}
@media(max-width:600px){.wrap{padding:0 14px}h1{font-size:21px}}
"""


def _theme_override() -> str:
    """Brand the sheet from the organization config written by the first-run wizard, if there is one.

    Maps the shared theme tokens onto this sheet's variables. A missing or invalid config changes
    nothing: the sheet keeps its built-in dark palette, so the renderer never needs the wizard to run.
    """
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib"))
        import aitooling
        cfg = aitooling.load()
        if cfg is None or aitooling.validate(cfg):
            return ""
        th = cfg.get("theme", {})
    except Exception:
        return ""
    pairs = (("--bg", "background"), ("--tx", "text"), ("--mut", "muted"), ("--bd", "border"),
             ("--acc", "primary"), ("--navy", "primary"))
    decl = ";".join("%s:%s" % (var, th[key]) for var, key in pairs if th.get(key))
    return ":root{%s}\n" % decl if decl else ""


_JS = """
var TITLE=document.body.dataset.title, DATE=document.body.dataset.date,
    GENERATED=document.body.dataset.generated,
    ORIGIN=document.body.dataset.origin, SKEY='answers:'+document.body.dataset.skey,
    RECEIPT=document.body.dataset.receipt||'', RCMD=document.body.dataset.rcmd||'';
function qs(s,r){return (r||document).querySelector(s);}
function qsa(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s));}

// Typing in an Other box selects its control, so an answer is never lost to a
// forgotten click.
qsa('.other-input').forEach(function(inp){
  var sel=function(){var c=inp.closest('.o').querySelector('input.opt');
    if(!c.checked){c.checked=true;tally();}};
  inp.addEventListener('focus',sel);
  inp.addEventListener('input',sel);
  inp.addEventListener('click',function(e){e.stopPropagation();});
});

function answered(q){
  var sel=qsa('input.opt:checked',q);
  if(!sel.length) return false;
  var other=sel.filter(function(s){return s.value==='__other__';});
  if(other.length && sel.length===other.length){
    var t=qs('.other-input',q); return !!(t && t.value.trim());
  }
  return true;
}

function tally(){
  var qs_=qsa('.q'), n=0;
  qs_.forEach(function(q){
    var a=answered(q); if(a)n++;
    q.classList.toggle('unanswered',!a);
  });
  qs('#tally').innerHTML = n===qs_.length
    ? '<span class="ok">'+n+' of '+qs_.length+' answered</span>'
    : '<span class="warnt">'+n+' of '+qs_.length+' answered</span>';
  setStatus();
}
document.addEventListener('change',tally);
document.addEventListener('input',function(e){
  if(e.target.classList.contains('other-input'))tally();});

// ---------------------------------------------------------------------------
// Browser-local autosave. A user answered a sheet, needed to reboot before pasting the
// result back into the session, and lost the answers — the page held them and nothing
// else did. Every change is now written to localStorage and restored on load.
//
// Fails SILENTLY and completely: a private window, a browser that refuses storage on
// file:// URLs, or a cleared profile must never break the sheet itself. Storage is a
// convenience on top of a page that works without it.
//
// The key includes the repo, the worktree and the question list (see _sheet_key) because
// Chrome gives EVERY file:// page one shared localStorage. Without that, six sheets in six
// scratchpad dirs would overwrite each other -- precisely the loss this prevents.
function store(op){ try { return op(window.localStorage); } catch(e) { return null; } }

// ---------------------------------------------------------------------------
// The status banner. A user runs four or five sessions at once and needs to know, per
// sheet, whether it is finished with him — i.e. whether he can close the tab.
//
// It states ONLY what is provable, because a banner he cannot trust is worse than none:
//
//   answered?  the page counts its own inputs.                      -> provable
//   copied?    the page owns the Copy button and records the click. -> provable
//   pasted?    happens in a terminal the page cannot see.           -> NOT provable
//
// So "safe to close" is never asserted by the page on its own. It is unlocked by a
// RECEIPT that the /answers skill writes into the spec and re-renders, at the moment the
// pasted payload actually reaches the session. If the sheet is edited after that receipt,
// the banner drops back to "copy again" — a receipt vouches for the answers the session
// SAW, not for whatever the page holds now.
function readState(){ 
  var raw=store(function(ls){ return ls.getItem(SKEY); });
  if(!raw) return null;
  try { return JSON.parse(raw); } catch(e) { return null; }
}

function setStatus(){
  var el=qs('#status'); if(!el) return;
  var all=qsa('.q'), n=all.filter(answered).length, m=all.length;
  var st=readState()||{};
  var copiedAt = st.copiedAt ? new Date(st.copiedAt) : null;
  var editedAt = st.when ? new Date(st.when) : null;
  var recAt = RECEIPT ? new Date(RECEIPT) : null;
  if(recAt && isNaN(recAt.getTime())) recAt=null;
  var t=function(d){ return d.toLocaleString(); };

  var cls,dot,msg,sub='';
  if(recAt && editedAt && editedAt.getTime() > recAt.getTime()+1000){
    cls='st-stale'; dot='\u26A0';
    msg='Edited since the session received these.';
    sub='The session has the answers from '+t(recAt)+', not the ones on screen now. '
       +'Press Copy my answers and paste again.';
  } else if(recAt){
    cls='st-done'; dot='\u2713';
    msg='Received by the session \u2014 safe to close this page.';
    sub='Recorded '+t(recAt)+'. Nothing further is needed from you on this sheet.';
  } else if(n<m){
    cls='st-todo'; dot='\u25CB';
    msg=n+' of '+m+' answered.';
    sub='Nothing has been sent yet. Answers save in this browser as you type.';
  } else if(copiedAt){
    cls='st-copied'; dot='\u2192';
    msg='All '+m+' answered and copied at '+t(copiedAt)+' \u2014 now paste it into the session.';
    sub='Not yet confirmed received. This turns green once the session has it, so keep '
       +'this page until then.';
  } else {
    cls='st-ready'; dot='\u25CF';
    msg='All '+m+' answered \u2014 not copied yet.';
    sub='Press Copy my answers, then paste the result into the session.';
  }
  el.className='status '+cls;
  el.innerHTML='<span class="dot">'+dot+'</span><span><b>'+msg+'</b>'
              +(sub?'<br><span class="sub2">'+sub+'</span>':'')+'</span>';
}

function snapshot(){
  var prev=readState()||{};
  // copiedAt is sticky across edits: it records that a copy HAPPENED, and setStatus
  // compares it against `when` to decide whether that copy is still current.
  var st={v:1,when:new Date().toISOString(),copiedAt:prev.copiedAt||null,q:{},notes:''};
  qsa('.q').forEach(function(q){
    var picked=qsa('input.opt:checked',q).map(function(s){return s.value;});
    var t=qs('.other-input',q);
    st.q[q.dataset.qn]={picked:picked,other:t?t.value:''};
  });
  var n=qs('#notes'); st.notes=n?n.value:'';
  return st;
}

function save(){ store(function(ls){ ls.setItem(SKEY,JSON.stringify(snapshot())); }); }

function restore(){
  var raw=store(function(ls){ return ls.getItem(SKEY); });
  if(!raw) return;
  var st; try { st=JSON.parse(raw); } catch(e) { return; }
  if(!st||!st.q) return;
  var touched=0;
  qsa('.q').forEach(function(q){
    var rec=st.q[q.dataset.qn]; if(!rec) return;
    qsa('input.opt',q).forEach(function(inp){
      var want=(rec.picked||[]).indexOf(inp.value)>=0;
      if(inp.checked!==want){inp.checked=want;}
      if(want)touched++;
    });
    var t=qs('.other-input',q);
    if(t&&rec.other){t.value=rec.other;touched++;}
  });
  var n=qs('#notes'); if(n&&st.notes){n.value=st.notes;touched++;}
  if(!touched) return;
  // Once the sheet is green, the status banner already says everything that matters and
  // a second green box only competes with it. Restore silently.
  if(qs('#status') && qs('#status').classList.contains('st-done')) return;
  var when=st.when?new Date(st.when):null;
  var el=qs('#restored');
  el.innerHTML='<b>Restored your answers</b> from this browser'
    +(when?' (last edited '+when.toLocaleString()+')':'')
    +'. They save automatically as you type \u2014 you can close this page and come back. '
    +'<a href="#" id="wipe">Clear them and start over</a>.';
  el.hidden=false;
  qs('#wipe').addEventListener('click',function(e){
    e.preventDefault();
    store(function(ls){ ls.removeItem(SKEY); });
    location.reload();
  });
}

document.addEventListener('change',save);
document.addEventListener('input',save);

function payload(){
  var out=['ANSWERS - '+TITLE+' - '+DATE,'Generated '+GENERATED];
  if(ORIGIN){out.push('From '+ORIGIN);}
  out.push('');
  qsa('.q').forEach(function(q){
    out.push('Q'+q.dataset.qn+'. '+q.dataset.qtitle);
    var sel=qsa('input.opt:checked',q);
    if(!sel.length){out.push('    (no answer)');}
    sel.forEach(function(s){
      if(s.value==='__other__'){
        var t=qs('.other-input',q), v=t?t.value.trim():'';
        out.push('    Other: '+(v||'(left blank)'));
      } else { out.push('    '+s.value); }
    });
    out.push('');
  });
  var n=qs('#notes').value.trim();
  if(n){out.push('NOTES',n,'');}
  // Rides along so the session can confirm delivery back to this sheet. Last, and on ONE
  // line, because a terminal paste that collapses newlines must not break it — the user's
  // paste of 2026-08-30 arrived with every newline stripped.
  if(RCMD){
    out.push('---');
    out.push('Assistant: I have pasted these. Mark the sheet received so I know it landed:');
    out.push('::answers-receipt:: '+RCMD);
  }
  return out.join('\\n');
}

function flash(html_,cls){
  qs('#st').innerHTML='<span class="'+(cls||'ok')+'">'+html_+'</span>';
  setTimeout(function(){qs('#st').textContent='';},5000);
}

// Three-step copy chain. The last step always works, so the copy path can
// never dead-end on a browser that blocks the clipboard API.
function copyAnswers(){
  var text=payload();
  // Copy is the moment the operator believes the answers are "handed over", so make the
  // local save explicit and unconditional here rather than trusting the input listeners
  // to have fired. saved===false means storage is unavailable; say so instead of implying
  // a safety net that is not there.
  var snap = snapshot(); snap.copiedAt = new Date().toISOString();
  var saved = store(function(ls){ ls.setItem(SKEY,JSON.stringify(snap)); return true; }) === true;
  setStatus();
  var kept = saved ? ' Answers saved in this browser.'
                   : ' NOTE: this browser refused local storage \u2014 the answers are NOT saved here.';
  var legacy=function(){
    var fb=qs('#fallback');
    fb.value=text; fb.style.display='block'; fb.focus(); fb.select();
    var okc=false;
    try{okc=document.execCommand('copy');}catch(e){okc=false;}
    if(okc){fb.style.display='none';flash('Copied. Paste it back to the assistant.'+kept,
                                     saved?'':'warnt');}
    else{flash('Could not reach the clipboard. The text is selected below, '+
               'copy it manually.','warnt');}
  };
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(text).then(
      function(){flash('Copied. Paste it back to the assistant.'+kept,saved?'':'warnt');},legacy);
  } else { legacy(); }
}

function showText(){
  var fb=qs('#fallback');
  fb.value=payload();
  fb.style.display = fb.style.display==='block' ? 'none' : 'block';
  if(fb.style.display==='block'){fb.focus();fb.select();}
}
setStatus();
restore();
tally();
"""

_PAGE = """<meta charset="utf-8">
<title>{title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{css}</style>
<body data-title="{title}" data-date="{date}" data-generated="{generated}"
      data-origin="{origin_txt}" data-skey="{skey}" data-receipt="{receipt_at}"
      data-rcmd="{rcmd}">
<header><div class="wrap">
  <div class="stamp">Generated {generated}</div>
  {origin}
  <h1>{title}</h1>
  {subtitle}
  <div class="intro">{intro}</div>
</div></header>
<div class="wrap">
<div id="status" class="status" role="status" aria-live="polite"></div>
<div id="restored" class="restored" hidden></div>
{body}
<div class="bar">
  <div class="row">
    <button onclick="copyAnswers()">Copy my answers</button>
    <button class="sec" onclick="showText()">Show text</button>
    <span id="tally" class="tally"></span>
    <span id="st" class="tally"></span>
  </div>
  <textarea id="notes" placeholder="Additional notes back to the assistant (optional)"></textarea>
  <textarea id="fallback" readonly aria-label="Answer text to copy manually"></textarea>
</div>
</div>
<script>{js}</script>
"""

_FIXTURE = {
    "title": 'Self test <script>alert(1)</script>',
    "subtitle": "fixture used by --self-test",
    "groups": [
        {
            "title": "First group",
            "note": "two questions here",
            "questions": [
                {
                    "title": "Question one",
                    "context": "Some <code>inline</code> context.",
                    "options": [
                        {"label": "Alpha", "recommended": True, "detail": "the safe one"},
                        {"label": "Beta"},
                    ],
                },
                {
                    # The unauthored path: derived, so no position is taken and
                    # the page says so. Exercised here because it is the shape
                    # /nrp emits for a decision with no recorded default.
                    "title": "Question two",
                    "context": "Context is mandatory even when nobody took a position.",
                    "unauthored": True,
                    "options": [{"label": "Yes"}, {"label": "No"}],
                },
            ],
        },
        {
            "title": "Second group",
            "questions": [
                {
                    "title": "Question three, multi",
                    "context": "Multi-select may recommend more than one option.",
                    "multi": True,
                    "options": [
                        {"label": "One", "recommended": True},
                        {"label": "Two", "recommended": True},
                        {"label": "Three"},
                    ],
                }
            ],
        },
    ],
}


def _self_test() -> int:
    out = render(_FIXTURE)
    checks = [
        ("global numbering starts at Q1", 'data-qn="1"' in out),
        ("numbering continues across groups", 'data-qn="3"' in out),
        ("no phantom fourth question", 'data-qn="4"' not in out),
        ("group two restarts no numbering", out.index('data-qn="2"') < out.index('data-qn="3"')),
        ("script tag escaped", "<script>alert(1)" not in out),
        ("escaped form present", "&lt;script&gt;" in out),
        ("other box on every question", out.count("other-input") >= 3 + 1),
        ("multi renders checkboxes", 'type="checkbox"' in out),
        ("single renders radios", 'type="radio"' in out),
        ("recommended badge", 'class="rec"' in out),
        ("recommended preselected", 'value="Alpha" checked' in out),
        ("allowlisted inline code survives", "<code>inline</code>" in out),
        ("notes textarea after questions", out.index("id=\"notes\"") > out.index('data-qn="3"')),
        ("clipboard fallback present", "execCommand" in out),
        ("unauthored question is marked on the page", 'class="derived"' in out),
        ("generated stamp on the page", 'class="stamp">Generated ' in out),
        ("stamp carries date, time and zone",
         re.search(r'class="stamp">Generated \d{4}-\d\d-\d\d \d\d:\d\d \S+<', out)
         is not None),
        ("payload carries the stamp", "'Generated '+GENERATED" in out),
        ("origin line rendered when provenance resolves",
         ("class=\"origin\"" in out) or not _provenance()),
        ("body carries the sheet key for autosave", 'data-skey="' in out),
        ("sheet key is not empty", 'data-skey=""' not in out),
        ("autosave writes on every change", "document.addEventListener('input',save)" in out),
        ("saved answers are restored on load", "restore();" in out),
        ("storage failure is swallowed, never thrown", "catch(e) { return null; }" in out),
        ("copy reports when storage refused", "NOT saved here" in out),
        ("payload names the origin", "'From '+ORIGIN" in out),
        # Without this the browser sniffs, lands on windows-1252, and every em-dash and
        # middot in the sheet renders as mojibake. Found live on 2026-08-30 with
        # document.characterSet reporting windows-1252 on a sheet with no meta.
        ("declares utf-8 so the browser does not guess", '<meta charset="utf-8">' in out),
        ("status banner element present", 'id="status"' in out),
        ("no receipt renders an empty receipt slot", 'data-receipt=""' in out),
        # The page must never claim delivery on its own. If this string can be reached
        # without a receipt, the banner starts lying and the whole feature is worthless.
        # Structural, not a substring count: the green message must be REACHABLE only
        # from inside the `recAt` branch. A count alone passed while counting this
        # file's own explanatory comment, which proves nothing about the code path.
        ("safe-to-close is gated behind a receipt",
         out.count("safe to close this page") == 1
         and out.index("} else if(recAt){")
             < out.index("safe to close this page")
             < out.index("} else if(n<m){")),
        ("a receipt older than the last edit goes stale, not green",
         "Edited since the session received these" in out),
        ("copied state does not claim receipt", "Not yet confirmed received" in out),
        ("copiedAt survives later edits", "prev.copiedAt" in out),
        ("payload carries the receipt marker", "::answers-receipt:: " in out),
        ("receipt marker is emitted on ONE line",
         "out.push('::answers-receipt:: '+RCMD)" in out),
        # After NOTES, so a Q-parser never has to skip past it.
        ("receipt marker comes after the notes block",
         out.index("if(n){out.push('NOTES'") < out.index("::answers-receipt::")),
        ("marker is suppressed when there is nowhere to point",
         "if(RCMD){" in out),
    ]

    # The receipt-line verifier, exercised on the shapes that must be REFUSED. A guard is
    # only worth having if it is proven to fire, and this one gates a command arriving
    # through a paste. Fixtures are deliberately harmless strings: what is under test is
    # the metacharacter/shape rejection, and a benign payload proves that identically.
    _real = os.path.abspath(__file__)
    _good = "%spython3 %s %s --out %s --receipt-now" % (
        _RECEIPT_PREFIX, _real, _real, _real)  # paths need only EXIST for the check
    checks += [
        ("verifier accepts the shape we emit", verify_receipt_line(_good)[0]),
        ("REFUSES a chained command", not verify_receipt_line(_good + " ; whoami")[0]),
        ("REFUSES a piped command", not verify_receipt_line(_good + " | sh")[0]),
        ("REFUSES a backgrounded command", not verify_receipt_line(_good + " & id")[0]),
        ("REFUSES command substitution",
         not verify_receipt_line(_good.replace("--receipt-now", "$(id)"))[0]),
        ("REFUSES a redirect", not verify_receipt_line(_good + " > /tmp/x")[0]),
        ("REFUSES backticks", not verify_receipt_line(_good + " `id`")[0]),
        ("REFUSES a different interpreter",
         not verify_receipt_line(_good.replace("python3", "bash", 1))[0]),
        ("REFUSES a different script",
         not verify_receipt_line(_good.replace(_real, "/tmp/other.py", 1))[0]),
        ("REFUSES a nonexistent path",
         not verify_receipt_line("%spython3 %s /nope/spec.json --out %s --receipt-now"
                                 % (_RECEIPT_PREFIX, _real, _real))[0]),
        ("REFUSES extra arguments", not verify_receipt_line(_good + " --extra")[0]),
        ("REFUSES a line without the marker",
         not verify_receipt_line("python3 x.py y --out z --receipt-now")[0]),
    ]

    # Negative controls. The guard exists to REFUSE these three shapes, all of
    # which reached a live sheet on 2026-08-23; a validator is only worth having
    # if it is proven to fire, so each one is rendered and required to raise.
    def _rejects(label, mutate):
        bad = copy.deepcopy(_FIXTURE)
        mutate(bad)
        try:
            render(bad)
        except ValueError:
            return (label, True)
        return (label, False)

    def _fragment(spec):
        spec["groups"][0]["questions"][0]["context"] = ", and when. Blocked regardless."

    def _no_context(spec):
        spec["groups"][0]["questions"][0]["context"] = "   "

    def _no_recommendation(spec):
        for opt in spec["groups"][0]["questions"][0]["options"]:
            opt.pop("recommended", None)

    def _unauthored_but_recommends(spec):
        spec["groups"][0]["questions"][1]["options"][0]["recommended"] = True

    checks.extend([
        _rejects("REFUSES a fragment context", _fragment),
        _rejects("REFUSES an empty context", _no_context),
        _rejects("REFUSES a single-select with no recommendation", _no_recommendation),
        _rejects("REFUSES unauthored + a recommendation", _unauthored_but_recommends),
    ])
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print("%s  %s" % ("ok   " if ok else "FAIL ", name))
    if failed:
        print("\n%d self-test check(s) failed" % len(failed), file=sys.stderr)
        return 1
    print("\nself-test passed (%d checks)" % len(checks))
    return 0


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Render an /answers HTML answer sheet.")
    ap.add_argument("spec", nargs="?", help="spec JSON path, or - for stdin")
    ap.add_argument("--out", help="write HTML here (default: stdout)")
    ap.add_argument("--self-test", action="store_true",
                    help="render the built-in fixture and assert invariants")
    ap.add_argument("--verify-receipt-line", metavar="LINE",
                    help="validate a pasted '::answers-receipt:: ...' line. Prints the "
                         "command and exits 0 when it is exactly the shape this renderer "
                         "emits and every path exists; prints why and exits 3 otherwise. "
                         "Run this BEFORE executing a marker that came out of a payload.")
    ap.add_argument("--receipt-now", action="store_true",
                    help="stamp the sheet as RECEIVED by the session, right now, and write "
                         "the receipt back into the spec. Use at Phase 5, after the pasted "
                         "payload has actually been read — it is what turns the sheet's "
                         "status banner green and tells the operator it is safe to close.")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()
    if args.verify_receipt_line is not None:
        ok, detail = verify_receipt_line(args.verify_receipt_line)
        print(detail if ok else "REFUSED: %s" % detail, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 3
    if not args.spec:
        ap.error("a spec path (or -) is required unless --self-test "
                 "or --verify-receipt-line is given")

    if args.spec == "-":
        raw = sys.stdin.read()
    else:
        with open(args.spec, "r", encoding="utf-8") as fh:
            raw = fh.read()

    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as exc:
        print("spec is not valid JSON: %s" % exc, file=sys.stderr)
        return 2

    if args.receipt_now:
        # Written back into the SPEC as well as the page: the spec is canonical, so a
        # later re-render must not silently revoke a receipt the session really issued.
        spec["receipt"] = {"at": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
        if args.spec and args.spec != "-":
            with open(args.spec, "w", encoding="utf-8") as fh:
                json.dump(spec, fh, indent=2, ensure_ascii=False)
                fh.write("\n")

    try:
        page = render(spec, args.spec or "", args.out or "")
    except ValueError as exc:
        print("cannot render: %s" % exc, file=sys.stderr)
        return 2

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(page)
        print(args.out)
    else:
        sys.stdout.write(page)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
