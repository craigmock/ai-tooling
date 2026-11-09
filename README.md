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

The commands below install from the `craigmock/ai-tooling` repository on GitHub. You do not need your own copy
of it first (see "New to git?" below).

### Step 1: install Python and git

The skills run small Python 3 scripts, so you need **Python 3.9 or newer** and **git**. Check what you have by
typing this in a terminal (macOS Terminal, Windows PowerShell, or a Linux shell):

```bash
python3 --version
git --version
```

If either command says "not found", install it with your system's package manager. Run these in a terminal:

| System | Install Python 3 | Install git |
|--------|------------------|-------------|
| macOS (needs [Homebrew](https://brew.sh)) | `brew install python` | `brew install git` |
| Windows (winget is built in to Windows 10 and 11) | `winget install Python.Python.3.12` | `winget install Git.Git` |
| Linux (Debian, Ubuntu) | `sudo apt install python3` | `sudo apt install git` |

Close and reopen the terminal afterwards so it finds the new programs. On Windows, if `python3` is not found
after installing, try `python --version`. If that works, tell your assistant to use `python` wherever a skill
says `python3`.

### Step 2a: Claude Code

The `/plugin` lines below are **not terminal commands**. You type them **inside a Claude Code session**:

1. Open a terminal and start Claude Code by typing `claude` and pressing Enter.
2. At the Claude Code prompt, type this line and press Enter:

```
/plugin install ai-tooling --marketplace craigmock/ai-tooling
```

If your version of Claude Code does not accept that line, add the source and install in two steps (still inside
the same Claude Code session):

```
/plugin marketplace add craigmock/ai-tooling
/plugin install ai-tooling@ai-tooling
```

Then run a skill, for example `/docs`, to start the setup wizard.

### Step 2b: Codex

(Skip this if you use Claude Code.) Codex has no plugin marketplace, so a small script copies the skills to the folder Codex reads
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
the latest version, refresh and update. Unlike the install lines above, these two are **terminal commands**: type
them in a normal terminal window, not inside a Claude Code session:

```bash
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

## Staying safe

These skills write files and run scripts on your machine, so keep secrets and private names out of what they
produce. This repository does not try to be a security product. It points you to maintained tools and adds only
a small check of its own (`tools/leak-scan.py`, which guards this repository's own publishing, and a secrets scan
that `/docs` runs on documents it creates). Use the layers that fit your situation:

| Layer | What it catches | Notes |
|-------|-----------------|-------|
| Good habits | Most accidents | Never paste keys, tokens or passwords into a prompt. Keep them in environment variables or a password manager. Keep `.env` files and config with secrets out of git. |
| [gitleaks](https://github.com/gitleaks/gitleaks) before each commit | Secrets in the changes you are about to commit | Free and open source. This repository ships a ready `.pre-commit-config.yaml` (setup below). |
| GitHub secret scanning and push protection | Known secret formats, at push time, even if a local hook is skipped | Turn on under Settings, then Code security. Free for public repositories; for private ones it depends on your GitHub plan. |
| A guard on the assistant itself (optional) | Risky tool calls, prompts and skills as the assistant works | See "Optional: DefenseClaw" below. |

### Scan before every commit with gitleaks

```bash
python3 -m pip install pre-commit      # once
pre-commit install                     # once per repository, from inside it
```

After that, every `git commit` runs gitleaks on the staged changes and stops if it finds a secret. To use it in
your own repositories, copy `.pre-commit-config.yaml` into them. To check a repository once without installing the
hook: `gitleaks detect --source .` (install gitleaks with `brew install gitleaks` or `winget install Gitleaks.Gitleaks`).

### Optional: DefenseClaw

[DefenseClaw](https://github.com/cisco-ai-defense/defenseclaw) is an open-source (Apache-2.0) project from Cisco
AI Defense. It describes itself as security governance for AI coding agents: it scans skills, plugins and tool
servers before use, inspects agent activity at run time, and keeps an audit trail. If your organization wants that
kind of control, it is a reasonable thing to evaluate. A few cautions, because a tool that sits in the path of every
tool call can also get in the way:

- Check its compatibility page for your assistant before you rely on it. This repository has not tested it with every
  assistant.
- Try it on one machine first, pin the version, and learn how to roll back (`defenseclaw rollback`) before you
  roll it out. A guard that fails closed on an internal error can stop your assistant from running commands.
- It can interfere with plugin updates. If an update fails after you install it, look at its quarantine and audit
  records before blaming the plugin.
- Its documented install is a `curl ... | bash` one-liner. Download the script and read it before running it.
- It is not a replacement for scanning what you publish. Use gitleaks and push protection as well.

### If a secret does leak

Revoke or rotate the secret first, because anything that was pushed, even for a minute, should be treated as
exposed. Then remove it from the files and, if needed, from history. Do not rely on deleting the commit alone.

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
.pre-commit-config.yaml       runs gitleaks before each commit
tests/run-tests.sh            checks
```

## License

MIT, see `LICENSE`.
