#!/usr/bin/env python3
"""Read-only dependency preflight. Does not install tools or create configuration."""
import argparse
import json
import shutil
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--json", action="store_true")
    mode.add_argument("--check", action="store_true", help="Silent on success")
    args = ap.parse_args()
    binaries = {name: shutil.which(name) for name in ("yt-dlp", "ffmpeg", "ffprobe")}
    missing = [name for name, path in binaries.items() if path is None]
    runtimes = {name: shutil.which(name) for name in ("deno", "node", "bun", "qjs")}
    python_version = sys.version.split()[0]
    problems = []
    if sys.version_info < (3, 10):
        problems.append(f"Python 3.10 or newer is required (found {python_version})")
    if missing:
        problems.append("Missing executables: " + ", ".join(missing))
    status = {"python": python_version, "binaries": binaries,
              "missing_binaries": missing, "js_runtimes": runtimes,
              "problems": problems, "can_proceed": not problems,
              "notes": ["YouTube requires a current yt-dlp distribution with EJS and a supported JS runtime.",
                        "Only Deno is enabled by yt-dlp by default; see SKILL.md for setup.",
                        "Media-tool checks use presence only, not versions, EJS availability, or network access."]}
    if args.json:
        print(json.dumps(status, indent=2))
    elif not args.check or not status["can_proceed"]:
        print("Ready" if status["can_proceed"] else "Setup required:\n" + "\n".join(problems))
        print("See SKILL.md for setup; this script does not install anything.")
    return 0 if status["can_proceed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
