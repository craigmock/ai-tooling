---
name: nrp
description: Next resume prompt. Find the resume prompt a previous session left in this repository (across every worktree), re-check its claims against git before trusting it, or write a new one that replaces the old. Use for "what am I resuming", "resume prompt", "where did I leave off", "next session prompt".
---

# /nrp

> Paths below use `${CLAUDE_SKILL_DIR}`, this skill's own folder. If your assistant does not set it (Codex does not), use the folder this SKILL.md was loaded from instead. In Codex, call the skill as `$nrp`.

## Step 0: organization config

```bash
python3 "${CLAUDE_SKILL_DIR}/../../lib/aitooling.py" ensure
```

Exit 0: continue. Exit 10: follow `lib/WIZARD.md`, then run `ensure` again.

## Find and check

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/nrp.py" find
python3 "${CLAUDE_SKILL_DIR}/scripts/nrp.py" check PATH/NEXT-SESSION-PROMPT.md
```

`find` lists prompts newest first with branch and age. `check` reports whether each commit the prompt names still
exists and whether the tree is clean. Treat the prompt as a claim about the past; anything `check` flags is
re-verified by hand before you act on it.

## Write a new one

Write `NEXT-SESSION-PROMPT.md` at the repository root. Replace the old file; do not append to it.

1. **State** - branch, last commit (full hash), whether the tree is clean, and the time you checked, in UTC.
2. **Done** - what is finished, one line each, with the commit that proves it.
3. **Next** - the next concrete step and the command that starts it.
4. **Waiting on the person** - decisions only they can make, as a short list. Keep this separate from "Next".
5. **Do not redo** - settled decisions and the reason, so the next session does not reopen them.

Every fact carries its source (a command output, a file, a commit). Do not write a fact you did not check in this
session.

Add the file to `.gitignore` if the team does not want it committed.
