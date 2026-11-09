#!/usr/bin/env bash
# tests/run-tests.sh - proves: the wizard writes a config, skills read it, bundled self-tests pass,
# and the leak scan is clean. Uses a throwaway HOME-independent config; never touches a real one.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
export PYTHONDONTWRITEBYTECODE=1
TB="${TMPDIR:-/tmp}"
T="$(mktemp -d "${TB%/}/ai-tooling-test.XXXXXX")"
export AI_TOOLING_CONFIG="$T/config.json"
LIB="$ROOT/lib/aitooling.py"

PASS=0; FAIL=0
pass(){ PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
fail(){ FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }
expect(){ if [ "$2" = "$3" ]; then pass "$1"; else fail "$1 (got '$2', want '$3')"; fi; }
has(){ case "$2" in *"$3"*) pass "$1";; *) fail "$1 (missing '$3')";; esac; }

printf '== ai-tooling tests == ROOT=%s\n' "$ROOT"

# 1. No config: ensure asks for the wizard and lists the questions.
OUT="$("$PY" "$LIB" ensure)"; RC=$?
expect "ensure without a config exits 10" "$RC" "10"
has "ensure prints the wizard questions" "$OUT" '"questions"'
has "ensure names the config path" "$OUT" "$T/config.json"

# 2. Invalid answers are refused and nothing is written.
"$PY" "$LIB" init --org-name "Example Corp" --short-name "Bad Name" --author-name "Alex Doe" >/dev/null 2>&1; RC=$?
expect "init refuses a bad short name" "$RC" "2"
test -e "$T/config.json" && fail "refused init wrote a file" || pass "refused init wrote nothing"
"$PY" "$LIB" init --org-name "Example Corp" --short-name example --author-name "Alex Doe" \
    --backend webhook --webhook-url "http://example.com/x" --docs-dir "$T/out/docs" >/dev/null 2>&1; RC=$?
expect "init refuses a non-https webhook" "$RC" "2"

# 3. The wizard (non-interactive form) writes the config.
"$PY" "$LIB" init --org-name "Example Corp" --short-name example --author-name "Alex Doe" \
    --author-email "alex@example.com" --preset slate --primary "#0a7d5a" --backend file \
    --docs-dir "$T/out/docs" --runbooks-dir "$T/out/runbooks" --worklog-dir "$T/out/worklog" \
    --sessions-dir "$T/out/sessions" --log-file "$T/out/worklog/events.jsonl" >/dev/null; RC=$?
expect "init writes the config" "$RC" "0"
test -s "$T/config.json" && pass "config file exists" || fail "config file missing"
"$PY" "$LIB" ensure >/dev/null; expect "ensure now exits 0" "$?" "0"
expect "org name round-trips" "$("$PY" "$LIB" get org.name)" "Example Corp"
expect "override beats preset" "$("$PY" "$LIB" get theme.primary)" "#0a7d5a"
expect "preset fills the rest" "$("$PY" "$LIB" get theme.background)" "#14181d"
"$PY" "$LIB" init --org-name "Other" --short-name other --author-name "Alex Doe" >/dev/null 2>&1
expect "init will not overwrite without --force" "$?" "1"

# 4. Skills read the config.
DOC="$("$PY" "$ROOT/skills/docs/scripts/doc-new.py" "Quarterly Report" | head -1)"
test -f "$DOC" && pass "/docs wrote a document" || fail "/docs wrote nothing"
D="$(<"$DOC")"
has "document carries the org name" "$D" "Example Corp"
has "document carries the author" "$D" "Alex Doe"
has "document carries the configured color" "$D" "#0a7d5a"
has "document uses the preset background" "$D" "#14181d"
case "$D" in *"{{"*) fail "document has unfilled placeholders";; *) pass "document has no unfilled placeholders";; esac

printf '# Heading\n\nSome **bold** text and a <script>alert(1)</script> tag.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n' > "$T/body.md"
"$PY" "$ROOT/skills/docs/scripts/doc-new.py" "From Markdown" --md "$T/body.md" >/dev/null; expect "/docs converts Markdown" "$?" "0"
M="$(<"$T/out/docs/from-markdown.html")"
has "markdown table becomes HTML" "$M" "<table"
case "$M" in *"<script>alert"*) fail "raw script tag survived";; *) pass "raw script tag is escaped";; esac

