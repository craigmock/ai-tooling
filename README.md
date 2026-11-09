# ai-tooling

Assistant skills that look like they belong to your organization. The first time you run one, a short setup
wizard asks for your organization name, brand colors, fonts, logo, ticket or time tracking choice and output
folders. It saves the answers in one local file, and every skill reads that file from then on.

| Skill | What it does |
|-------|--------------|
| `/setup` | Run or change the setup wizard |
| `/eos` | End-of-session wrap-up: summary, unsaved work, worklog entry, optional tracking call |
| `/docs` | Branded HTML document from a title or a Markdown file, plus a secrets scan |
| `/runbook` | Runbook scaffold and a validator for a fixed section contract |
| `/loose-ends` | Sweep a session for unfinished work and unanswered questions |
| `/answers` | Interactive HTML answer sheet for open decisions |
| `/nrp` | Find, check and write the next-session resume prompt |

Everything is plain Python 3 (standard library only) and Markdown. It runs on macOS, Linux and Windows
(Git Bash or WSL).

## Install

This repository is a plugin for Claude Code. Add it as a plugin source and enable it:

```
/plugin marketplace add <owner>/ai-tooling
/plugin install ai-tooling
```

Or clone it and point your assistant at the `skills/` folder. Requirements: Python 3.9 or newer and git.

## First run

Run any skill, for example `/docs`. If there is no config yet, the skill asks the setup questions, writes the
config, and carries on with your request. You can also run `/setup` directly, or from a terminal:

```bash
python3 lib/aitooling.py wizard
```

Questions asked: organization name and short name, your name and optional email, a theme preset (or custom
colors), body font, optional logo path, tracking backend (`none`, `file`, `webhook`), and the folder for generated
documents. Blank answers take the preset's value.

The config is written to `$AI_TOOLING_CONFIG` if you set it, otherwise `~/.config/ai-tooling/config.json`
(`%APPDATA%\ai-tooling\config.json` on Windows). It is never committed; `config.json` is in `.gitignore`.

For scripted setup:

```bash
python3 lib/aitooling.py init --org-name "Example Corp" --short-name example --author-name "Alex Doe" \
    --preset default --primary "#0a7d5a" --backend none
```

## How theming works

The config holds theme tokens: `primary`, `accent`, `background`, `text`, `muted`, `border`, `font_body`,
`font_mono` and an optional `logo_path`. Documents are built from `skills/docs/templates/doc.template.html`,
which uses them as CSS custom properties, so a theme change recolors every document without editing a template.
The answer sheet maps the same tokens onto its own palette.

`python3 lib/aitooling.py theme-css` prints the tokens as CSS if you want to use them in your own pages.

## Add an organization theme

1. Copy `themes/default.json` to `themes/<your-name>.json`.
2. Set the colors (`#rrggbb`) and font stacks. Keep the `name` field readable.
3. Run `/setup` and choose `<your-name>` as the preset, or run
   `python3 lib/aitooling.py init --force --preset <your-name> ...`.

Individual tokens given at setup override the preset, so a one-off color needs no new file.

## Tracking backends

| Backend | Behavior of `/eos` |
|---------|--------------------|
| `none` | Writes the worklog entry only |
| `file` | Also appends one JSON line per session to the configured log file |
| `webhook` | Also sends the same JSON to an `https://` URL you choose |

The JSON is `{time, org, author, kind, summary, minutes, ref}`. Nothing is sent unless you pick `webhook`, and
only when `/eos` records a session.

## Checks

```bash
bash tests/run-tests.sh
```

runs the wizard against a throwaway config, checks that each skill reads it, runs the bundled self-tests, and runs
the leak scan (`tools/leak-scan.py`). The leak scan must pass before this repository is published or updated: it
fails on private names, local paths, private IP ranges, email addresses, credential shapes and vendor credit
lines.

## Layout

```
.claude-plugin/plugin.json    plugin manifest
lib/aitooling.py              config, wizard, theme tokens, tracking
lib/WIZARD.md                 how a skill runs the wizard
themes/*.json                 theme presets
skills/<name>/SKILL.md        one folder per skill, with scripts/ and templates/
tools/leak-scan.py            publish gate
tests/run-tests.sh            checks
```

## License

MIT, see `LICENSE`.
