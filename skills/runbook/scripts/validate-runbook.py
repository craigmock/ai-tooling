#!/usr/bin/env python3
"""
Enforce the RUNBOOK SECTION CONTRACT on runbook deliverables.

WHY THIS EXISTS
A runbook kind was checked against published
practice (ISO/IEC 27001:2022 A.5.37 documented operating procedures, NIST SP 800-53r5
CP-2/CP-4/CM-3/CM-4/IR-8/SA-5, SP 800-34r1, SP 800-61r3, CIS Controls v8.1 11 and 17,
Google SRE playbooks). An earlier version of this toolchain required diagrams of a runbook and nothing
of its procedure: the words "rollback", "escalation" and "verification" appeared zero
times across the doc tooling. A runbook could pass every gate with no
steps in it. This validator is the missing half. Run it alongside any diagram validator you use.

THE CONTRACT (single source; `validate-runbook.py contract` prints it)
Every section is a <section data-runbook="KIND"> element. Declaring a kind is not
covering it: each is probed for the shape it claims, because a marker nothing verifies
is how four gates in this toolchain came to pass documents with no diagrams at all.

Exit: 0 all files pass (warnings allowed), 1 at least one file fails, 2 usage error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

# kind -> (what it must show, source it answers to, may it be declared not-applicable)
CONTRACT: dict[str, tuple[str, str, bool]] = {
    "trigger": ("the alert, symptom, schedule or request that sends a reader here, and when NOT to use it",
                "Google SRE: every alert links to a playbook", False),
    "scope": ("the systems, hosts and software versions this applies to", "NIST SP 800-53 SA-5", False),
    "authority": ("who may run it, the access it needs, and who approves it", "NIST SP 800-34 roles; 800-53 CP-2", False),
    "prerequisites": ("a list of access, tools and inputs to have before step 1", "ISO 27001 A.5.37", False),
    "backup": ("the snapshot, export or copy taken before anything changes, with its command",
               "NIST SP 800-34 recovery; CIS 11", True),
    "procedure": ("numbered steps, each with the exact action, the expected result and what to do if it fails",
                  "ISO 27001 A.5.37", False),
    "point-of-no-return": ("the step after which rollback no longer restores the old state", "NIST SP 800-53 CM-3", True),
    "rollback": ("how to put it back, as steps or commands, and the condition that triggers it", "NIST SP 800-53 CM-3", True),
    "verification": ("checks that prove the state CHANGED, not that a command exited 0", "NIST SP 800-53 CM-3(2)", False),
    "comms": ("who is told, before and after, and how", "NIST SP 800-61r3; 800-34 notification", True),
    "escalation": ("a table: situation, contact, method", "NIST SP 800-61r3; 800-53 IR-8", False),
    "review": ("data-last-tested (date or never) and data-next-review (date, at most 13 months out)",
               "CIS v8.1 establish-and-maintain; 800-53 CP-4", False),
    "gaps": ("every value nobody collected, one list item each; 'None.' if there are none",
             "house rule: unknowns are drawn as gaps, never guessed", False),
}
NA_MIN = 15          # characters of reason a not-applicable declaration must carry
TEXT_MIN = 30        # characters of body text a section must carry beyond its heading
REVIEW_MAX_DAYS = 400
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Node:
    __slots__ = ("tag", "attrs", "children", "text", "parent")

    def __init__(self, tag: str, attrs: dict[str, str], parent: "Node | None"):
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children: list[Node] = []
        self.text: list[str] = []

    def classes(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def all_text(self, skip_headings: bool = False) -> str:
        parts: list[str] = []

        def rec(n: Node):
            if skip_headings and re.fullmatch(r"h[1-6]", n.tag):
                return
            parts.extend(n.text)
            for c in n.children:
                rec(c)
        rec(self)
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    def find(self, pred) -> list["Node"]:
        return [n for n in self.walk() if n is not self and pred(n)]


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, {k: (v or "") for k, v in attrs}, self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, {k: (v or "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.text.append(data)


def has_action(n: Node) -> bool:
    return bool(n.find(lambda x: x.tag in ("pre", "code") or "rb-action" in x.classes()))


def probe(kind: str, sec: Node, doc: Node, today: dt.date) -> tuple[list[str], list[str]]:
    fails: list[str] = []
    warns: list[str] = []
    na = sec.attrs.get("data-na")
    if na is not None:
        if not CONTRACT[kind][2]:
            return [f"{kind}: cannot be declared not-applicable"], warns
        if len(na.strip()) < NA_MIN:
            return [f"{kind}: data-na needs a reason of at least {NA_MIN} characters"], warns
        return fails, warns
    body = sec.all_text(skip_headings=True)
    if re.search(r"\bTODO\b", sec.all_text()) or any(
            "TODO" in v for n in sec.walk() for k, v in n.attrs.items() if k.startswith("data-")):
        fails.append(f"{kind}: unfilled TODO from the scaffold")
    if len(body) < TEXT_MIN:
        fails.append(f"{kind}: {len(body)} characters of content; a heading is not a section")

    if kind == "prerequisites" and not sec.find(lambda x: x.tag == "li"):
        fails.append("prerequisites: no list items")

    if kind == "procedure":
        steps = sec.find(lambda x: "rb-step" in x.classes())
        if not steps:
            fails.append('procedure: no class="rb-step" elements')
        for i, s in enumerate(steps, 1):
            label = s.attrs.get("id") or f"step {i}"
            if not has_action(s):
                fails.append(f'procedure: {label} has no exact action (<pre>, <code> or class="rb-action")')
            for need in ("rb-expect", "rb-onfail"):
                hits = s.find(lambda x, c=need: c in x.classes())
                if not hits or not any(len(h.all_text()) >= 8 for h in hits):
                    fails.append(f"procedure: {label} has no {need} text")

    if kind in ("rollback", "verification") and not (has_action(sec) or sec.find(lambda x: "rb-step" in x.classes())):
        fails.append(f"{kind}: no command or step; prose alone cannot be followed at 3am")

    if kind == "escalation":
        rows = sec.find(lambda x: x.tag == "tr")
        if len(rows) < 2:
            fails.append("escalation: needs a table with a header row and at least one contact row")

    if kind == "review":
        lt, nr = sec.attrs.get("data-last-tested", "").strip(), sec.attrs.get("data-next-review", "").strip()
        if lt != "never" and not _DATE.match(lt):
            fails.append('review: data-last-tested must be YYYY-MM-DD or "never"')
        elif lt == "never":
            warns.append("review: never tested (CIS 17.7 / 800-53 CP-4 expect an exercise)")
        if not _DATE.match(nr):
            fails.append("review: data-next-review must be YYYY-MM-DD")
        else:
            due = dt.date.fromisoformat(nr)
            if due < today:
                fails.append(f"review: OVERDUE since {nr}; review it, then move the date")
            elif (due - today).days > REVIEW_MAX_DAYS:
                fails.append(f"review: next review {nr} is more than {REVIEW_MAX_DAYS} days out")

    if kind == "gaps":
        items = sec.find(lambda x: x.tag == "li")
        marked = doc.find(lambda x: "rb-gap" in x.classes())
        if not items and "none" not in body.lower():
            fails.append('gaps: list each unknown as an <li>, or say "None."')
        if len(marked) > len(items):
            fails.append(f'gaps: {len(marked)} class="rb-gap" markers in the body but {len(items)} listed')
    return fails, warns


def check(path: Path, today: dt.date) -> dict:
    html = path.read_text(encoding="utf-8", errors="replace")
    res: dict = {"file": str(path), "fail": [], "warn": []}
    m = re.search(r'data-doc-kind\s*=\s*"([^"]+)"', html)
    if not m or m.group(1).strip().lower() != "runbook":
        if "runbook" not in path.name.lower():
            res["skipped"] = 'not a runbook (no data-doc-kind="runbook", no "runbook" in the name)'
            return res
        res["fail"].append('<html> lacks data-doc-kind="runbook"')
    t = Tree()
    t.feed(html)
    secs: dict[str, list[Node]] = {}
    for n in t.root.walk():
        k = n.attrs.get("data-runbook")
        if k is not None:
            secs.setdefault(k.strip(), []).append(n)
    for k in secs:
        if k not in CONTRACT:
            res["fail"].append(f'unknown data-runbook="{k}"')
    for kind in CONTRACT:
        if kind not in secs:
            res["fail"].append(f"{kind}: missing ({CONTRACT[kind][0]})")
            continue
        for sec in secs[kind]:
            f, w = probe(kind, sec, t.root, today)
            res["fail"] += f
            res["warn"] += w
    irrev = t.root.find(lambda x: "data-irreversible" in x.attrs)
    if irrev:
        for kind in ("point-of-no-return", "backup"):
            if any("data-na" in s.attrs for s in secs.get(kind, [])):
                res["fail"].append(f"{kind}: declared not-applicable but a step is data-irreversible")
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="Enforce the runbook section contract.")
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--today", help="YYYY-MM-DD, for tests")
    a = ap.parse_args()
    if a.files and a.files[0].name == "contract":
        for k, (what, src, na) in CONTRACT.items():
            print(f'{k:20} {"(may be data-na)" if na else "":17} {what}  [{src}]')
        return 0
    if not a.files:
        ap.print_usage(sys.stderr)
        return 2
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    results = [check(f, today) for f in a.files]
    if a.json:
        print(json.dumps(results, indent=1))
    else:
        for r in results:
            if "skipped" in r:
                print(f"SKIP {r['file']}: {r['skipped']}")
                continue
            print(f"{'FAIL' if r['fail'] else 'PASS'} {r['file']}")
            for x in r["fail"]:
                print(f"  - {x}")
            for x in r["warn"]:
                print(f"  ~ {x}")
    return 1 if any(r["fail"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
