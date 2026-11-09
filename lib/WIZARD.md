# First-run wizard

Every skill starts with:

```bash
python3 "${CLAUDE_SKILL_DIR}/../../lib/aitooling.py" ensure
```

| Exit | Meaning | What to do |
|------|---------|------------|
| 0 | A valid config exists; its path is printed | Continue with the skill |
| 10 | First run, or the config is invalid | Run the wizard below, then continue |
| 11 | The wizard needs a terminal and there is none | Use the question flow below |

## Question flow (inside an assistant session)

Exit 10 prints JSON with a `questions` list and the bundled `presets`. Ask them together:

1. Use question cards if your tool has them (up to four per call), otherwise ask in plain text.
   Group them: organization (name, short name), author (name, email), theme (preset, primary, accent,
   font, logo), tracking and folders.
2. Offer the bundled theme presets as options; "custom" means the person supplies the colors.
3. Save the answers as a JSON object keyed by the dotted names, in a scratch file outside the repository:

   ```json
   {
     "org.name": "Example Corp",
     "org.short_name": "example",
     "author.name": "Alex Doe",
     "theme.preset": "default",
     "theme.primary": "#1f6feb",
     "tracking.backend": "none"
   }
   ```

4. Write the config: `python3 "${CLAUDE_SKILL_DIR}/../../lib/aitooling.py" init --answers FILE.json`
5. Run `ensure` again. It must print the config path and exit 0.
6. Tell the person where the config was written and that `/setup` changes it later.

Blank answers take the preset or default value. `init` refuses invalid colors, a non-https webhook URL and an
unknown backend, and prints each problem; fix the answers and run it again.

## Terminal flow

In a terminal: `python3 lib/aitooling.py wizard` asks the same questions one at a time.

## Where the config lives

`$AI_TOOLING_CONFIG` if set, otherwise `%APPDATA%\ai-tooling\config.json` on Windows or
`~/.config/ai-tooling/config.json` elsewhere. It holds no secrets: a webhook URL is the only sensitive
value, so prefer a URL that does not embed a credential.
