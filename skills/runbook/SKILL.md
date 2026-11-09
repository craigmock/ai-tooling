---
name: runbook
description: Write, upgrade or check an operator runbook to a fixed section contract (trigger, scope, authority, prerequisites, steps with expected result and on-fail, point of no return, rollback, verification, comms, escalation, review dates). Use for "write a runbook", "make this procedure a runbook", "audit this runbook".
---

# /runbook

> Paths below use `${CLAUDE_SKILL_DIR}`, this skill's own folder. If your assistant does not set it (Codex does not), use the folder this SKILL.md was loaded from instead. In Codex, call the skill as `$runbook`.

A runbook is a procedure someone can follow at 3 a.m. without asking the author. This skill scaffolds one in the
organization's theme and then checks it against a contract so a runbook cannot pass with no steps in it.

## Step 0: organization config

```bash
python3 "${CLAUDE_SKILL_DIR}/../../lib/aitooling.py" ensure
```

Exit 0: continue. Exit 10: follow `lib/WIZARD.md`, then run `ensure` again.

## Steps

1. Gather facts from the real system: configuration files, scripts, the commands actually used. Never invent a
   command; if you cannot verify one, write `TODO: verify` in its place.
2. Scaffold:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/../docs/scripts/doc-new.py" "Restore the database" --kind runbook
   ```

   The file lands in the configured runbooks folder with the runbook skeleton already injected.
3. Fill every section of the skeleton from step 1. Each step needs a command, the expected result and what to
   do on failure.
4. Validate until it exits 0:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/validate-runbook.py" PATH.html
   python3 "${CLAUDE_SKILL_DIR}/scripts/validate-runbook.py" contract   # print the contract
   ```

5. Run the secrets scan from `/docs` on the finished file, and report both results.

## Rules

- Access sections name the role, user or environment-variable name, never the secret value.
- A step that changes state names its rollback. A step with no rollback is marked as a point of no return.
- Do not mark the runbook reviewed; the review date is the person's to set.
