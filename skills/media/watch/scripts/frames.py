#!/usr/bin/env python3
"""Probe video metadata and extract frames at an auto-scaled fps.

Auto-fps targets a frame budget, not a fixed rate. Token cost scales with frame
count, so budget-by-duration keeps short videos dense and long videos capped.
When a user-specified range is passed, focused-mode budgets denser (they are
zooming in for detail).
"""
from __future__ import annotations

import json
import math
from collections import deque
import re
import shutil
import subprocess
import sys
from pathlib import Path


MAX_FPS = 2.0
SCENE_THRESHOLD = 0.20
# Keep scene-detection results once we have at least this many distinct shots.
# Below this the video is effectively static (screen recording, talking head),
# so we fall back to uniform sampling. This floor is based on the candidate
# count before selection, independently of a small user-specified frame budget.
SCENE_MIN_FRAMES = 8
# Below this many decoded keyframes a clip is too sparse for keyframe coverage
# (very short or oddly encoded), so the cheap tier falls back to uniform.
KEYFRAME_MIN = 4
MAX_READ_DIMENSION = 1998
# Frame-delta dedup: downscale each frame to a DEDUP_THUMB x DEDUP_THUMB
# grayscale thumbnail and treat two frames as near-identical when their mean
# per-pixel difference (0-255) is at or below DEDUP_THRESHOLD. Conservative on
# purpose: only collapses frames that are visually the same shot, so a code diff
# / scrolling terminal / slide-gaining-a-bullet survives. Unlike a within-frame
# perceptual hash, this distinguishes flat frames (solid slides, fades) by luma.
DEDUP_THUMB = 16
DEDUP_THRESHOLD = 2.0
SHOWINFO_TS_RE = re.compile(r"pts_time:([-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?)")


def _decoded_frames(files: list[Path], stderr: str, start: float | None,
                    end: float | None, reason: str) -> list[dict]:
    timestamps = [float(m.group(1)) for m in SHOWINFO_TS_RE.finditer(stderr)]
    if len(timestamps) < len(files):
        raise SystemExit("Cannot align decoded frames with source timestamps")
    lo = start or 0.0
    selected = []
    for path, relative_time in zip(files, timestamps):
        timestamp = lo + relative_time
        if timestamp < lo - 0.000001 or (end is not None and timestamp >= end):
            path.unlink()
            continue
        selected.append({"index": len(selected), "timestamp_seconds": round(timestamp, 3),
                         "path": str(path), "reason": reason})
    return selected


def _scale_filter(resolution: int) -> str:
    return (
        f"scale=w='min({resolution},iw)':h='min({MAX_READ_DIMENSION},ih)':"
        "force_original_aspect_ratio=decrease:force_divisible_by=2"
    )


def _clamp_fps(fps: float, duration_seconds: float, max_frames: int) -> tuple[float, int]:
    fps = min(fps, MAX_FPS)
    target = min(max_frames, max(1, int(round(fps * duration_seconds))))
    return fps, target


