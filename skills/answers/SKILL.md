---
name: answers
description: Turn a pile of open decisions into an interactive HTML answer sheet in the organization's theme. Each question is numbered, has a recommended default and an Other box; the person picks, presses Copy, and pastes the numbered result back. Use for "answer sheet", "let me answer these", "give me the questions", "what do you still need from me".
---

# /answers

## Step 0: organization config

```bash
python3 "${CLAUDE_SKILL_DIR}/../../lib/aitooling.py" ensure
```

Exit 0: continue. Exit 10: follow `lib/WIZARD.md`, then run `ensure` again. The sheet uses the configured theme
colors; with no config it falls back to a built-in dark palette.

## Steps

1. Collect every unanswered question from the session. Group related ones. Every question needs a title, short
   context, and at least one option; mark the one you recommend.
2. Write a spec file (see the shape at the top of `scripts/answers-render.py`, or run it with `--self-test` to
   see a full example):

   ```json
   {"title": "Decisions", "groups": [{"title": "Release", "questions": [
     {"title": "Ship now?", "context": "Tests pass; one review is still open.",
      "options": [{"label": "Yes", "recommended": true}, {"label": "No"}]}]}]}
   ```

   Each question needs context and exactly one recommended option (or `"unauthored": true` when nobody has a
   position yet); the renderer refuses a spec that breaks either rule.

3. Render and open it:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/answers-render.py" SPEC.json --out sheet.html
   ```

4. Tell the person the path and ask them to paste the copied result back. Read the numbered answers back to them
   before acting on anything that changes state.
5. When the pasted payload ends with a receipt marker, check it first with `--verify-receipt-line "LINE"`; run the
   command it prints only if it exits 0.

## Rules

- Every caller-supplied string is escaped by the renderer. Do not assemble the HTML yourself.
- Keep options to real choices. Free text is already provided by the Other box.
