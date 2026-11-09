#!/usr/bin/env python3
"""doc-secrets-scan.py — flag likely secrets in a generated HTML deliverable.

Operational secrets belong in a secrets manager / env file (e.g. ~/.env.secrets),
never embedded in a committed doc. HTML docs must not embed real API keys, bearer
tokens, passwords, or private keys.

This scanner is intentionally noisy on suspicious patterns. False positives are
cheap; a leaked production token is not. Exit code is always 0 unless `--strict`
is passed (the bundled /docs arm runs it in --strict so a hit STOPs generation).

Usage:
    python3 doc-secrets-scan.py [--strict] <file> [<file> ...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# (regex, label, severity, suggestion)
PATTERNS: list[tuple[str, str, str, str]] = [
    (r'-----BEGIN [A-Z ]+PRIVATE KEY-----', 'private-key', 'HIGH',
     'Move to a secrets manager; never embed private keys in HTML.'),
    (r'\bAKIA[0-9A-Z]{16}\b', 'aws-access-key', 'HIGH',
     'Rotate the AWS key immediately, then store in a secrets manager.'),
    (r'\bASIA[0-9A-Z]{16}\b', 'aws-temp-key', 'HIGH',
     'AWS temp credential present — should not be in any doc.'),
    (r'\bsk-[A-Za-z0-9]{20,}\b', 'llm-api-key', 'HIGH',
     'Rotate and replace with ${API_KEY} environment reference.'),
    (r'\bxox[abeprs]-[A-Za-z0-9-]{10,}\b', 'slack-token', 'HIGH',
     'Slack token detected — rotate via Slack admin, move to a secrets manager.'),
    (r'\bxapp-[0-9]-[A-Za-z0-9-]{10,}\b', 'slack-app-token', 'HIGH',
     'Slack app-level token detected - regenerate in the app config, move to env.'),
    # Slack incoming webhooks. Added 2026-08-03 after a live webhook was found
    # committed in git (Kuma config backups) that this scanner passed, because it
    # only ever looked for xox*- tokens. A webhook URL IS the credential: anyone
    # holding it can post to that channel.
    (r'https?://hooks\.slack\.com/services/T[A-Z0-9]{6,}/B[A-Z0-9]{6,}/[A-Za-z0-9]{16,}',
     'slack-webhook-url', 'HIGH',
     'Live Slack incoming webhook. Revoke at https://<workspace>.slack.com/services/<B-id> '
     '(the B... segment of this URL), then reference ${SLACK_WEBHOOK} instead.'),
    # Looser catch: HTML/session exports wrap long URLs, so the secret tail may be
    # split across lines. The team/bot pair alone warrants a look.
    (r'hooks\.slack\.com/services/T[A-Z0-9]{6,}', 'slack-webhook-fragment', 'MED',
     'Slack webhook URL fragment - verify the secret tail is not present elsewhere '
     'in this file, and that the webhook is not live.'),
    (r'\bghp_[A-Za-z0-9]{20,}\b', 'github-pat', 'HIGH',
     'GitHub PAT detected — revoke at github.com/settings/tokens, move to env.'),
    (r'\bghs_[A-Za-z0-9]{20,}\b', 'github-app-token', 'HIGH',
     'GitHub app token detected — revoke and move to env.'),
    # Generic bearer / Authorization headers with non-trivial payload
    (r'(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]{20,}', 'bearer-token', 'HIGH',
     'Bearer token literal — replace with ${ENV_VAR} placeholder.'),
    (r'(?i)\bx-auth-token\s*[:=]\s*["\']?[A-Za-z0-9._\-]{16,}', 'x-auth-token', 'HIGH',
     'X-Auth-Token literal — replace with ${ENV_VAR}.'),
    # Password/secret assignments with non-placeholder values
    (r'(?i)\b(password|passwd|pwd)\s*[:=]\s*["\']?(?!TODO|<|\${|\*+|REDACTED|example|changeme)[^\s"\'<]{8,}', 'password-literal', 'MED',
     'Hard-coded password literal — replace with ${ENV_VAR} or note to use a secrets manager.'),
    (r'(?i)\b(api_?key|secret_?key|access_?key)\s*[:=]\s*["\']?(?!TODO|<|\${|\*+|REDACTED|example)[A-Za-z0-9._\-]{16,}', 'api-key-literal', 'MED',
     'API key literal — move to a secrets manager, reference as ${ENV_VAR}.'),
    # Long hex/base64-ish blobs that look like keys
    (r'\b[A-Fa-f0-9]{40,}\b', 'long-hex-blob', 'LOW',
     'Long hex string — verify it is a hash/sha, not a secret.'),
]


def scan_text(text: str) -> list[tuple[int, str, str, str, str]]:
    findings = []
    for lineno, line in enumerate(text.splitlines(), 1):
        # Skip obvious placeholders & examples
        if '${' in line and re.search(r'\$\{[A-Z_]+\}', line):
            # Allow lines that include placeholder references
            stripped = re.sub(r'\$\{[A-Z_]+\}', '', line)
        else:
            stripped = line
        for pat, label, sev, suggestion in PATTERNS:
            for m in re.finditer(pat, stripped):
                snippet = m.group(0)
                if len(snippet) > 80:
                    snippet = snippet[:77] + '...'
                findings.append((lineno, label, sev, snippet, suggestion))
    return findings


def main() -> int:
    args = sys.argv[1:]
    strict = False
    if '--strict' in args:
        strict = True
        args.remove('--strict')
    if not args:
        print("Usage: doc-secrets-scan.py [--strict] <file> [<file> ...]", file=sys.stderr)
        return 2

    any_hits = False
    for p in args:
        path = Path(p)
        if not path.exists():
            print(f"ERR: {p} not found", file=sys.stderr)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        findings = scan_text(text)
        print(f"\n=== {p} ===")
        if not findings:
            print("  PASS — no obvious secrets detected")
            continue
        any_hits = True
        for lineno, label, sev, snippet, suggestion in findings:
            print(f"  [{sev}] line {lineno} — {label}: {snippet}")
            print(f"           ↪ {suggestion}")

    if any_hits and strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
