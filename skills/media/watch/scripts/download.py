#!/usr/bin/env python3
"""Download a video via yt-dlp, or resolve a local file path.

Also fetches subtitles (manual first, then auto-generated) in VTT format so
transcribe.py can parse them without needing Whisper.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse


VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi", ".flv", ".wmv"}
AUDIO_EXTS = {".m4a", ".mp3", ".opus", ".wav", ".flac", ".ogg", ".aac"}
MAX_MEDIA_SECONDS = 1800
MAX_MEDIA_BYTES = 256 * 1024 * 1024
YTDLP_FLAGS = [
    "--ignore-config", "--no-plugin-dirs", "--no-remote-components",
    "--no-playlist", "--no-progress", "--socket-timeout", "30",
    "--retries", "2", "--fragment-retries", "2",
]
YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtu.be", "www.youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com",
}


class MediaRefusal(SystemExit):
    """Keep source metadata available when an admitted media pass cannot finish."""

    def __init__(self, message: str, info: dict):
        super().__init__(message)
        self.info = info


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
            try:
                duration = float(raw.get("duration") or 0)
            except (TypeError, ValueError):
                duration = 0
            if not math.isfinite(duration) or duration <= 0:
                duration = None
            info = {
                "title": raw.get("title"),
                "uploader": raw.get("uploader") or raw.get("channel"),
                "duration": duration,
                "is_live": raw.get("is_live"),
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
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
) -> dict:
    validate_url(url)
    if not math.isfinite(start_seconds) or start_seconds < 0:
        raise SystemExit("Download start must be finite and non-negative")
    if end_seconds is not None:
        if not math.isfinite(end_seconds) or end_seconds <= start_seconds:
            raise SystemExit("Download end must be finite and greater than start")
        if end_seconds - start_seconds > MAX_MEDIA_SECONDS:
            raise SystemExit("Remote media is limited to 30 minutes per run; use a shorter --start/--end range")
    if shutil.which("yt-dlp") is None:
        raise SystemExit("yt-dlp is not on PATH. See SKILL.md for dependency setup.")

    out_dir = _fresh_dir(out_dir)
    output_template = str(out_dir / "video.%(ext)s")

    # Establish a finite interval before admitting any media download, including
    # calls made directly to this helper rather than through watch.py.
    info_command = ["yt-dlp", *YTDLP_FLAGS, "--skip-download", "--write-info-json",
                    "-o", output_template, "--", url]
    info_result = subprocess.run(info_command, stdout=sys.stderr, stderr=sys.stderr)
    if info_result.returncode:
        raise SystemExit(f"yt-dlp metadata fetch failed (exit {info_result.returncode})")
    source_info = _read_info(out_dir / "video.info.json", url)
    if source_info.get("is_live"):
        raise MediaRefusal("Live streams are outside the bounded media workflow", source_info)
    try:
        source_duration = float(source_info.get("duration") or 0)
    except (TypeError, ValueError):
        source_duration = 0
    known_duration = math.isfinite(source_duration) and source_duration > 0
    if end_seconds is None:
        if not known_duration:
            raise MediaRefusal("Media duration is unknown; provide a finite --start/--end range", source_info)
        end_seconds = source_duration
    elif known_duration:
        end_seconds = min(end_seconds, source_duration)
    interval = end_seconds - start_seconds
    if interval <= 0:
        raise MediaRefusal("Download range is past the end of the media", source_info)
    if interval > MAX_MEDIA_SECONDS:
        raise MediaRefusal("Remote media is limited to 30 minutes per run; use a shorter --start/--end range", source_info)

    fmt = "ba[ext=m4a]" if audio_only else "bv[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4][height<=720]"
    # Re-encode accurate cuts with a fine time base, retaining fractional frame
    # phase. Flush packets so FFmpeg observes its size guard during writing.
    cmd = [
        "yt-dlp",
        *YTDLP_FLAGS,
        "--download-sections", f"*{start_seconds:.6f}-{end_seconds:.6f}",
        "--downloader", "ffmpeg",
        "--force-keyframes-at-cuts",
        "--downloader-args", (f"ffmpeg_o:-c:v mpeg4 -q:v 3 -enc_time_base:v 1:60000 -c:a aac -fps_mode vfr -flush_packets 1 "
                              f"-t {interval:.6f} -fs {MAX_MEDIA_BYTES}"),
        "--match-filters", "!is_live & !is_upcoming",
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

    try:
        result = subprocess.run(cmd, stdout=sys.stderr, stderr=sys.stderr)
    except OSError as exc:
        raise MediaRefusal(f"yt-dlp download could not start: {exc}", source_info) from exc
    if result.returncode:
        raise MediaRefusal(f"yt-dlp download failed (exit {result.returncode}); evidence kept in {out_dir}", source_info)
    video = _pick_video(out_dir)
    if video is None:
        raise MediaRefusal(
            f"yt-dlp did not produce a video file in {out_dir} (exit {result.returncode})", source_info
        )
    if video.stat().st_size >= MAX_MEDIA_BYTES:
        raise MediaRefusal(f"Media reached the 256 MiB output limit; use a shorter range. Evidence kept in {out_dir}", source_info)

    subtitle = _pick_subtitle(out_dir)
    info = _read_info(out_dir / "video.info.json", url)

    return {
        "video_path": str(video),
        "subtitle_path": str(subtitle) if subtitle else None,
        "info": info or {"url": url},
        "downloaded": True,
        "source_range": {"start": start_seconds, "end": end_seconds},
    }


def download(
    source: str,
    out_dir: Path,
    audio_only: bool = False,
    sub_lang: str = "en.*",
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
) -> dict:
    if is_url(source):
        return download_url(source, out_dir, audio_only=audio_only, sub_lang=sub_lang,
                            start_seconds=start_seconds, end_seconds=end_seconds)
    return resolve_local(source)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: download.py <url-or-path> <out-dir>", file=sys.stderr)
        raise SystemExit(2)
    result = download(sys.argv[1], Path(sys.argv[2]))
    print(json.dumps(result, indent=2))
