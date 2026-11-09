#!/usr/bin/env python3
"""md-to-html.py — convert a Markdown file to the HTML subset /docs' template speaks.

Why this exists (BUG-2): `doc-new.sh` only ever *scaffolded* — it emitted a
TODO skeleton and left the body to the model. There was no path at all from
"here is a .md file" to "here is the HTML deliverable", so every markdown-to-doc
request became hand-authored HTML (slow, and inconsistent between runs).

Scope is deliberately narrow: emit exactly the tags the bundled template, the
`doc-audit.py` structural rules, and `validate-ascii-diagrams.py` already
understand — headings with stable id slugs, paragraphs, lists, tables,
blockquotes, code blocks (`<pre class="ascii">` for box-drawing diagrams), and
the inline set. Nothing else. This is not a general-purpose Markdown engine.

OPS-04: pure stdlib (no `markdown`, no `mistune`) so it runs on the git-bash /
WSL Windows boxes that never get to `pip install`.

Termination safety (the reason the block loop looks the way it does): every
iteration of the block scanner records the index it started on and force-advances
if no branch consumed a line. A block-level branch that fails to consume its own
input can therefore only produce *wrong* output, never a hang. Do not "simplify"
that guard away.

Usage:
    python3 md-to-html.py --emit body <file.md>
    python3 md-to-html.py --emit toc  <file.md>
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

# Box-drawing characters that mark a code fence as an ASCII diagram — the only
# form validate-ascii-diagrams.py recognizes (it scans <pre class="ascii">).
_BOX_CHARS = set("┌┐└┘│─├┤┬┴┼╔╗╚╝║═╠╣╦╩╬▲▼◄►")

_FENCE_RE = re.compile(r'^(?P<fence>```+|~~~+)\s*(?P<info>[^`]*)$')
_ATX_RE = re.compile(r'^(?P<hashes>#{1,6})\s+(?P<text>.*?)\s*#*\s*$')
_UL_RE = re.compile(r'^(?P<indent>[ \t]*)(?P<bullet>[-*+])\s+(?P<text>.*)$')
_OL_RE = re.compile(r'^(?P<indent>[ \t]*)(?P<num>\d+)[.)]\s+(?P<text>.*)$')
_HR_RE = re.compile(r'^[ \t]*(?:-{3,}|\*{3,}|_{3,})[ \t]*$')
_QUOTE_RE = re.compile(r'^[ \t]*>\s?(?P<text>.*)$')
_TABLE_DELIM_RE = re.compile(r'^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(\|[ \t]*:?-{2,}:?[ \t]*)*\|?[ \t]*$')


# ─────────────────────────── inline ───────────────────────────

def _slug(text: str, seen: dict[str, int]) -> str:
    """Stable, readable id slug. Deduped with a -2/-3 suffix so two sections
    named the same never collide (a duplicate id silently breaks TOC anchors)."""
    base = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'section'
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}-{seen[base]}"


def _inline(text: str) -> str:
    """Escape first, then re-introduce ONLY the inline markup we support.

    Order matters: code spans are extracted before every other rule so that
    `**not bold**` inside backticks survives verbatim, and links are resolved
    before emphasis so a URL containing underscores is not italicized.
    """
    # 1. Pull code spans out to placeholders so nothing else rewrites them.
    spans: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        spans.append(html.escape(m.group(1)))
        return f"\x00CODE{len(spans) - 1}\x00"

    text = re.sub(r'`([^`]+)`', _stash, text)

    # 2. Everything else is escaped exactly once.
    text = html.escape(text)

    # 3. Links: [label](url). The url is escaped already; reject anything that
    #    is not http(s)/mailto/relative so an escaped javascript: cannot ride in.
    def _link(m: re.Match[str]) -> str:
        label, url = m.group(1), m.group(2)
        if re.match(r'(?i)^\s*(javascript|data|vbscript):', html.unescape(url)):
            return label
        return f'<a href="{url}">{label}</a>'

    text = re.sub(r'\[([^\]]*)\]\(([^)\s]+)\)', _link, text)

    # 4. Emphasis. Bold before italic so ** is never eaten as two singles.
    text = re.sub(r'\*\*(?=\S)(.+?)(?<=\S)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__(?=\S)(.+?)(?<=\S)__', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(?=\S)([^*]+?)(?<=\S)\*', r'<em>\1</em>', text)
    text = re.sub(r'(?<![A-Za-z0-9_])_(?=\S)([^_]+?)(?<=\S)_(?![A-Za-z0-9_])', r'<em>\1</em>', text)

    # 5. Restore code spans.
    for i, span in enumerate(spans):
        text = text.replace(f"\x00CODE{i}\x00", f"<code>{span}</code>")
    return text


# ─────────────────────────── block helpers ───────────────────────────

def _is_block_start(line: str) -> bool:
    """True when `line` begins a NON-paragraph block.

    This is the predicate the paragraph branch uses to decide where to stop.
    It deliberately does NOT treat `**bold**`, `_em_` or any inline construct
    as a block start — a paragraph opening with bold text is still a paragraph.
    Getting this wrong is what makes a paragraph branch consume zero lines.
    """
    if not line.strip():
        return True
    return bool(
        _FENCE_RE.match(line)
        or _ATX_RE.match(line)
        or _HR_RE.match(line)
        or _QUOTE_RE.match(line)
        or _UL_RE.match(line)
        or _OL_RE.match(line)
    )


def _table_at(lines: list[str], i: int) -> bool:
    return (
        i + 1 < len(lines)
        and '|' in lines[i]
        and _TABLE_DELIM_RE.match(lines[i + 1]) is not None
    )


def _split_row(row: str) -> list[str]:
    row = row.strip()
    if row.startswith('|'):
        row = row[1:]
    if row.endswith('|'):
        row = row[:-1]
    return [c.strip() for c in row.split('|')]


def _list_items(lines: list[str], i: int, pattern: re.Pattern[str]) -> tuple[list[str], int]:
    """Consume consecutive items of one list. Returns (items, next_index).

    Guaranteed to consume at least the line at `i` (the caller only enters when
    `pattern` already matched there), so it can never return `i` unchanged.
    """
    items: list[str] = []
    while i < len(lines):
        m = pattern.match(lines[i])
        if not m:
            # A lazy continuation line (indented, not a new item, not blank)
            # belongs to the item we just added.
            if items and lines[i].strip() and lines[i][:1] in (' ', '\t'):
                items[-1] += ' ' + lines[i].strip()
                i += 1
                continue
            break
        items.append(m.group('text').strip())
        i += 1
    return items, i


def _heading_levels(lines: list[str]) -> list[int]:
    """ATX heading levels that are NOT inside a fenced code block, in order."""
    levels: list[int] = []
    fence: str | None = None
    for line in lines:
        fm = _FENCE_RE.match(line)
        if fence is not None:
            if line.startswith(fence):
                fence = None
            continue
        if fm:
            fence = fm.group('fence')[0] * 3
            continue
        hm = _ATX_RE.match(line)
        if hm:
            levels.append(len(hm.group('hashes')))
    return levels


# ─────────────────────────── the block scanner ───────────────────────────

def convert(md: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (body_html, [(id, heading_text), ...]) for top-level headings."""
    lines = md.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    out: list[str] = []
    toc: list[tuple[str, str]] = []
    seen_slugs: dict[str, int] = {}

    # Normalize heading depth: whatever the shallowest heading in the file is
    # becomes <h2>, since the template already supplies the document <h1>.
    #
    # This pre-scan MUST skip fenced code — shell snippets are full of `# comment`
    # lines, and counting those as headings makes every real `##` section demote
    # to <h3> and empties the TOC (the TOC is built from h2s).
    levels = _heading_levels(lines)
    base_level = min(levels) if levels else 1

    # A lone top-level heading at the very start is the document TITLE — the
    # template already renders it in the header, so drop it and rebase on the
    # next level down. Without this, every `##` section demotes to <h3> and the
    # TOC (built from h2s) contains nothing but the title.
    drop_title = False
    if levels and levels.count(base_level) == 1 and levels[0] == base_level:
        deeper = [lv for lv in levels if lv > base_level]
        if deeper:
            drop_title = True
            base_level = min(deeper)

    i = 0
    while i < len(lines):
        start = i  # ── progress sentinel: see module docstring ──
        line = lines[i]

        # blank
        if not line.strip():
            i += 1

        # fenced code
        elif _FENCE_RE.match(line):
            m = _FENCE_RE.match(line)
            assert m is not None
            fence, info = m.group('fence')[0] * 3, m.group('info').strip().lower()
            i += 1
            buf: list[str] = []
            while i < len(lines) and not lines[i].startswith(fence):
                buf.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1  # consume the closing fence
            content = '\n'.join(buf)
            is_ascii = info == 'ascii' or any(ch in _BOX_CHARS for ch in content)
            if is_ascii:
                out.append(f'<pre class="ascii">{html.escape(content)}</pre>')
            elif info == 'mermaid':
                # The template ships mermaid v10 and initialises `.mermaid` DIVS. A
                # ```mermaid fence left as <pre><code> renders the diagram's SOURCE on
                # the page, and every validator passes, because none of them asks
                # whether a declared diagram drew. Found 2026-09-19 in
                # cowork-aistudio-port-plan.html. Content stays escaped: mermaid reads
                # textContent, so the browser hands it back unescaped, and raw markup in
                # a .md body still cannot reach the document.
                out.append(f'<div class="mermaid">{html.escape(content)}</div>')
            else:
                cls = f' class="language-{html.escape(info)}"' if info else ''
                out.append(f'<pre><code{cls}>{html.escape(content)}</code></pre>')

        # heading
        elif _ATX_RE.match(line):
            m = _ATX_RE.match(line)
            assert m is not None
            raw_level = len(m.group('hashes'))
            if drop_title and raw_level < base_level:
                i += 1          # the document title — the template renders it
                continue        # (loop guard not needed: i advanced)
            depth = raw_level - base_level + 2   # shallowest → h2
            depth = max(2, min(6, depth))
            text = m.group('text').strip()
            hid = _slug(text, seen_slugs)
            out.append(f'<h{depth} id="{hid}">{_inline(text)}</h{depth}>')
            if depth == 2:
                toc.append((hid, text))
            i += 1

        # horizontal rule (checked before lists: `---` also matches nothing else here)
        elif _HR_RE.match(line):
            out.append('<hr>')
            i += 1

        # table
        elif _table_at(lines, i):
            header = _split_row(lines[i])
            i += 2  # header + delimiter
            body_rows: list[list[str]] = []
            while i < len(lines) and '|' in lines[i] and lines[i].strip():
                body_rows.append(_split_row(lines[i]))
                i += 1
            head_html = ''.join(f'<th>{_inline(c)}</th>' for c in header)
            rows_html = ''.join(
                '<tr>' + ''.join(f'<td>{_inline(c)}</td>' for c in r) + '</tr>'
                for r in body_rows
            )
            out.append(
                '<table>\n  <thead>\n    <tr>' + head_html + '</tr>\n  </thead>\n'
                '  <tbody>\n    ' + rows_html + '\n  </tbody>\n</table>'
            )

        # blockquote
        elif _QUOTE_RE.match(line):
            buf = []
            while i < len(lines):
                qm = _QUOTE_RE.match(lines[i])
                if not qm:
                    break
                buf.append(qm.group('text'))
                i += 1
            inner = ' '.join(t.strip() for t in buf if t.strip())
            out.append(f'<blockquote><p>{_inline(inner)}</p></blockquote>')

        # unordered list
        elif _UL_RE.match(line):
            items, i = _list_items(lines, i, _UL_RE)
            out.append('<ul>\n' + '\n'.join(f'  <li>{_inline(t)}</li>' for t in items) + '\n</ul>')

        # ordered list
        elif _OL_RE.match(line):
            items, i = _list_items(lines, i, _OL_RE)
            out.append('<ol>\n' + '\n'.join(f'  <li>{_inline(t)}</li>' for t in items) + '\n</ol>')

        # paragraph — the catch-all. Consumes until a blank line or the start of
        # another block. Because `_is_block_start` returns False for inline
        # markup (**bold**, _em_, `code`, [links]), a paragraph that opens with
        # any of those still consumes its own first line.
        else:
            buf = [line]
            i += 1
            while i < len(lines) and not _is_block_start(lines[i]) and not _table_at(lines, i):
                buf.append(lines[i])
                i += 1
            out.append(f'<p>{_inline(" ".join(s.strip() for s in buf))}</p>')

        # ── unconditional progress guard ──
        # If any branch above failed to consume input, force-advance rather than
        # spin. Wrong output is recoverable; a hung skill is not.
        if i == start:
            i += 1

    return '\n\n'.join(out), toc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', help='path to the .md file')
    ap.add_argument('--emit', choices=('body', 'toc'), default='body',
                    help="'body' = the HTML fragment; 'toc' = <a href=#id> links for its h2s")
    args = ap.parse_args()

    src = Path(args.source)
    if not src.is_file():
        print(f"ERR: not a file: {src}", file=sys.stderr)
        return 1

    body, toc = convert(src.read_text(encoding='utf-8'))
    if args.emit == 'toc':
        print(' '.join(f'<a href="#{hid}">{html.escape(text)}</a>' for hid, text in toc))
    else:
        print(body)
    return 0


if __name__ == '__main__':
    sys.exit(main())
