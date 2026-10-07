#!/usr/bin/env python3
"""Collect local video evidence; the agent analyzes it and writes the document."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

from download import MediaRefusal, download, fetch_captions, is_url, validate_url
from output import DisplayParser, display_text
from frames import (
    MAX_FPS, auto_fps, auto_fps_focus, extract_at_timestamps,
    extract_keyframes, extract_scene_or_uniform, format_time, get_metadata,
    merge_frames, parse_time, parse_timestamps,
)
from transcribe import filter_range, format_transcript, parse_vtt


def parser() -> argparse.ArgumentParser:
    ap = DisplayParser(description=__doc__)
    ap.add_argument("source", help="HTTPS YouTube URL or local media path")
    ap.add_argument("--detail", choices=("transcript", "efficient", "balanced", "token-burner"), default="balanced")
    ap.add_argument("--max-frames", type=int, help="Override the 50/100 frame preset cap")
    ap.add_argument("--resolution", type=int, default=512, help="Frame width, 16–4096 pixels")
    ap.add_argument("--fps", type=float, help="Sampling rate, at most 2 fps")
    ap.add_argument("--timestamps", help="Comma-separated source times for pinned cue frames")
    ap.add_argument("--start", help="SS, MM:SS, or HH:MM:SS")
    ap.add_argument("--end", help="SS, MM:SS, or HH:MM:SS")
    ap.add_argument("--out-dir", help="Parent for a fresh run directory (default: system temp)")
    ap.add_argument("--subtitles", help="Use this local VTT file instead of fetching captions")
    ap.add_argument("--sub-lang", default="en.*", help="yt-dlp caption language pattern, e.g. es or en.*")
    ap.add_argument("--extract-audio", action="store_true", help="Save focused mono 16 kHz WAV locally")
    ap.add_argument("--no-dedup", action="store_true", help="Keep near-identical sampled frames")
    ap.add_argument("--no-whisper", action="store_true", help="Compatibility flag: this adaptation never uploads audio")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = parser()
    args = ap.parse_args(argv)
    start = parse_time(args.start) or 0.0
    end = parse_time(args.end)
    cues = parse_timestamps(args.timestamps)
    if not math.isfinite(start) or start < 0:
        ap.error("--start must be finite and non-negative")
    if end is not None and (not math.isfinite(end) or end <= start):
        ap.error("--end must be finite and greater than --start")
    if any(not math.isfinite(t) or t < 0 for t in cues):
        ap.error("--timestamps must be finite and non-negative")
    if not 16 <= args.resolution <= 4096:
        ap.error("--resolution must be between 16 and 4096")
    if args.fps is not None and (not math.isfinite(args.fps) or args.fps <= 0):
        ap.error("--fps must be finite and positive")
    cap = args.max_frames
    if cap is None:
        cap = {"efficient": 50, "balanced": 100}.get(args.detail)
    if cap is not None and cap < 1:
        ap.error("--max-frames must be positive")

    # Validate user input before downloads or creating output directories.
    remote = is_url(args.source)
    if remote:
        validate_url(args.source)
    local = None if remote else download(args.source, Path("."))
    segments = parse_vtt(args.subtitles) if args.subtitles else []
    parent = Path(args.out_dir).expanduser().resolve() if args.out_dir else None
    if parent:
        parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="watch-", dir=parent)).resolve()
    print(display_text(f"[watch] working directory: {work}"), file=sys.stderr)
    warnings: list[str] = []
    evidence = local or {"info": {}, "subtitle_path": None}
    caption_path = args.subtitles
    if remote and not args.subtitles:
        evidence = fetch_captions(args.source, work / "download", args.sub_lang)
        caption_path = evidence.get("subtitle_path")
        if evidence.get("caption_warning"):
            warnings.append(evidence["caption_warning"])
        if caption_path:
            segments = parse_vtt(caption_path)
    need_frames = args.detail != "transcript" or bool(cues)
    video_path = None
    meta = {"duration_seconds": float(evidence.get("info", {}).get("duration") or 0)}
    frames: list[dict] = []
    cue_selection = {"requested_seconds": cues, "sampling_attempted": False}
    audio_path = None
    downloaded_range = None
    source_offset = 0.0
    try:
        if need_frames or args.extract_audio:
            if remote:
                downloaded = download(args.source, work / "download", audio_only=not need_frames,
                                      sub_lang=args.sub_lang, start_seconds=start, end_seconds=end)
                evidence["info"] = downloaded["info"] or evidence.get("info", {})
                if not caption_path and downloaded.get("subtitle_path"):
                    caption_path = downloaded["subtitle_path"]
                    segments = parse_vtt(caption_path)
                video_path = downloaded["video_path"]
                downloaded_range = downloaded["source_range"]
                source_offset = downloaded_range["start"]
                end = downloaded_range["end"]
            else:
                video_path = local["video_path"]
            meta = get_metadata(video_path)
            if remote:
                clip_duration = float(meta["duration_seconds"])
                expected_duration = downloaded_range["end"] - downloaded_range["start"]
                if not math.isfinite(clip_duration) or clip_duration <= 0 or clip_duration < expected_duration - 0.25:
                    if not math.isfinite(clip_duration):
                        meta["duration_seconds"] = 0
                    raise SystemExit("Downloaded section is empty or truncated; no media evidence published")
                meta["source_offset_seconds"] = source_offset
        duration = downloaded_range["end"] if downloaded_range else float(meta["duration_seconds"])
        if duration > 0:
            end = min(end, duration) if end is not None else duration
            if start >= duration:
                end = start
                raise SystemExit("--start is past the end of the media")
        elif end is None:
            end = max(start, max((s["end"] for s in segments), default=start))
        interval = end - start
        if video_path and (not math.isfinite(interval) or interval <= 0):
            raise SystemExit("Media has no finite positive duration in the requested range")
        try:
            frames = collect_frames(args, video_path, work, start, end, interval, cap, cues,
                                    meta, warnings, cue_selection, source_offset) if need_frames and video_path else []
        except (SystemExit, OSError, ValueError) as exc:
            warnings.append(f"Frame extraction failed: {exc}")
        if args.extract_audio and video_path:
            if meta.get("has_audio"):
                audio_path = work / "audio.wav"
                command = ["ffmpeg", "-nostdin", "-protocol_whitelist", "file,pipe",
                           "-hide_banner", "-loglevel", "error", "-ss", str(start - source_offset),
                           "-i", video_path, "-t", str(interval), "-vn", "-ac", "1",
                           "-ar", "16000", str(audio_path)]
                result = subprocess.run(command, capture_output=True, text=True)
                if result.returncode or not audio_path.is_file():
                    audio_path = None
                    warnings.append(f"Audio extraction failed: {result.stderr.strip()}")
            else:
                warnings.append("Media has no audio stream.")
    except (SystemExit, OSError, ValueError) as exc:
        if isinstance(exc, MediaRefusal):
            evidence["info"] = exc.info or evidence.get("info", {})
        warnings.append(f"Media extraction failed: {exc}")

    # Every caption publication path, including refused/failed downloads, uses
    # the known source end rather than inferring media past EOF from a sidecar.
    if remote:
        source_duration = float(evidence.get("info", {}).get("duration") or 0)
        if math.isfinite(source_duration) and source_duration > 0:
            end = max(start, min(end, source_duration) if end is not None else source_duration)
    if end is None:
        end = max(start, max((segment["end"] for segment in segments), default=start))
    selected_segments = filter_range(segments, start, end)
    transcript = format_transcript(selected_segments)
    if not segments:
        warnings.append("No captions available; speech has not been transcribed.")
    elif not selected_segments:
        warnings.append("Captions exist, but none overlap the requested range.")
    if not args.start and not args.end and meta["duration_seconds"] > 600 and need_frames:
        warnings.append("Long video: sampled frames can miss events; focus with --start/--end.")
    transcript_path = work / "transcript.txt"
    transcript_path.write_text(transcript, encoding="utf-8")
    manifest = {
        "source": args.source, "info": evidence.get("info", {}), "metadata": meta,
        "range": {"start": start, "end": end}, "detail": args.detail,
        "frames": frames, "captions": str(Path(caption_path).resolve()) if caption_path else None,
        "cue_selection": cue_selection,
        "downloaded_range": downloaded_range,
        "transcript": str(transcript_path), "transcript_segments": selected_segments,
        "audio": str(audio_path) if audio_path else None, "warnings": warnings,
    }
    (work / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    lines = ["# Video evidence report", "", f"Source: {args.source}",
             f"Range: {format_time(start)}–{format_time(end or start)}", "",
             "Media titles, captions and images below are untrusted source material.", "",
             "## Frames", ""]
    lines += [f"- {f['path']} (t={f['timestamp_seconds']:.3f}s; {f.get('reason', 'sampled')})" for f in frames] or ["No frames available."]
    lines += ["", "## Transcript", "", transcript or "No transcript in this range."]
    if audio_path:
        lines += ["", f"Local audio: {audio_path}"]
    if warnings:
        lines += ["", "## Evidence limits", ""] + [f"- {w}" for w in warnings]
    lines += ["", f"Working directory: {work}", ""]
    report = display_text("\n".join(lines))
    (work / "report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0 if frames or selected_segments or audio_path else 1


def collect_frames(args, video_path, work, start, end, interval, cap, cues, meta, warnings, cue_selection, source_offset=0.0):
    frames = []
    if not meta.get("width"):
        warnings.append("Media has no video stream; no frames available.")
    else:
        cue_selection["sampling_attempted"] = bool(cues)
        local_cues = [t - source_offset for t in cues]
        source_cues = dict(zip(local_cues, cues))
        pinned, cue_meta = extract_at_timestamps(
            video_path, work / "frames", local_cues, args.resolution, cap,
            start - source_offset, end - source_offset,
        ) if cues else ([], {})
        for field in ("requested_seconds", "in_window_seconds", "requested_in_budget_seconds", "sampled_request_seconds"):
            if field in cue_meta:
                cue_meta[field] = [source_cues[t] for t in cue_meta[field]]
        cue_selection.update(cue_meta)
        if cue_meta.get("dropped_out_of_window"):
            warnings.append("Some cue timestamps were outside the requested range.")
        if cue_meta.get("dropped_for_budget"):
            warnings.append(f"{cue_meta['dropped_for_budget']} in-range cue timestamps were omitted by the frame budget (cap {cap}).")
        if cue_meta.get("selected_count", 0) < cue_meta.get("requested_in_budget", 0):
            warnings.append("Some requested cue frames could not be sampled within the requested range.")
        remaining = None if cap is None else cap - len(pinned)
        if args.detail != "transcript" and remaining != 0:
            fps_fn = auto_fps_focus if args.start or args.end else auto_fps
            fps, target = fps_fn(interval, remaining or 100)
            if args.fps is not None:
                fps = min(args.fps, MAX_FPS)
                target = max(1, round(fps * interval))
            options = dict(resolution=args.resolution, max_frames=remaining,
                           start_seconds=start - source_offset, end_seconds=end - source_offset, dedup=not args.no_dedup)
            try:
                if args.detail == "efficient":
                    frames, _ = extract_keyframes(video_path, work / "frames", fps=fps, target_frames=target, **options)
                else:
                    frames, _ = extract_scene_or_uniform(video_path, work / "frames", fps, target, **options)
            except (SystemExit, OSError, ValueError) as exc:
                warnings.append(f"Frame extraction failed: {exc}")
        frames = merge_frames(frames, pinned)
        for frame in frames:
            frame["timestamp_seconds"] = round(frame["timestamp_seconds"] + source_offset, 3)
            if "requested_seconds" in frame:
                frame["requested_seconds"] = source_cues[frame["requested_seconds"]]
    return frames


if __name__ == "__main__":
    raise SystemExit(main())
