---
name: eos
description: End-of-session wrap-up. Summarize what was done, show anything uncommitted or unpushed, append a worklog entry, and record the work through the organization's tracking backend (none, a local log file, or a webhook). Use for "wrap up", "end of session", "log my time", "we're done".
---

# /eos

## Step 0: organization config

```bash
python3 "${CLAUDE_SKILL_DIR}/../../lib/aitooling.py" ensure
```

Exit 0: continue. Exit 10: this is the first run. Follow `lib/WIZARD.md`: ask the printed questions (including
which tracking backend to use), run `init`, then run `ensure` again before going on.

## Steps

1. **Context.** Show what is unsaved:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/eos-wrapup.py" context
   ```

   Report uncommitted paths and unpushed commits plainly. Commit or push only if the person says to; this skill
   never does it on its own.
2. **Summary.** Write two to five sentences of what was done this session, in plain language, naming files and
   commits. Say what was changed and what was only proposed; never describe a change that went out as a
   suggestion.
3. **Minutes.** Ask the person how long the session took, or estimate from timestamps and say it is an estimate.
   Do not invent a number.
4. **Record.**

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/eos-wrapup.py" record --summary "TEXT" --minutes N --ref "TICKET-OR-NOTE"
   ```

   This appends to the monthly worklog in the configured folder and calls the tracking backend:

   | Backend | Effect |
   |---------|--------|
   | `none` | Worklog entry only |
   | `file` | Also appends one JSON line to the configured log file |
   | `webhook` | Also POSTs the same JSON to the configured https URL |

   If the webhook fails, say so and give the JSON line so nothing is lost.
5. **Report.** State what was written (paths, time), whether the tracking call succeeded, and what remains
   unsaved.

## Rules

- Never claim something is committed, pushed or logged without having run the command and seen it succeed.
- The summary and worklog may be shared; do not put secrets, tokens or private URLs in them.
