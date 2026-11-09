#!/usr/bin/env python3
"""Install ai-tooling for Codex (or any assistant that reads $HOME/.agents/skills).

Claude Code installs this repository as a plugin and does not need this script. Codex has no plugin
marketplace, so this copies the skills where it looks for them:

    ~/.agents/skills/<skill>/   one folder per skill (SKILL.md, scripts, templates)
    ~/.agents/lib/              shared setup code the skills call
    ~/.agents/themes/           theme presets

Run from a clone of the repository:

    python3 tools/install-codex.py            # copy (works everywhere, re-run after `git pull` to update)
    python3 tools/install-codex.py --link     # symlinks instead (macOS/Linux), so `git pull` updates in place
    python3 tools/install-codex.py --dest DIR # use DIR instead of ~/.agents

A folder is only replaced if this script created it (it carries a `.ai-tooling` marker). Anything else with
the same name is left alone and reported.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MARK = ".ai-tooling"


def ours(p: Path) -> bool:
    return p.is_symlink() or (p.is_dir() and (p / MARK).exists())


def clear(p: Path) -> None:
    if p.is_symlink() or p.is_file():
        p.unlink()
    elif p.is_dir():
        shutil.rmtree(p)


def place(src: Path, dst: Path, link: bool) -> bool:
    if dst.exists() or dst.is_symlink():
        if not ours(dst):
            print("  skipped  %s (exists and was not installed by this script)" % dst)
            return False
        clear(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if link:
        os.symlink(src, dst, target_is_directory=True)
    else:
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"))
        (dst / MARK).write_text("installed by tools/install-codex.py\n", encoding="utf-8")
    print("  %-8s %s" % ("linked" if link else "copied", dst))
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", default=os.path.join(os.path.expanduser("~"), ".agents"))
    ap.add_argument("--link", action="store_true", help="symlink instead of copy (macOS/Linux)")
    a = ap.parse_args()
    dest = Path(a.dest)

    if a.link and not hasattr(os, "symlink"):
        print("symlinks are not available here; run without --link", file=sys.stderr)
        return 2
    skills = sorted(p for p in (REPO / "skills").iterdir() if (p / "SKILL.md").is_file())
    if not skills:
        print("no skills found under %s/skills" % REPO, file=sys.stderr)
        return 2

    print("Installing %d skills into %s" % (len(skills), dest))
    failed = 0
    for s in skills:
        if not place(s, dest / "skills" / s.name, a.link):
            failed += 1
    if not a.link:
        # The skills reach ../../lib and ../../themes, which from ~/.agents/skills/<name> is ~/.agents.
        for name in ("lib", "themes"):
            if not place(REPO / name, dest / name, False):
                failed += 1

    print()
    print("Done." if not failed else "Done with %d item(s) skipped; see above." % failed)
    print("Start Codex and run a skill, for example:  $docs   (the first run asks the setup questions).")
    print("To update later:  git pull  then run this script again.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
