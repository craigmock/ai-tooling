#!/usr/bin/env python3
"""Finish a /loose-ends spec so every question carries the research-first option.

/loose-ends hands its questions to the /answers renderer (sheet) or to
AskUserQuestion (cards). Both need the same extra choice on every question:
"explain this properly and research it before I decide". Writing that option by
hand into each question is the step that gets forgotten on question 7 of 9, so
this script appends it and refuses a spec it cannot make valid.

Rules it enforces:
  * at most 3 authored options per question. Cards hold 4 options, and the
    research option takes one of them. More than 3 means the question is really
    two questions; split it.
  * at least 1 authored option (the research option is not a decision).
  * an authored option may not already be the research option (idempotent re-run
    strips and re-appends it, so it is always last and always identical).
  * no authored "Other" option: both the sheet and the cards add free text.

Usage:
  loose-ends-spec.py SPEC.json [--out PATH]   # default: rewrite SPEC in place
  loose-ends-spec.py --self-test

Exit codes: 0 written, 2 the spec has problems (each one printed), 1 bad usage.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RESEARCH_LABEL = "Explain more + research first"
RESEARCH_DETAIL = (
    "Not ready to decide. Give me the full explanation, research it (code, docs, "
    "web if needed), then ask again with a recommendation."
)
MAX_AUTHORED = 3


def _is_research(opt: dict) -> bool:
    return str(opt.get("label", "")).strip().lower() == RESEARCH_LABEL.lower()


def finish(spec: dict) -> list[str]:
    """Append the research option to every question. Returns problems; empty = ok."""
    problems = []
    qnum = 0
    for group in spec.get("groups") or []:
        for q in group.get("questions") or []:
            qnum += 1
            where = "Q%d %r" % (qnum, str(q.get("title", ""))[:60])
            opts = [o for o in (q.get("options") or []) if not _is_research(o)]
            if not opts:
                problems.append("%s has no authored options." % where)
            if len(opts) > MAX_AUTHORED:
                problems.append(
                    "%s has %d authored options; the cap is %d because the research "
                    "option takes the fourth card slot. Split the question."
                    % (where, len(opts), MAX_AUTHORED))
            if any(str(o.get("label", "")).strip().lower().startswith("other") for o in opts):
                problems.append("%s authors an Other option; the renderer and the "
                                "cards add free text themselves." % where)
            opts.append({"label": RESEARCH_LABEL, "detail": RESEARCH_DETAIL})
            q["options"] = opts
    if qnum == 0:
        problems.append("spec has no questions. If nothing is open, say so and do not render.")
    return problems


def _self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name)
        ok = ok and cond

    spec = {"groups": [{"questions": [
        {"title": "A", "options": [{"label": "x", "recommended": True}, {"label": "y"}]},
    ]}]}
    check("clean spec has no problems", finish(spec) == [])
    opts = spec["groups"][0]["questions"][0]["options"]
    check("research option appended last", _is_research(opts[-1]) and len(opts) == 3)
    finish(spec)
    check("re-run is idempotent", len(spec["groups"][0]["questions"][0]["options"]) == 3)

    four = {"groups": [{"questions": [{"title": "B", "options": [{"label": str(i)} for i in range(4)]}]}]}
    check("4 authored options refused", any("cap is 3" in p for p in finish(four)))

    other = {"groups": [{"questions": [{"title": "C", "options": [{"label": "Other: type it"}]}]}]}
    check("authored Other refused", any("Other" in p for p in finish(other)))

    empty_q = {"groups": [{"questions": [{"title": "D", "options": []}]}]}
    check("question with no options refused", any("no authored" in p for p in finish(empty_q)))

    check("empty spec refused", any("no questions" in p for p in finish({"groups": []})))
    print("self-test %s" % ("passed" if ok else "FAILED"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return _self_test()
    if not a.spec:
        ap.print_usage(sys.stderr)
        return 1
    src = Path(a.spec)
    spec = json.loads(src.read_text(encoding="utf-8"))
    problems = finish(spec)
    if problems:
        print("spec has %d problem(s):" % len(problems), file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return 2
    out = Path(a.out) if a.out else src
    out.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
