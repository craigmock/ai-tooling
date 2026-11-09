---
name: setup
description: Run or change the first-run setup for ai-tooling - organization name, author, brand theme, tracking backend and output folders. Use when the person says "set up", "change the theme", "change my organization", "reconfigure", or when another skill reports that no config exists.
---

# /setup

> Paths below use `${CLAUDE_SKILL_DIR}`, this skill's own folder. If your assistant does not set it (Codex does not), use the folder this SKILL.md was loaded from instead. In Codex, call the skill as `$setup`.

Creates or edits the one config file every ai-tooling skill reads. See `lib/WIZARD.md` for the full flow.

## Steps

1. Check the current state: `python3 "${CLAUDE_SKILL_DIR}/../../lib/aitooling.py" ensure`
   - Exit 0: a config exists. Show it with `... show` and ask what to change.
   - Exit 10: first run. Ask the questions printed in the JSON and continue at step 3.
2. To change values, collect the new answers, then run `init --force --answers FILE.json`. Start the answers
   file from the current config so unchanged values stay the same.
3. Run `init --answers FILE.json` for a first run. Folders in the config are created if missing.
4. Run `ensure` again; it must print the path and exit 0.
5. Report what was written and where. Do not print a webhook URL back in full.

## Themes

`... themes` lists the bundled presets (files in `themes/`). To add an organization theme, copy
`themes/default.json` to `themes/<name>.json`, set the colors and fonts, then choose `<name>` as the preset.
