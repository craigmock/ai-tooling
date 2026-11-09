---
name: loose-ends
description: Sweep the current session for loose ends before moving on - unfinished work, promised follow-ups, uncommitted or unpushed changes, failing checks, and questions that were asked but never answered - then put the decisions in front of the person as question cards or an answer sheet. Use for "loose ends", "what's still open", "anything unfinished", "what did I not answer".
---

# /loose-ends

## Step 0: organization config

```bash
python3 "${CLAUDE_SKILL_DIR}/../../lib/aitooling.py" ensure
```

Exit 0: continue. Exit 10: follow `lib/WIZARD.md`, then run `ensure` again.

## Steps

1. Collect the facts; do not guess:
   - `python3 "${CLAUDE_SKILL_DIR}/../eos/scripts/eos-wrapup.py" context` for uncommitted paths, unpushed commits
     and recent commits.
   - The conversation: things started but not finished, follow-ups you promised, questions you asked that got
     no answer, checks that failed.
2. Write the list of loose ends as short items, each with its evidence (a path, a commit, a message).
3. Turn every open decision into a question with one to three real options. Put them in a spec file:

   ```json
   {"title": "Open decisions", "groups": [{"title": "Release", "questions": [
     {"title": "Ship now or wait for review?", "context": "Tests pass; review pending.",
      "options": [{"label": "Ship now", "recommended": true}, {"label": "Wait"}]}]}]}
   ```

4. Add the research-first option to every question (the script enforces the rules and is safe to re-run):

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/loose-ends-spec.py" SPEC.json
   ```

5. Two or more questions: ask them as question cards in the same turn if your tool has cards (up to four per
   call), otherwise render the answer sheet with `/answers`. One question: ask it inline.
6. Report the loose ends and what was decided. Do not commit, push or delete anything because of an answer
   without saying so first.

## Rules

- A loose end needs evidence. "Maybe the tests are flaky" is not one.
- Never end the reply with a numbered list of questions; use cards or a sheet.
