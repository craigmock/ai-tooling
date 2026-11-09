---
name: docs
description: Create a branded HTML document (report, as-built, summary, runbook scaffold) styled with the organization's own colors, fonts, logo and author line, or convert a Markdown file into one. Use for "make this a doc", "write a report", "render this markdown as HTML", "audit this document for secrets".
---

# /docs

Produces a self-contained HTML document themed from the organization config. The first run of any ai-tooling
skill asks a few setup questions; this skill does the same if no config exists yet.

## Step 0: organization config

```bash
python3 "${CLAUDE_SKILL_DIR}/../../lib/aitooling.py" ensure
```

Exit 0: continue. Exit 10: follow `lib/WIZARD.md` (ask the printed questions, write the answers file, run
`init`), then run `ensure` again before going on.

## Steps

1. Get the title and the content. If the person has a Markdown file, use it; otherwise write the body yourself
   as Markdown in a scratch file first.
2. Create the document:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/doc-new.py" "Title here" --md body.md
   ```

   It writes `<slug>.html` and a dated snapshot `<slug>-YYYYMMDD.html` to the configured docs folder and prints
   both paths. Without `--md` the body is a TODO placeholder for you to fill.
3. Scan for secrets before sharing:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/doc-secrets-scan.py" PATH.html
   ```

   Exit 0 means clean. Any HIGH finding blocks sharing until the value is replaced by an environment-variable
   reference and, if it was real, rotated.
4. Tell the person the paths. Open the file in a browser only if they ask.

## Rules

- All text from the person goes through the scripts, which escape it. Never paste user text into the template by
  hand.
- Theme comes only from the config (`lib/aitooling.py theme-css`). Do not hard-code colors, names or logos.
- The author line is the configured author. Do not invent one.
- Markdown subset supported by `md-to-html.py`: headings, paragraphs, lists, tables, quotes, code blocks, bold,
  italic, inline code and links.

## Tooling

| Script | Purpose |
|--------|---------|
| `scripts/doc-new.py` | Build a themed document, optionally from Markdown |
| `scripts/md-to-html.py` | Markdown to the HTML subset the template uses (`--emit body` or `--emit toc`) |
| `scripts/doc-secrets-scan.py` | Find credential-shaped strings in a document |
| `templates/doc.template.html` | Page template; colors come from CSS custom properties |
