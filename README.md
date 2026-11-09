# ai-tooling

Skills for Claude Code and Codex that look like they belong to your organization. The first time you run one, a short setup
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

Requirements: Python 3.9 or newer and git. The commands below install from the `craigmock/ai-tooling` repository
on GitHub. You do not need your own copy of it first (see "New to git?" below).

### Claude Code

```
/plugin install ai-tooling --marketplace craigmock/ai-tooling
```

If your version of Claude Code does not accept that line, add the source and install in two steps:

```
/plugin marketplace add craigmock/ai-tooling
/plugin install ai-tooling@ai-tooling
```

### Codex

Codex has no plugin marketplace, so a small script copies the skills to the folder Codex reads
(`~/.agents/skills`). Clone the repository once, then run the script from inside it:

```bash
git clone https://github.com/craigmock/ai-tooling.git
cd ai-tooling
python3 tools/install-codex.py
```

In Codex, call a skill with a dollar sign, for example `$docs` or `$eos`. On macOS or Linux,
`python3 tools/install-codex.py --link` links the skills to your clone instead of copying them, so a later
`git pull` updates them in place.

Codex support follows the shared `SKILL.md` format and has been tested only by running the scripts directly,
not inside a live Codex session. If a skill cannot find its scripts, tell Codex to use the folder the
`SKILL.md` was loaded from (each skill says so at the top).

### Other assistants

Any assistant that reads `SKILL.md` folders from `~/.agents/skills` can use the Codex steps above.

## New to git? How this works

You can skip this if you already use GitHub.

**Do I need to copy ("fork" or "clone") this repository to my own account first?** No. For Claude Code, the
install line above reads the skills straight from the publisher's GitHub repository. You never create a copy,
and you never need to learn git for ordinary use.

**What happens when the publisher makes an update?** Nothing changes on your computer by itself. When you want
the latest version, refresh and update:

```
claude plugin marketplace update ai-tooling
claude plugin update ai-tooling
```

For Codex, run `git pull` inside your clone and run `python3 tools/install-codex.py` again.

**Will an update erase my settings?** No. Your organization name, colors and choices live in one file on your
own computer (`~/.config/ai-tooling/config.json`, or `%APPDATA%\ai-tooling\config.json` on Windows). The
repository never contains it and updates never touch it.

**When would I fork it?** Only if you want to change the skills themselves and keep your changes. A fork is
your own copy on GitHub. Fork it, change it, then install from your copy:
`/plugin install ai-tooling --marketplace <your-account>/ai-tooling`. If you only want your own colors and
wording, you do not need a fork: run `/setup`.

**Words you will see**

| Word | Meaning |
|------|---------|
| Repository ("repo") | A project folder whose history is tracked by git and stored on GitHub |
| Clone | Download a copy of a repository to your computer |
| Pull | Download the latest changes into a clone you already have |
| Fork | Your own copy of someone else's repository on GitHub |
| Marketplace | A repository that Claude Code can install plugins from |
| Plugin | A bundle of skills that Claude Code installs and updates for you |

**If the install fails with "not found" or a permission error.** Either the account name is wrong, or the
repository is private and your GitHub account has not been given access. Ask the publisher to add you, then sign
in once with the GitHub command line (`gh auth login`) and try again.

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
.claude-plugin/plugin.json    plugin manifest (Claude Code)
.claude-plugin/marketplace.json  lets Claude Code install this repository by name
tools/install-codex.py        copies the skills to ~/.agents for Codex
lib/aitooling.py              config, wizard, theme tokens, tracking
lib/WIZARD.md                 how a skill runs the wizard
themes/*.json                 theme presets
skills/<name>/SKILL.md        one folder per skill, with scripts/ and templates/
tools/leak-scan.py            publish gate
tests/run-tests.sh            checks
```

## License

MIT, see `LICENSE`.
