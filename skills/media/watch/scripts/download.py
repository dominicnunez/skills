#!/usr/bin/env python3
"""Download a video via yt-dlp, or resolve a local file path.

Also fetches subtitles (manual first, then auto-generated) in VTT format so
transcribe.py can parse them without needing Whisper.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse


VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi", ".flv", ".wmv"}
AUDIO_EXTS = {".m4a", ".mp3", ".opus", ".wav", ".flac", ".ogg", ".aac"}
YTDLP_FLAGS = [
    "--ignore-config", "--no-plugin-dirs", "--no-remote-components",
    "--no-playlist", "--no-progress", "--socket-timeout", "30",
    "--retries", "2", "--fragment-retries", "2",
]
YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtu.be", "www.youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com",
}


def validate_url(source: str) -> None:
    parsed = urlparse(source)
    try:
        valid = (parsed.scheme == "https" and parsed.hostname in YOUTUBE_HOSTS
                 and parsed.port in (None, 443) and not parsed.username and not parsed.password)
    except ValueError:
        valid = False
    if not valid:
        raise SystemExit("Use an HTTPS YouTube URL or supply a local media file.")


def _fresh_dir(parent: Path) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="fetch-", dir=parent))


def is_url(source: str) -> bool:
    if source.startswith("-"):
        return False
    parsed = urlparse(source)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def resolve_local(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise SystemExit(f"File not found: {p}")
    if p.suffix.lower() not in VIDEO_EXTS | AUDIO_EXTS:
        raise SystemExit(f"Unsupported media extension: {p.suffix}")
    return {
        "video_path": str(p),
        "subtitle_path": None,
        "info": {"title": p.name, "url": str(p)},
        "downloaded": False,
    }


def _pick_subtitle(out_dir: Path) -> Path | None:
    candidates = sorted(out_dir.glob("video*.vtt"))
    if not candidates:
        return None
    preferred = [
        c for c in candidates
        if any(marker in c.name for marker in (".en.", ".en-US.", ".en-GB.", ".en-orig."))
    ]
    return preferred[0] if preferred else candidates[0]


def _pick_video(out_dir: Path) -> Path | None:
    # Only the final fixed output name, never partial files or merge components.
    for ext in sorted(VIDEO_EXTS | AUDIO_EXTS):
        candidate = out_dir / f"video{ext}"
        if candidate.is_file() and candidate.stat().st_size:
            return candidate
    return None


def fetch_captions(url: str, out_dir: Path, sub_lang: str = "en.*") -> dict:
    """Fetch metadata and best available VTT captions without downloading video."""
    validate_url(url)
    if shutil.which("yt-dlp") is None:
        raise SystemExit("yt-dlp is not on PATH. See SKILL.md for dependency setup.")

    out_dir = _fresh_dir(out_dir)
    output_template = str(out_dir / "video.%(ext)s")
    cmd = [
        "yt-dlp",
        *YTDLP_FLAGS,
        "--skip-download",
        "--write-info-json",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", sub_lang,
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        "-o", output_template,
        "--",
        url,
    ]
    result = subprocess.run(cmd, stdout=sys.stderr, stderr=sys.stderr)
    subtitle = _pick_subtitle(out_dir)
    info = _read_info(out_dir / "video.info.json", url)
    return {
        "video_path": None,
        "subtitle_path": str(subtitle) if subtitle else None,
        "info": info or {"url": url},
        "downloaded": False,
        "caption_warning": f"Caption fetch exited {result.returncode}" if result.returncode else None,
    }


def _read_info(info_path: Path, url: str) -> dict:
    info: dict = {}
    if info_path.exists():
        try:
            raw = json.loads(info_path.read_text(encoding="utf-8"))
            info = {
                "title": raw.get("title"),
                "uploader": raw.get("uploader") or raw.get("channel"),
                "duration": raw.get("duration"),
                "url": raw.get("webpage_url") or url,
            }
        except Exception as exc:
            print(f"[watch] info.json parse failed: {exc}", file=sys.stderr)
            info = {"url": url}
    return info


def download_url(
    url: str,
    out_dir: Path,
    audio_only: bool = False,
    sub_lang: str = "en.*",
) -> dict:
    validate_url(url)
    if shutil.which("yt-dlp") is None:
        raise SystemExit("yt-dlp is not on PATH. See SKILL.md for dependency setup.")

    out_dir = _fresh_dir(out_dir)
    output_template = str(out_dir / "video.%(ext)s")

    fmt = "ba/bestaudio" if audio_only else "bv*[height<=720]+ba/b[height<=720]/bv+ba/b"
    cmd = [
        "yt-dlp",
        *YTDLP_FLAGS,
        "-N", "8",
        "-f", fmt,
        "--merge-output-format", "mp4",
        "--write-info-json",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", sub_lang,
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        "-o", output_template,
        "--",
        url,
    ]

    result = subprocess.run(cmd, stdout=sys.stderr, stderr=sys.stderr)
    if result.returncode:
        raise SystemExit(f"yt-dlp download failed (exit {result.returncode}); evidence kept in {out_dir}")
    video = _pick_video(out_dir)
    if video is None:
        raise SystemExit(
            f"yt-dlp did not produce a video file in {out_dir} (exit {result.returncode})"
        )

    subtitle = _pick_subtitle(out_dir)
    info = _read_info(out_dir / "video.info.json", url)

    return {
        "video_path": str(video),
        "subtitle_path": str(subtitle) if subtitle else None,
        "info": info or {"url": url},
        "downloaded": True,
    }


def download(
    source: str,
    out_dir: Path,
    audio_only: bool = False,
    sub_lang: str = "en.*",
) -> dict:
    if is_url(source):
        return download_url(source, out_dir, audio_only=audio_only, sub_lang=sub_lang)
    return resolve_local(source)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: download.py <url-or-path> <out-dir>", file=sys.stderr)
        raise SystemExit(2)
    result = download(sys.argv[1], Path(sys.argv[2]))
    print(json.dumps(result, indent=2))