def parse_time(value: str | float | int | None) -> float | None:
    """Parse SS, MM:SS, or HH:MM:SS (with optional .ms) into seconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    parts = s.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        pass
    raise SystemExit(f"Cannot parse time value: {value!r} (expected SS, MM:SS, or HH:MM:SS)")


def format_time(seconds: float) -> str:
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, sec = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


def get_metadata(video_path: str) -> dict:
    if shutil.which("ffprobe") is None:
        raise SystemExit("ffprobe is not installed. See SKILL.md for dependency setup")

    result = subprocess.run(
        [
            "ffprobe", "-protocol_whitelist", "file,pipe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(Path(video_path).resolve()),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"ffprobe failed: {result.stderr.strip()}")

    data = json.loads(result.stdout or "{}")
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = float(fmt.get("duration") or video_stream.get("duration") or 0)
    return {
        "duration_seconds": duration,
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
        "codec": video_stream.get("codec_name"),
        "size_bytes": int(fmt.get("size") or 0),
        "has_audio": audio_stream is not None,
    }


def auto_fps(duration_seconds: float, max_frames: int = 100) -> tuple[float, int]:
    """Pick fps that targets a sensible frame budget for full-video scans."""
    if duration_seconds <= 0:
        return 1.0, 1

    if duration_seconds <= 30:
        target = min(max_frames, max(12, int(round(duration_seconds))))
    elif duration_seconds <= 60:
        target = min(max_frames, 40)
    elif duration_seconds <= 180:  # 3 min
        target = min(max_frames, 60)
    elif duration_seconds <= 600:  # 10 min
        target = min(max_frames, 80)
    else:
        target = max_frames

    return _clamp_fps(target / duration_seconds, duration_seconds, max_frames)


def auto_fps_focus(duration_seconds: float, max_frames: int = 100) -> tuple[float, int]:
    """Denser budget for user-specified ranges — they are zooming in for detail."""
    if duration_seconds <= 0:
        return min(MAX_FPS, 2.0), 2

    if duration_seconds <= 5:
        target = min(max_frames, max(10, int(round(duration_seconds * 6))))
    elif duration_seconds <= 15:
        target = min(max_frames, max(30, int(round(duration_seconds * 4))))
    elif duration_seconds <= 30:
        target = min(max_frames, 60)
    elif duration_seconds <= 60:
        target = min(max_frames, 80)
    elif duration_seconds <= 180:
        target = max_frames
    else:
        target = max_frames

    return _clamp_fps(target / duration_seconds, duration_seconds, max_frames)


def _scan_candidates(command: list[str], targets: list[float] | None) -> tuple[int, list[int]]:
    """Count candidates with bounded memory and optionally choose time targets."""
    count = 0
    chosen: list[int] = []
    previous: tuple[int, float] | None = None
    next_target = 0
    tail: deque[str] = deque(maxlen=20)
    with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                          text=True, encoding="utf-8", errors="replace") as process:
        try:
            for line in process.stderr:
                tail.append(line.rstrip())
                match = SHOWINFO_TS_RE.search(line)
                if match is None:
                    continue
                timestamp = float(match.group(1))
                if targets:
                    # The final target is the actual last candidate, chosen at EOF.
                    limit = len(targets) - 1 if len(targets) > 1 else 1
                    while next_target < limit and timestamp >= targets[next_target]:
                        candidate = (count, timestamp)
                        if previous and abs(previous[1] - targets[next_target]) <= abs(timestamp - targets[next_target]):
                            candidate = previous
                        chosen.append(candidate[0])
                        next_target += 1
                previous = (count, timestamp)
                count += 1
            if process.wait():
                raise SystemExit("ffmpeg candidate scan failed: " + "\n".join(tail))
        except BaseException:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise
    if targets and count and len(targets) > 1:
        chosen.append(count - 1)
    return count, sorted(set(chosen))


def _select_candidates(video_path: str, out_dir: Path, resolution: int,
                       max_frames: int | None, start: float | None,
                       end: float | None, engine: str,
                       threshold: float = SCENE_THRESHOLD,
                       fps: float | None = None) -> tuple[list[dict], int]:
    """Scan without JPEGs, then decode only selected candidate indices to images.

    Capped modes keep O(cap) selection metadata and materialize at most the cap.
    Both passes decode the range; the extra pass avoids unbounded scratch files.
    """
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is not installed. See SKILL.md for dependency setup")
    end = end if end is not None else get_metadata(video_path)["duration_seconds"]
    duration = end - (start or 0.0)
    if not math.isfinite(duration) or duration <= 0:
        raise SystemExit("Frame extraction requires a finite positive interval")
    out_dir.mkdir(parents=True, exist_ok=True)
    for existing in out_dir.glob("frame_*.jpg"):
        existing.unlink()
    command = ["ffmpeg", "-nostdin", "-protocol_whitelist", "file,pipe",
               "-hide_banner", "-loglevel", "info", "-nostats", "-y"]
    if start is not None:
        command += ["-ss", f"{start:.6f}"]
    if engine == "keyframe":
        command += ["-skip_frame", "nokey"]
    command += ["-i", str(Path(video_path).resolve()), "-an"]
    filters = [f"select='gte(t\\,0)*lt(t\\,{duration:.9f})'"]
    if engine == "scene":
        filters += [f"select='eq(n\\,0)+gt(scene\\,{threshold})'"]
    targets = None
    if engine == "uniform":
        if fps is None or not math.isfinite(fps) or fps <= 0 or max_frames is None or max_frames < 1:
            raise SystemExit("Uniform extraction requires positive FPS and a frame cap")
        n = min(max_frames, max(1, math.ceil(min(fps, MAX_FPS) * duration)))
        targets = [0.0] if n == 1 else [i * duration / (n - 1) for i in range(n)]
    scan_filter = ",".join([*filters, "showinfo"])
    scan = command + ["-vf", scan_filter, "-fps_mode", "vfr", "-t", f"{duration:.6f}", "-f", "null", "-"]
    count, time_indices = _scan_candidates(scan, targets)
    if count == 0:
        return [], 0
    indices = time_indices if targets else (_even_indices(count, max_frames) if max_frames is not None else None)
    output_filter = list(filters)
    if indices is not None:
        if not indices:
            return [], count
        output_filter += ["select='" + "+".join(f"eq(n\\,{i})" for i in indices) + "'"]
    output_filter += [_scale_filter(resolution), "showinfo"]
    render = command + ["-vf", ",".join(output_filter), "-fps_mode", "vfr", "-t", f"{duration:.6f}",
                        "-q:v", "4", str(out_dir / "frame_%04d.jpg")]
    result = subprocess.run(render, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(f"ffmpeg frame extraction failed: {result.stderr.strip()}")
    files = sorted(out_dir.glob("frame_*.jpg"))
    frames = _decoded_frames(files, result.stderr, start, end, engine if engine != "scene" else "scene-change")
    if engine == "scene" and frames:
        frames[0]["reason"] = "first-frame"
    return frames, count


def extract(video_path: str, out_dir: Path, fps: float, resolution: int = 512,
            max_frames: int = 100, start_seconds: float | None = None,
            end_seconds: float | None = None) -> list[dict]:
    """Choose actual frames near evenly spaced times, including both range ends.

    A one-frame budget uses the first available frame. FPS determines the desired
    sample count; the cap can reduce that count, without losing the range tail.
    """
    frames, _ = _select_candidates(video_path, out_dir, resolution, max_frames,
                                   start_seconds, end_seconds, "uniform", fps=fps)
    return frames


def extract_scene_candidates(video_path: str, out_dir: Path, resolution: int = 512,
                             max_frames: int | None = 100,
                             start_seconds: float | None = None,
                             end_seconds: float | None = None,
                             threshold: float = SCENE_THRESHOLD) -> list[dict]:
    frames, _ = _select_candidates(video_path, out_dir, resolution, max_frames,
                                   start_seconds, end_seconds, "scene", threshold)
    return frames


def _even_indices(count: int, n: int) -> list[int]:
    """Indices of ``n`` evenly-spaced items out of ``count`` (first + last kept).

    ``n >= count`` returns every index; ``n == 1`` returns just the first.
    """
    if n >= count:
        return list(range(count))
    if n <= 1:
        return [0]
    return [round(i * (count - 1) / (n - 1)) for i in range(n)]


def parse_timestamps(value: str | None) -> list[float]:
    """Parse a comma-separated list of times (SS, MM:SS, HH:MM:SS) into a
    sorted, de-duplicated list of seconds. Empty/blank tokens are skipped;
    an unparseable token raises (via :func:`parse_time`)."""
    if not value:
        return []
    out: list[float] = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        seconds = parse_time(token)
        if seconds is not None:
            out.append(float(seconds))
    return sorted(set(out))


def merge_frames(primary: list[dict], pinned: list[dict]) -> list[dict]:
    """Combine two frame lists into one chronological list and reindex 0..n-1.

    ``pinned`` frames (transcript cues) are never dropped — this is a plain
    union, so the cap is enforced upstream by reserving budget for the cues.
    """
    merged = sorted([*primary, *pinned], key=lambda f: f["timestamp_seconds"])
    for i, frame in enumerate(merged):
        frame["index"] = i
    return merged


def extract_at_timestamps(
    video_path: str,
    out_dir: Path,
    timestamps: list[float],
    resolution: int = 512,
    max_frames: int | None = None,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
) -> tuple[list[dict], dict]:
    """Grab exactly one frame at each requested timestamp (transcript cues).

    Timestamps are absolute source seconds. Any falling outside an active
    ``[start, end)`` focus window are dropped. Files use a ``cue_*.jpg`` prefix
    so they sit alongside detail-engine ``frame_*.jpg`` output without either
    clobbering the other. When more cues than ``max_frames`` survive, they are
    even-sampled (first + last kept) before extraction.
    """
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is not installed. See SKILL.md for dependency setup")

    out_dir.mkdir(parents=True, exist_ok=True)
    for existing in out_dir.glob("cue_*.jpg"):
        existing.unlink()

    lo = start_seconds or 0.0
    hi = end_seconds if end_seconds is not None else float("inf")
    requested = sorted(set(float(t) for t in timestamps))
    in_window = [t for t in requested if lo <= t < hi]
    dropped = len(requested) - len(in_window)

    if max_frames is not None and len(in_window) > max_frames:
        points = [in_window[i] for i in _even_indices(len(in_window), max_frames)]
    else:
        points = in_window

    out: list[dict] = []
    for t in points:
        path = out_dir / f"cue_{len(out):04d}.jpg"
        cmd = [
            "ffmpeg", "-nostdin", "-protocol_whitelist", "file,pipe",
            "-hide_banner",
            "-loglevel", "info",
            "-y",
            "-ss", f"{t:.6f}",
            "-i", str(Path(video_path).resolve()),
            "-frames:v", "1",
            "-vf", f"{_scale_filter(resolution)},showinfo",
            "-q:v", "4",
            str(path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and path.exists():
            decoded = _decoded_frames([path], result.stderr, t, end_seconds, "transcript-cue")
            for frame in decoded:
                frame["index"] = len(out)
                frame["requested_seconds"] = t
                out.append(frame)

    meta = {
        "engine": "timestamps",
        "requested_seconds": requested,
        "in_window_seconds": in_window,
        "requested_in_budget_seconds": points,
        "sampled_request_seconds": [frame["requested_seconds"] for frame in out],
        "candidate_count": len(requested),
        "selected_count": len(out),
        "dropped_out_of_window": dropped,
        "requested_in_budget": len(points),
        "dropped_for_budget": len(in_window) - len(points),
        "fallback": False,
    }
    return out, meta


def _frame_delta(a: bytes, b: bytes) -> float:
    """Mean absolute per-pixel difference (0-255) between two grayscale
    thumbnails. Mismatched lengths are treated as maximally different so a
    decode hiccup never collapses distinct frames."""
    if not a or len(a) != len(b):
        return float("inf")
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def _thumb_frames(paths: list[Path]) -> list[bytes]:
    """Decode every frame in ``paths`` to a small grayscale thumbnail via one
    ffmpeg pass over the JPEG sequence.

    ffmpeg does the pixel decode (keeps us pure-stdlib); we slice the raw
    grayscale stream into one ``DEDUP_THUMB``-square thumbnail per frame.
    Fail-open: any ffmpeg error, an unrecognized name, or a byte-count mismatch
    returns ``[]`` so the caller skips dedup rather than breaking extraction.
    """
    if not paths:
        return []
    paths = [Path(p) for p in paths]
    m = re.match(r"(.*?)(\d+)(\.[A-Za-z0-9]+)$", paths[0].name)
    if m is None:
        return []
    prefix, digits, ext = m.group(1), m.group(2), m.group(3)
    pattern = str(paths[0].parent / f"{prefix}%0{len(digits)}d{ext}")

    cmd = [
        "ffmpeg", "-nostdin", "-protocol_whitelist", "file,pipe",
        "-hide_banner",
        "-loglevel", "error",
        "-start_number", str(int(digits)),
        "-i", pattern,
        "-vf", f"scale={DEDUP_THUMB}:{DEDUP_THUMB},format=gray",
        "-f", "rawvideo",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        return []

    chunk = DEDUP_THUMB * DEDUP_THUMB
    data = result.stdout
    if len(data) != chunk * len(paths):
        return []
    return [data[i * chunk:(i + 1) * chunk] for i in range(len(paths))]


def dedupe_perceptual(
    candidates: list[dict], threshold: float = DEDUP_THRESHOLD
) -> tuple[list[dict], int]:
    """Drop near-identical frames from a chronological candidate list.

    Thumbnails the extracted JPEGs and greedily removes interior frames whose
    mean per-pixel difference from the last kept one is within ``threshold``.
    The first and last frames preserve coverage even in static clips. Returns
    ``(survivors, dropped_count)``; a no-op (unchanged list) when thumbnails are
    unavailable or there are fewer than two candidates.
    """
    if len(candidates) <= 1:
        return candidates, 0
    thumbs = _thumb_frames([Path(c["path"]) for c in candidates])
    return _dedupe_by_deltas(candidates, thumbs, threshold)


def _dedupe_by_deltas(
    candidates: list[dict], thumbs: list[bytes], threshold: float = DEDUP_THRESHOLD
) -> tuple[list[dict], int]:
    """Greedily drop frames within ``threshold`` mean per-pixel difference of the
    last *kept* frame, preserving the first and last. Deletes dropped JPEGs and
    reindexes survivors 0..n-1. Fail-open: if ``thumbs`` does not
    line up 1:1 with ``candidates``, return them unchanged.
    """
    if len(thumbs) != len(candidates) or len(candidates) <= 1:
        return candidates, 0

    kept = [candidates[0]]
    last = thumbs[0]
    dropped: list[dict] = []
    for index, (cand, thumb) in enumerate(zip(candidates[1:], thumbs[1:]), 1):
        if index != len(candidates) - 1 and _frame_delta(thumb, last) <= threshold:
            dropped.append(cand)
        else:
            kept.append(cand)
            last = thumb

    for cand in dropped:
        try:
            Path(cand["path"]).unlink()
        except OSError:
            pass
    for i, frame in enumerate(kept):
        frame["index"] = i
    return kept, len(dropped)


def extract_scene_or_uniform(video_path: str, out_dir: Path, fps: float,
                             target_frames: int, resolution: int = 512,
                             max_frames: int | None = 100,
                             start_seconds: float | None = None,
                             end_seconds: float | None = None,
                             dedup: bool = True) -> tuple[list[dict], dict]:
    frames, count = _select_candidates(video_path, out_dir, resolution, max_frames,
                                       start_seconds, end_seconds, "scene")
    fallback = count < SCENE_MIN_FRAMES
    if fallback:
        cap = target_frames if max_frames is None else min(max_frames, target_frames)
        frames = extract(video_path, out_dir, fps, resolution, cap, start_seconds, end_seconds)
    frames, dropped = dedupe_perceptual(frames) if dedup else (frames, 0)
    return frames, {"engine": "uniform" if fallback else "scene", "candidate_count": count,
                    "deduped_count": dropped, "selected_count": len(frames), "fallback": fallback}


def extract_keyframes(video_path: str, out_dir: Path, resolution: int = 512,
                      max_frames: int | None = 50,
                      start_seconds: float | None = None,
                      end_seconds: float | None = None,
                      dedup: bool = True, fps: float | None = None,
                      target_frames: int | None = None) -> tuple[list[dict], dict]:
    frames, count = _select_candidates(video_path, out_dir, resolution, max_frames,
                                       start_seconds, end_seconds, "keyframe")
    fallback = count < KEYFRAME_MIN
    if fallback:
        cap = max_frames if max_frames is not None else (target_frames or 100)
        if fps is None:
            duration = (end_seconds if end_seconds is not None else get_metadata(video_path)["duration_seconds"]) - (start_seconds or 0.0)
            fps_fn = auto_fps_focus if start_seconds is not None or end_seconds is not None else auto_fps
            fps, target_frames = fps_fn(duration, cap)
        cap = min(cap, target_frames) if target_frames is not None else cap
        frames = extract(video_path, out_dir, fps, resolution, cap, start_seconds, end_seconds)
    frames, dropped = dedupe_perceptual(frames) if dedup else (frames, 0)
    return frames, {"engine": "uniform" if fallback else "keyframe", "candidate_count": count,
                    "deduped_count": dropped, "selected_count": len(frames), "fallback": fallback}