RB="$("$PY" "$ROOT/skills/docs/scripts/doc-new.py" "Restore Service" --kind runbook | head -1)"
case "$RB" in "$T"/out/runbooks/*) pass "/runbook scaffold lands in the runbooks folder";; *) fail "runbook path wrong: $RB";; esac
R="$(<"$RB")"
has "runbook skeleton injected" "$R" 'data-runbook="trigger"'
has "runbook keeps the org theme" "$R" "#0a7d5a"
"$PY" "$ROOT/skills/runbook/scripts/validate-runbook.py" "$RB" >/dev/null 2>&1
test $? -ne 0 && pass "validator rejects an unfilled runbook skeleton" || fail "validator passed an unfilled skeleton"

"$PY" "$ROOT/skills/docs/scripts/doc-secrets-scan.py" "$DOC" >/dev/null 2>&1; expect "secrets scan passes a clean doc" "$?" "0"

"$PY" "$ROOT/skills/answers/scripts/answers-render.py" --self-test >/dev/null 2>&1; expect "answers renderer self-test" "$?" "0"
printf '{"title":"T","groups":[{"title":"G","questions":[{"title":"Q","context":"Why this matters.","options":[{"label":"A","recommended":true}]}]}]}' > "$T/spec.json"
"$PY" "$ROOT/skills/loose-ends/scripts/loose-ends-spec.py" "$T/spec.json" >/dev/null; expect "loose-ends spec accepted" "$?" "0"
"$PY" "$ROOT/skills/answers/scripts/answers-render.py" "$T/spec.json" --out "$T/sheet.html" >/dev/null; expect "answer sheet rendered" "$?" "0"
has "answer sheet takes the configured color" "$(<"$T/sheet.html")" "--acc:#0a7d5a"

# 5. eos records through the configured backend (file).
"$PY" "$ROOT/skills/eos/scripts/eos-wrapup.py" record --summary "Wrote the quarterly report" --minutes 30 --ref NOTE-1 >/dev/null
expect "eos record succeeds" "$?" "0"
has "tracking log has the event" "$(<"$T/out/worklog/events.jsonl")" '"summary": "Wrote the quarterly report"'
test -n "$(ls "$T"/out/worklog/worklog-*.md 2>/dev/null)" && pass "worklog entry written" || fail "worklog entry missing"
"$PY" "$ROOT/skills/eos/scripts/eos-wrapup.py" context --repo "$ROOT" | "$PY" -c "import json,sys; json.load(sys.stdin)"
expect "eos context is valid JSON" "$?" "0"
"$PY" "$ROOT/skills/nrp/scripts/nrp.py" find --repo "$T" >/dev/null; expect "nrp reports nothing found with exit 1" "$?" "1"

# 6. A skill with the config absent falls back to the wizard instead of crashing.
AI_TOOLING_CONFIG="$T/none.json" "$PY" "$ROOT/skills/docs/scripts/doc-new.py" "X" >/dev/null 2>&1
expect "doc-new without a config exits 10" "$?" "10"

# 7. Every skill folder has a SKILL.md with front matter and the config gate.
for d in "$ROOT"/skills/*/; do
  n="$(basename "$d")"
  head -1 "$d/SKILL.md" | grep -q '^---$' && grep -q "^name: $n$" "$d/SKILL.md" && pass "skill $n has front matter" || fail "skill $n front matter"
  [ "$n" = "setup" ] || { grep -q 'aitooling.py" ensure' "$d/SKILL.md" && pass "skill $n runs the config gate" || fail "skill $n lacks the config gate"; }
done

# 8. Leak scan (files and commit history when there is one).
"$PY" "$ROOT/tools/leak-scan.py" "$ROOT" --commits; expect "leak scan is clean" "$?" "0"

printf '== run-tests == PASS=%s FAIL=%s\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
