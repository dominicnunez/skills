"""Offline contract checks; no video services or transcription APIs are called."""
import contextlib
from array import array
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import download
import setup as preflight
import watch
from transcribe import filter_range, parse_vtt


class PreflightTests(unittest.TestCase):
    def invoke(self, version, missing, option):
        output = io.StringIO()
        def locate(name):
            return None if name in missing else f"/tools/{name}"
        with patch("sys.argv", ["setup.py", *option]), patch.object(preflight.sys, "version_info", version), \
             patch.object(preflight.sys, "version", ".".join(map(str, version))), \
             patch.object(preflight.shutil, "which", side_effect=locate), contextlib.redirect_stdout(output):
            result = preflight.main()
        return result, output.getvalue()

    def test_unsupported_python_has_a_reason_in_every_output(self):
        for option in ([], ["--check"], ["--json"]):
            for missing in ([], ["ffprobe"]):
                with self.subTest(option=option, missing=missing):
                    result, output = self.invoke((3, 9, 9), missing, option)
                    self.assertEqual(result, 2)
                    if option == ["--json"]:
                        data = json.loads(output)
                        self.assertFalse(data["can_proceed"])
                        output = "\n".join(data["problems"])
                    self.assertIn("Python 3.10 or newer", output)
                    self.assertIn("3.9.9", output)
                    if missing:
                        self.assertIn("ffprobe", output)

    def test_supported_python_distinguishes_ready_from_missing_binary(self):
        for option in ([], ["--check"], ["--json"]):
            with self.subTest(option=option):
                result, output = self.invoke((3, 12, 0), [], option)
                self.assertEqual(result, 0)
                if option == ["--check"]:
                    self.assertEqual(output, "")
                if option == ["--json"]:
                    self.assertTrue(json.loads(output)["can_proceed"])
                    self.assertEqual(json.loads(output)["problems"], [])
                result, output = self.invoke((3, 12, 0), ["ffmpeg"], option)
                self.assertEqual(result, 2)
                if option == ["--json"]:
                    data = json.loads(output)
                    self.assertFalse(data["can_proceed"])
                    output = "\n".join(data["problems"])
                self.assertIn("ffmpeg", output)

    def test_preflight_requires_the_enabled_youtube_runtime(self):
        runtimes = {"deno", "node", "qjs", "bun"}
        for present in (set(), {"node"}, {"qjs"}, {"bun"}, {"deno"}):
            for option in ([], ["--check"], ["--json"]):
                with self.subTest(present=present, option=option):
                    result, output = self.invoke((3, 12, 0), runtimes - present, option)
                    self.assertEqual(result, 0 if "deno" in present else 2)
                    if "deno" not in present:
                        if option == ["--json"]:
                            data = json.loads(output)
                            self.assertFalse(data["can_proceed"])
                            output = "\n".join(data["problems"])
                        self.assertIn("Deno", output)


class DownloadTests(unittest.TestCase):
    def test_caption_request_cannot_load_config_or_plugins(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("download.shutil.which", return_value="yt-dlp"):
                with patch("download.subprocess.run") as run:
                    run.return_value = subprocess.CompletedProcess([], 0)
                    download.fetch_captions("https://youtu.be/example", Path(folder))
            command = run.call_args.args[0]
            for flag in ("--ignore-config", "--no-plugin-dirs", "--no-remote-components"):
                self.assertIn(flag, command)
            self.assertEqual(command[-2:], ["--", "https://youtu.be/example"])
            self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_failed_download_cannot_reuse_a_stale_file(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            (output / "video.mp4").write_bytes(b"old unrelated media")
            with patch("download.shutil.which", return_value="yt-dlp"):
                def fail_media(command, **kwargs):
                    if "--skip-download" in command:
                        template = command[command.index("-o") + 1]
                        Path(template.replace("%(ext)s", "info.json")).write_text(json.dumps({"duration": 10}))
                        return subprocess.CompletedProcess(command, 0)
                    return subprocess.CompletedProcess(command, 1)
                with patch("download.subprocess.run", side_effect=fail_media):
                    with self.assertRaises(SystemExit):
                        download.download_url("https://youtu.be/new-video", output)

    def test_merge_component_is_not_a_completed_download(self):
        with tempfile.TemporaryDirectory() as folder:
            def incomplete(command, **kwargs):
                template = command[command.index("-o") + 1]
                if "--skip-download" in command:
                    Path(template.replace("%(ext)s", "info.json")).write_text(json.dumps({"duration": 10}))
                else:
                    Path(template.replace("%(ext)s", "f137.mp4")).write_bytes(b"component")
                return subprocess.CompletedProcess(command, 0)
            with patch("download.shutil.which", return_value="yt-dlp"):
                with patch("download.subprocess.run", side_effect=incomplete):
                    with self.assertRaisesRegex(SystemExit, "did not produce"):
                        download.download_url("https://youtu.be/example", Path(folder))

    def test_whole_remote_denies_long_or_unknown_duration_before_media(self):
        for duration, live in ((3601, False), (None, False), (float("inf"), False), ("invalid", False), (10, True)):
            with self.subTest(duration=duration, live=live), tempfile.TemporaryDirectory() as folder:
                media_calls = []
                def video_service(command, **kwargs):
                    template = command[command.index("-o") + 1]
                    Path(template.replace("%(ext)s", "info.json")).write_text(json.dumps({"duration": duration, "is_live": live}))
                    if "--skip-download" not in command:
                        media_calls.append(command)
                        Path(template.replace("%(ext)s", "mp4")).write_bytes(b"oversized source")
                    return subprocess.CompletedProcess(command, 0)
                with patch("download.shutil.which", return_value="yt-dlp"), \
                     patch("download.subprocess.run", side_effect=video_service):
                    with self.assertRaises(SystemExit):
                        download.download("https://youtu.be/example", Path(folder))
                self.assertEqual(media_calls, [])
                self.assertEqual(list(Path(folder).glob("fetch-*/video.mp4")), [])

    def test_remote_invalid_or_overlong_range_denies_io(self):
        for start, end in ((-1, 2), (0, float("inf")), (1, 1), (3, 2), (0, 1801)):
            with self.subTest(start=start, end=end), tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / "uncreated"
                with patch("download.subprocess.run") as run:
                    with self.assertRaises(SystemExit):
                        download.download_url("https://youtu.be/example", output,
                                              start_seconds=start, end_seconds=end)
                    run.assert_not_called()
                self.assertFalse(output.exists())

    def test_media_at_output_limit_is_not_published(self):
        for audio_only in (False, True):
            with self.subTest(audio_only=audio_only), tempfile.TemporaryDirectory() as folder:
                media_commands = []
                def video_service(command, **kwargs):
                    template = command[command.index("-o") + 1]
                    Path(template.replace("%(ext)s", "info.json")).write_text(json.dumps({"duration": 86400}))
                    if "--skip-download" not in command:
                        media_commands.append(command)
                        Path(template.replace("%(ext)s", "m4a" if audio_only else "mp4")).write_bytes(b"x" * 64)
                    return subprocess.CompletedProcess(command, 0)
                with patch("download.shutil.which", return_value="yt-dlp"), \
                     patch("download.subprocess.run", side_effect=video_service), \
                     patch.object(download, "MAX_MEDIA_BYTES", 64):
                    with self.assertRaisesRegex(SystemExit, "output limit"):
                        download.download_url("https://youtu.be/example", Path(folder), audio_only=audio_only,
                                              start_seconds=5000, end_seconds=5002)
                self.assertEqual(len(media_commands), 1)
                command = media_commands[0]
                section = command[command.index("--download-sections") + 1]
                self.assertEqual(list(map(float, section.lstrip("*").split("-"))), [5000, 5002])
                self.assertEqual(command[command.index("--downloader") + 1], "ffmpeg")
                self.assertIn("--force-keyframes-at-cuts", command)
                options = shlex.split(command[command.index("--downloader-args") + 1].split(":", 1)[1])
                self.assertEqual(float(options[options.index("-t") + 1]), 2)
                self.assertEqual(int(options[options.index("-fs") + 1]), 64)


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = self.root / "local video.mp4"
        self.media.write_bytes(b"fixture")
        self.captions = self.root / "captions.vtt"
        self.captions.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nEarly evidence\n\n"
                                 "00:00:07.000 --> 00:00:08.000\nLater evidence\n", encoding="utf-8")
        self.output = self.root / "runs"

    def invoke(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return watch.main([str(self.media), "--out-dir", str(self.output), *args])

    def test_unknown_remote_duration_keeps_caption_evidence(self):
        for duration in ("invalid", float("inf"), float("nan")):
            with self.subTest(duration=duration):
                media_calls = []
                def video_service(command, **kwargs):
                    template = command[command.index("-o") + 1]
                    Path(template.replace("%(ext)s", "info.json")).write_text(json.dumps({"duration": duration}))
                    if "--write-subs" in command:
                        shutil.copyfile(self.captions, template.replace("%(ext)s", "en.vtt"))
                    if "--skip-download" not in command:
                        media_calls.append(command)
                    return subprocess.CompletedProcess(command, 0)
                with patch("download.shutil.which", return_value="yt-dlp"), \
                     patch("download.subprocess.run", side_effect=video_service), \
                     contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(watch.main(["https://youtu.be/example", "--out-dir", str(self.output)]), 0)
                data = json.loads(max(self.output.glob("watch-*/manifest.json"), key=lambda p: p.stat().st_mtime_ns).read_text())
                self.assertEqual(data["metadata"]["duration_seconds"], 0)
                self.assertEqual(data["range"], {"start": 0.0, "end": 8.0})
                self.assertEqual(len(data["transcript_segments"]), 2)
                self.assertEqual(data["frames"], [])
                self.assertTrue(any("unknown" in warning for warning in data["warnings"]))
                self.assertEqual(media_calls, [])

    def test_overlong_remote_range_keeps_captions_without_media_transfer(self):
        with patch("download.subprocess.run") as run, \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = watch.main(["https://youtu.be/example", "--subtitles", str(self.captions),
                                 "--end", "3600", "--extract-audio", "--out-dir", str(self.output)])
        self.assertEqual(result, 0)
        run.assert_not_called()
        data = json.loads(next(self.output.glob("watch-*/manifest.json")).read_text())
        self.assertEqual(len(data["transcript_segments"]), 2)
        self.assertEqual(data["frames"], [])
        self.assertIsNone(data["audio"])
        self.assertTrue(any("30 minutes" in warning for warning in data["warnings"]))

    def test_empty_or_truncated_remote_section_keeps_focused_captions(self):
        for duration in (0, 0.5):
            with self.subTest(duration=duration):
                result = {"info": {"duration": 10}, "video_path": str(self.media),
                          "source_range": {"start": 1.0, "end": 8.0}, "subtitle_path": None}
                metadata = {"duration_seconds": duration, "width": 320, "has_audio": True}
                with patch("watch.download", return_value=result), patch("watch.get_metadata", return_value=metadata), \
                     patch("watch.collect_frames", return_value=[]) as frames, \
                     patch("watch.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "unexpected audio call")) as audio, \
                     contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    status = watch.main(["https://youtu.be/example", "--subtitles", str(self.captions),
                                         "--start", "1", "--end", "8", "--extract-audio", "--out-dir", str(self.output)])
                self.assertEqual(status, 0)
                frames.assert_not_called()
                audio.assert_not_called()
                data = json.loads(max(self.output.glob("watch-*/manifest.json"), key=lambda p: p.stat().st_mtime_ns).read_text())
                self.assertEqual(data["range"], {"start": 1.0, "end": 8.0})
                self.assertEqual(len(data["transcript_segments"]), 2)
                self.assertEqual(data["frames"], [])
                self.assertIsNone(data["audio"])
                self.assertTrue(any("section" in warning for warning in data["warnings"]))

    def test_remote_refusal_retains_known_end_before_publishing_captions(self):
        self.captions.write_text("WEBVTT\n\n00:07.000 --> 00:12.000\nForeign captions past EOF\n", encoding="utf-8")
        for options in ([], ["--end", "20"], ["--detail", "transcript", "--extract-audio"]):
            with self.subTest(options=options):
                media_calls = []
                def video_service(command, **kwargs):
                    template = command[command.index("-o") + 1]
                    Path(template.replace("%(ext)s", "info.json")).write_text(json.dumps({"duration": 6}))
                    if "--skip-download" not in command:
                        media_calls.append(command)
                    return subprocess.CompletedProcess(command, 0)
                with patch("download.shutil.which", return_value="yt-dlp"), \
                     patch("download.subprocess.run", side_effect=video_service), \
                     patch("watch.get_metadata") as probe, \
                     contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    status = watch.main(["https://youtu.be/example", "--subtitles", str(self.captions),
                                         "--start", "10", "--out-dir", str(self.output), *options])
                self.assertEqual(status, 1)
                probe.assert_not_called()
                self.assertEqual(media_calls, [])
                data = json.loads(max(self.output.glob("watch-*/manifest.json"), key=lambda p: p.stat().st_mtime_ns).read_text())
                self.assertEqual(data["range"], {"start": 10.0, "end": 10.0})
                self.assertEqual(data["info"]["duration"], 6)
                self.assertEqual(data["transcript_segments"], [])
                self.assertEqual(data["frames"], [])
                self.assertIsNone(data["audio"])

    def test_remote_media_failures_keep_known_end_and_valid_captions(self):
        for failure in ("exit", "missing", "size", "start"):
            with self.subTest(failure=failure):
                media_calls = []
                def video_service(command, **kwargs):
                    template = command[command.index("-o") + 1]
                    if "--skip-download" in command:
                        Path(template.replace("%(ext)s", "info.json")).write_text(json.dumps({"duration": 6}))
                        return subprocess.CompletedProcess(command, 0)
                    media_calls.append(command)
                    if failure == "start":
                        raise OSError("downloader unavailable")
                    if failure == "size":
                        Path(template.replace("%(ext)s", "mp4")).write_bytes(b"x" * 64)
                    return subprocess.CompletedProcess(command, 1 if failure == "exit" else 0)
                with patch("download.shutil.which", return_value="yt-dlp"), \
                     patch("download.subprocess.run", side_effect=video_service), \
                     patch.object(download, "MAX_MEDIA_BYTES", 64), patch("watch.get_metadata") as probe, \
                     contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    status = watch.main(["https://youtu.be/example", "--subtitles", str(self.captions),
                                         "--start", "1", "--end", "10", "--extract-audio", "--out-dir", str(self.output)])
                self.assertEqual(status, 0)
                self.assertEqual(len(media_calls), 1)
                probe.assert_not_called()
                data = json.loads(max(self.output.glob("watch-*/manifest.json"), key=lambda p: p.stat().st_mtime_ns).read_text())
                self.assertEqual(data["range"], {"start": 1.0, "end": 6.0})
                self.assertEqual(data["info"]["duration"], 6)
                self.assertEqual(data["transcript_segments"], [{"start": 1.0, "end": 2.0, "text": "Early evidence"}])
                self.assertEqual(data["frames"], [])
                self.assertIsNone(data["audio"])
                self.assertTrue(any("Media extraction failed" in warning for warning in data["warnings"]))

    def test_caption_source_end_survives_later_metadata_failure(self):
        evidence = {"info": {"duration": 6}, "subtitle_path": str(self.captions)}
        with patch("watch.fetch_captions", return_value=evidence), \
             patch("download.shutil.which", return_value="yt-dlp"), \
             patch("download.subprocess.run", return_value=subprocess.CompletedProcess([], 1)) as run, \
             patch("watch.get_metadata") as probe, \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            status = watch.main(["https://youtu.be/example", "--start", "1", "--end", "10",
                                 "--out-dir", str(self.output)])
        self.assertEqual(status, 0)
        self.assertEqual(run.call_count, 1)
        self.assertIn("--skip-download", run.call_args.args[0])
        probe.assert_not_called()
        data = json.loads(next(self.output.glob("watch-*/manifest.json")).read_text())
        self.assertEqual(data["range"], {"start": 1.0, "end": 6.0})
        self.assertEqual(data["transcript_segments"], [{"start": 1.0, "end": 2.0, "text": "Early evidence"}])
        self.assertEqual(data["frames"], [])
        self.assertIsNone(data["audio"])

    def test_focused_captions_use_positive_half_open_overlap(self):
        self.captions.write_text("WEBVTT\n\n00:01.000 --> 00:02.000\nTouches start\n\n"
                                 "00:01.999 --> 00:02.001\nCrosses start\n\n"
                                 "00:02.000 --> 00:04.000\nInside\n\n"
                                 "00:03.999 --> 00:04.001\nCrosses end\n\n"
                                 "00:04.000 --> 00:05.000\nTouches end\n", encoding="utf-8")
        for options, expected in ((["--start", "2", "--end", "4"], ["Crosses start", "Inside", "Crosses end"]),
                                  (["--start", "2"], ["Crosses start", "Inside", "Crosses end", "Touches end"]),
                                  (["--end", "4"], ["Touches start", "Crosses start", "Inside", "Crosses end"])):
            with self.subTest(options=options):
                self.assertEqual(self.invoke("--detail", "transcript", "--subtitles", str(self.captions), *options), 0)
                latest = max(self.output.glob("watch-*/manifest.json"), key=lambda path: path.stat().st_mtime_ns)
                data = json.loads(latest.read_text())
                self.assertEqual([segment["text"] for segment in data["transcript_segments"]], expected)
                crossing = next(segment for segment in data["transcript_segments"] if segment["text"] == "Crosses start")
                self.assertEqual((crossing["start"], crossing["end"]), (1.999, 2.001))

    def test_nested_rolling_cues_preserve_the_full_evidence_interval(self):
        for later in ("Repeated evidence", "Repeated evidence extended"):
            with self.subTest(later=later):
                self.captions.write_text("WEBVTT\n\n00:05.000 --> 00:09.000\nRepeated evidence\n\n"
                                         f"00:06.000 --> 00:07.000\n{later}\n", encoding="utf-8")
                self.assertEqual(self.invoke("--detail", "transcript", "--subtitles", str(self.captions),
                                             "--start", "7.5", "--end", "8.5"), 0)
                latest = max(self.output.glob("watch-*/manifest.json"), key=lambda path: path.stat().st_mtime_ns)
                data = json.loads(latest.read_text())
                self.assertEqual(data["transcript_segments"], [{"start": 5.0, "end": 9.0, "text": "Repeated evidence"}])
        self.captions.write_text("WEBVTT\n\n00:05.000 --> 00:06.000\nRepeated evidence\n\n"
                                 "00:06.000 --> 00:07.000\nRepeated evidence\n", encoding="utf-8")
        self.assertEqual(self.invoke("--detail", "transcript", "--subtitles", str(self.captions),
                                     "--start", "5", "--end", "7"), 0)
        latest = max(self.output.glob("watch-*/manifest.json"), key=lambda path: path.stat().st_mtime_ns)
        data = json.loads(latest.read_text())
        self.assertEqual(data["transcript_segments"], [
            {"start": 5.0, "end": 6.0, "text": "Repeated evidence"},
            {"start": 6.0, "end": 7.0, "text": "Repeated evidence"},
        ])

    def test_cue_requests_survive_media_probe_failure(self):
        with patch("watch.get_metadata", side_effect=SystemExit("probe failed")):
            self.assertEqual(self.invoke("--timestamps", "2,3,4", "--subtitles", str(self.captions)), 0)
        data = json.loads(next(self.output.glob("watch-*/manifest.json")).read_text())
        self.assertEqual(data["cue_selection"]["requested_seconds"], [2.0, 3.0, 4.0])
        self.assertFalse(data["cue_selection"]["sampling_attempted"])
        self.assertEqual(data["range"], {"start": 0.0, "end": 8.0})
        self.assertTrue(any("probe failed" in warning for warning in data["warnings"]))

    def test_prefix_cues_preserve_their_own_start_time(self):
        for end in (7, 9, 10):
            with self.subTest(end=end):
                self.captions.write_text("WEBVTT\n\n00:05.000 --> 00:09.000\nRepeated evidence\n\n"
                                         f"00:06.000 --> 00:{end:02d}.000\nRepeated evidence extended\n", encoding="utf-8")
                self.assertEqual(self.invoke("--detail", "transcript", "--subtitles", str(self.captions),
                                             "--start", "5", "--end", "6"), 0)
                latest = max(self.output.glob("watch-*/manifest.json"), key=lambda path: path.stat().st_mtime_ns)
                data = json.loads(latest.read_text())
                self.assertEqual(data["transcript_segments"], [
                    {"start": 5.0, "end": 9.0, "text": "Repeated evidence"},
                ])

    def test_start_after_caption_coverage_has_valid_empty_range(self):
        self.captions.write_text("WEBVTT\n\n00:05.000 --> 00:06.000\nEarlier evidence\n", encoding="utf-8")
        for mode in ("transcript", "balanced"):
            with self.subTest(mode=mode), patch("watch.get_metadata", side_effect=SystemExit("probe failed")):
                self.assertEqual(self.invoke("--detail", mode, "--start", "10", "--subtitles", str(self.captions)), 1)
                latest = max(self.output.glob("watch-*/manifest.json"), key=lambda path: path.stat().st_mtime_ns)
                data = json.loads(latest.read_text())
                self.assertEqual(data["range"], {"start": 10.0, "end": 10.0})
                self.assertEqual(data["transcript_segments"], [])

    def test_media_end_blocks_captions_and_decoders_past_eof(self):
        self.captions.write_text("WEBVTT\n\n00:07.000 --> 00:12.000\nBeyond actual media\n", encoding="utf-8")
        metadata = {"duration_seconds": 6, "width": 320, "height": 180, "has_audio": True}
        for end in ([], ["--end", "20"]):
            with self.subTest(end=end), patch("watch.get_metadata", return_value=metadata), patch("watch.subprocess.run") as run:
                self.assertEqual(self.invoke("--start", "10", "--extract-audio", "--subtitles", str(self.captions), *end), 1)
                run.assert_not_called()
                latest = max(self.output.glob("watch-*/manifest.json"), key=lambda path: path.stat().st_mtime_ns)
                data = json.loads(latest.read_text())
                self.assertEqual(data["range"], {"start": 10.0, "end": 10.0})
                self.assertEqual(data["transcript_segments"], [])
                self.assertEqual(data["frames"], [])
                self.assertIsNone(data["audio"])
                self.assertTrue(any("past the end" in warning for warning in data["warnings"]))

    def test_empty_caption_windows_have_no_overlap(self):
        segments = [{"start": 0.0, "end": 20.0, "text": "Straddles point"}]
        self.assertEqual(filter_range(segments, 10, 10), [])
        self.assertEqual(filter_range(segments, 12, 10), [])

    def test_invalid_caption_times_preserve_valid_later_evidence(self):
        huge_hour = "9" * 310
        self.captions.write_text(f"WEBVTT\n\n00:00.000 --> {huge_hour}:00:00.000\nInvalid infinite end\n\n"
                                 "00:03.000 --> 00:02.000\nReversed\n\n"
                                 "00:03.000 --> 00:03.000\nEmpty interval\n\n"
                                 "00:05.000 --> 00:06.000\nValid later evidence\n", encoding="utf-8")
        self.assertEqual(self.invoke("--detail", "transcript", "--subtitles", str(self.captions)), 0)
        data = json.loads(next(self.output.glob("watch-*/manifest.json")).read_text())
        self.assertEqual(data["transcript_segments"], [
            {"start": 5.0, "end": 6.0, "text": "Valid later evidence"},
        ])
        self.assertEqual(data["range"], {"start": 0.0, "end": 6.0})

    def test_invalid_range_is_rejected_before_output_or_network(self):
        with patch("watch.fetch_captions") as fetch:
            for options in (("--start", "nan"), ("--end", "-1"), ("--start", "5", "--end", "4"),
                            ("--fps", "0"), ("--resolution", "0"), ("--timestamps", "inf")):
                with self.subTest(options=options), self.assertRaises(SystemExit):
                    self.invoke(*options)
            fetch.assert_not_called()
            self.assertFalse(self.output.exists())

    def test_focused_sidecar_transcript_saved_without_media_tools(self):
        with patch("watch.get_metadata") as probe, patch("watch.fetch_captions") as fetch:
            result = self.invoke("--detail", "transcript", "--subtitles", str(self.captions),
                                 "--start", "6", "--end", "9")
        self.assertEqual(result, 0)
        probe.assert_not_called()
        fetch.assert_not_called()
        run = next(self.output.iterdir())
        self.assertEqual((run / "transcript.txt").read_text(), "[00:07] Later evidence")
        data = json.loads((run / "manifest.json").read_text())
        self.assertEqual(data["range"], {"start": 6.0, "end": 9.0})
        self.assertEqual(data["frames"], [])
        self.assertIn("Later evidence", (run / "report.md").read_text())

    def test_decoding_failure_preserves_captions_and_prior_runs(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("existing work")
        with patch("watch.get_metadata", side_effect=SystemExit("invalid media")):
            result = self.invoke("--subtitles", str(self.captions))
        self.assertEqual(result, 0)
        self.assertEqual(sentinel.read_text(), "existing work")
        run = next(p for p in self.output.iterdir() if p.is_dir())
        data = json.loads((run / "manifest.json").read_text())
        self.assertEqual(len(data["transcript_segments"]), 2)
        self.assertTrue(any("invalid media" in w for w in data["warnings"]))

    def test_transcript_only_url_does_not_download_media(self):
        captions = {"info": {"duration": 10}, "subtitle_path": str(self.captions)}
        with patch("watch.fetch_captions", return_value=captions), patch("watch.download") as dl:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = watch.main(["https://youtu.be/example", "--detail", "transcript",
                                     "--out-dir", str(self.output)])
        self.assertEqual(result, 0)
        dl.assert_not_called()

    def test_short_and_long_webvtt_times_preserve_cue_evidence(self):
        self.captions.write_text("WEBVTT\n\n00:01.000 --> 00:02.000\nShort &amp; valid\n\n"
                                 "01:00:03.500 --> 01:00:04.750\nLong form\n", encoding="utf-8")
        self.assertEqual(parse_vtt(str(self.captions)), [
            {"start": 1.0, "end": 2.0, "text": "Short & valid"},
            {"start": 3603.5, "end": 3604.75, "text": "Long form"},
        ])

    def test_non_youtube_urls_are_rejected_before_output_or_network(self):
        with patch("watch.fetch_captions") as fetch:
            for source in ("https://127.0.0.1/video", "https://169.254.169.254/video",
                           "https://youtube.com.example/video", "https://user@youtube.com/watch?v=x",
                           "http://youtube.com/watch?v=x", "https://youtube.com:8443/watch?v=x"):
                with self.subTest(source=source), self.assertRaises(SystemExit):
                    with contextlib.redirect_stderr(io.StringIO()):
                        watch.main([source, "--out-dir", str(self.output)])
            fetch.assert_not_called()
            self.assertFalse(self.output.exists())

    def test_frame_failure_still_extracts_requested_audio(self):
        metadata = {"duration_seconds": 10, "width": 320, "height": 180, "has_audio": True}
        def extract_audio(command, **kwargs):
            Path(command[-1]).write_bytes(b"local audio evidence")
            return subprocess.CompletedProcess(command, 0, "", "")
        with patch("watch.get_metadata", return_value=metadata):
            with patch("watch.extract_scene_or_uniform", side_effect=SystemExit("frame decoder failed")):
                with patch("watch.subprocess.run", side_effect=extract_audio):
                    result = self.invoke("--subtitles", str(self.captions), "--extract-audio")
        self.assertEqual(result, 0)
        data = json.loads(next(self.output.glob("watch-*/manifest.json")).read_text())
        self.assertIsNotNone(data["audio"])
        self.assertTrue(Path(data["audio"]).is_file())
        self.assertTrue(any("frame decoder failed" in w for w in data["warnings"]))

    def test_pinned_frame_survives_regular_sampling_failure(self):
        metadata = {"duration_seconds": 10, "width": 320, "height": 180, "has_audio": False}
        def cue_frame(video, output, *args):
            output.mkdir()
            image = output / "cue_0000.jpg"
            image.write_bytes(b"cue image")
            return ([{"path": str(image), "timestamp_seconds": 2, "reason": "transcript-cue"}], {})
        with patch("watch.get_metadata", return_value=metadata):
            with patch("watch.extract_at_timestamps", side_effect=cue_frame):
                with patch("watch.extract_scene_or_uniform", side_effect=SystemExit("scene failure")):
                    result = self.invoke("--timestamps", "2", "--subtitles", str(self.captions))
        self.assertEqual(result, 0)
        data = json.loads(next(self.output.glob("watch-*/manifest.json")).read_text())
        self.assertEqual(len(data["frames"]), 1)
        self.assertEqual(data["frames"][0]["timestamp_seconds"], 2)
        self.assertTrue(any("scene failure" in w for w in data["warnings"]))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Requires FFmpeg/ffprobe on PATH")
class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.media = cls.root / "synthetic clip.mp4"
        # Many distinct cuts and fixed one-second keyframes exercise both engines.
        pattern = ("color=c=black:size=320x180:rate=10:duration=10,"
                   "drawbox=color=white:x=0:y=0:w=iw:h=ih:t=fill:enable='lt(mod(t,0.4),0.2)',"
                   "drawbox=color=blue:x=0:y=0:w=32:h=32:t=fill:enable='lt(t,2)',"
                   "drawbox=color=lime:x=0:y=0:w=32:h=32:t=fill:enable='gte(t,2)*lt(t,8)',"
                   "drawbox=color=red:x=0:y=0:w=32:h=32:t=fill:enable='gte(t,8)'")
        audio = "aevalsrc=0.2*sin(2*PI*if(lt(t\\,2)\\,220\\,if(lt(t\\,8)\\,440\\,880))*t):s=16000:d=10"
        subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                        "-f", "lavfi", "-i", pattern, "-f", "lavfi", "-i", audio,
                        "-c:v", "mpeg4", "-g", "10", "-c:a", "aac",
                        "-shortest", str(cls.media)], check=True, capture_output=True, timeout=30)
        cls.captions = cls.root / "captions.vtt"
        cls.captions.write_text("WEBVTT\n\n00:00.000 --> 00:01.000\nExcluded opening\n\n"
                                "00:02.000 --> 00:03.000\nIn-range evidence\n\n"
                                "00:09.000 --> 00:10.000\nExcluded ending\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def remote_service(self, media_commands):
        real_run = subprocess.run
        def video_service(command, **kwargs):
            if command[0] != "yt-dlp":
                return real_run(command, **kwargs)
            template = command[command.index("-o") + 1]
            Path(template.replace("%(ext)s", "info.json")).write_text(json.dumps({"duration": 10}))
            if "--skip-download" not in command:
                media_commands.append(command)
                target = template.replace("%(ext)s", "mp4")
                if "--download-sections" in command:
                    section = command[command.index("--download-sections") + 1].lstrip("*")
                    start, end = map(float, section.split("-"))
                    options = shlex.split(command[command.index("--downloader-args") + 1].split(":", 1)[1])
                    encoded = real_run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                                        "-ss", str(start), "-t", str(end - start), "-i", str(self.media),
                                        *options, target], capture_output=True, text=True, timeout=30)
                    self.assertEqual(encoded.returncode, 0, encoded.stderr)
                else:
                    shutil.copyfile(self.media, target)
            return subprocess.CompletedProcess(command, 0)
        return video_service

    def test_remote_focus_downloads_only_the_section_and_keeps_source_times(self):
        real_run = subprocess.run
        real_which = shutil.which
        output = self.root / "remote-focus"
        media_commands = []
        with patch("download.shutil.which", side_effect=lambda name: "yt-dlp" if name == "yt-dlp" else real_which(name)), \
             patch("download.subprocess.run", side_effect=self.remote_service(media_commands)), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = watch.main(["https://youtu.be/example", "--subtitles", str(self.captions),
                                 "--start", "1.35", "--end", "8.7", "--max-frames", "3",
                                 "--timestamps", "2.04,8.54", "--extract-audio", "--out-dir", str(output)])
        self.assertEqual(result, 0)
        downloaded = next(output.glob("watch-*/download/fetch-*/video.mp4"))
        from frames import get_metadata
        self.assertAlmostEqual(get_metadata(str(downloaded))["duration_seconds"], 7.35, delta=0.1)
        self.assertEqual(len(media_commands), 1)
        self.assertIn("--download-sections", media_commands[0])
        data = json.loads(next(output.glob("watch-*/manifest.json")).read_text())
        self.assertEqual(data["range"], {"start": 1.35, "end": 8.7})
        self.assertEqual(data["downloaded_range"], {"start": 1.35, "end": 8.7})
        self.assertTrue(all(1.35 <= frame["timestamp_seconds"] < 8.7 for frame in data["frames"]))
        pinned = [frame for frame in data["frames"] if frame["reason"] == "transcript-cue"]
        self.assertEqual([frame["requested_seconds"] for frame in pinned], [2.04, 8.54])
        self.assertEqual([frame["timestamp_seconds"] for frame in pinned], [2.1, 8.6])
        self.assertTrue(any(frame["timestamp_seconds"] < 2 for frame in data["frames"]))
        for frame in data["frames"]:
            decoded = real_run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                                "-i", frame["path"], "-vf", "crop=8:8:4:4,scale=1:1",
                                "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=30)
            self.assertEqual(decoded.returncode, 0, decoded.stderr)
            expected_channel = 2 if frame["timestamp_seconds"] < 2 else (1 if frame["timestamp_seconds"] < 8 else 0)
            self.assertEqual(max(range(3), key=lambda index: decoded.stdout[index]), expected_channel)
        self.assertEqual(data["transcript_segments"], [{"start": 2.0, "end": 3.0, "text": "In-range evidence"}])
        with wave.open(data["audio"]) as audio:
            length = audio.getnframes() / 16000
            self.assertAlmostEqual(length, 7.35, delta=0.1)
            for local_time, expected_hz in ((0.1, 220), (1.0, 440), (length - 0.3, 880)):
                audio.setpos(round(local_time * 16000))
                samples = array("h", audio.readframes(3200))
                crossings = sum((a < 0) != (b < 0) for a, b in zip(samples, samples[1:]))
                self.assertAlmostEqual(crossings / 0.4, expected_hz, delta=20)

    def test_native_remote_size_guard_stops_writes_and_keeps_captions(self):
        real_which = shutil.which
        output = self.root / "remote-size-refusal"
        media_commands = []
        with patch("download.shutil.which", side_effect=lambda name: "yt-dlp" if name == "yt-dlp" else real_which(name)), \
             patch("download.subprocess.run", side_effect=self.remote_service(media_commands)), \
             patch.object(download, "MAX_MEDIA_BYTES", 15000), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = watch.main(["https://youtu.be/example", "--subtitles", str(self.captions),
                                 "--start", "1.35", "--end", "8.7", "--extract-audio", "--out-dir", str(output)])
        self.assertEqual(result, 0)
        media = next(output.glob("watch-*/download/fetch-*/video.mp4"))
        # This fixture's full section encodes to more than 80 kB. Flushed size
        # limiting stops early, with muxer/packet overshoot below this ceiling.
        self.assertGreaterEqual(media.stat().st_size, 15000)
        self.assertLess(media.stat().st_size, 30000)
        self.assertEqual(len(media_commands), 1)
        data = json.loads(next(output.glob("watch-*/manifest.json")).read_text())
        self.assertEqual(data["frames"], [])
        self.assertIsNone(data["audio"])
        self.assertEqual(data["range"], {"start": 1.35, "end": 8.7})
        self.assertEqual(len(data["transcript_segments"]), 1)
        self.assertTrue(any("output limit" in warning for warning in data["warnings"]))

    def test_native_modes_keep_frames_and_audio_in_fractional_range(self):
        for mode in ("balanced", "efficient", "transcript"):
            with self.subTest(mode=mode):
                output = self.root / mode
                result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "watch.py"), str(self.media),
                                         "--subtitles", str(self.captions), "--detail", mode, "--start", "1.3",
                                         "--end", "8.7", "--max-frames", "3", "--extract-audio", "--no-dedup",
                                         "--out-dir", str(output)], capture_output=True, text=True,
                                        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(next(output.glob("watch-*/manifest.json")).read_text(encoding="utf-8"))
                self.assertEqual(data["warnings"], [])
                self.assertLessEqual(len(data["frames"]), 3)
                self.assertEqual(data["transcript_segments"], [{"start": 2.0, "end": 3.0, "text": "In-range evidence"}])
                if mode != "transcript":
                    self.assertEqual(len(data["frames"]), 3)
                    self.assertTrue(all(1.3 <= f["timestamp_seconds"] <= 8.7 for f in data["frames"]))
                    self.assertGreater(data["frames"][-1]["timestamp_seconds"], 7.0)
                    for frame in data["frames"]:
                        self.assertTrue(Path(frame["path"]).is_file())
                with wave.open(data["audio"]) as audio:
                    self.assertEqual((audio.getnchannels(), audio.getframerate()), (1, 16000))
                    self.assertAlmostEqual(audio.getnframes() / 16000, 7.4, delta=0.1)

    def test_uniform_override_spans_range_within_frame_budget(self):
        # A static clip forces the public balanced workflow's uniform fallback.
        static = self.root / "static.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "color=c=blue:size=320x180:rate=10:duration=10", "-c:v", "mpeg4",
                        str(static)], check=True, capture_output=True, timeout=30)
        for dedup, expected in ((False, 3), (True, 2)):
            with self.subTest(dedup=dedup):
                output = self.root / f"uniform-{dedup}"
                args = [sys.executable, "-B", str(SCRIPTS / "watch.py"), str(static),
                        "--subtitles", str(self.captions), "--start", "1.3", "--end", "8.7",
                        "--fps", "2", "--max-frames", "3", "--out-dir", str(output)]
                if not dedup:
                    args += ["--no-dedup"]
                result = subprocess.run(args, capture_output=True, text=True,
                                        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(next(output.glob("watch-*/manifest.json")).read_text(encoding="utf-8"))
                self.assertEqual(len(data["frames"]), expected)
                self.assertTrue(all(f["reason"] == "uniform" for f in data["frames"]))
                self.assertTrue(all(1.3 <= f["timestamp_seconds"] <= 8.7 for f in data["frames"]))
                self.assertAlmostEqual(data["frames"][0]["timestamp_seconds"], 1.3, delta=0.001)
                self.assertGreater(data["frames"][-1]["timestamp_seconds"], 8.5)

    def test_capped_modes_bound_images_during_complete_operation(self):
        real_run = subprocess.run
        for mode in ("balanced", "efficient"):
            for cap in (3, 7):
                with self.subTest(mode=mode, cap=cap):
                    output = self.root / f"bounded-{mode}-{cap}"
                    observed_counts = []
                    def observe_process(command, **kwargs):
                        result = real_run(command, **kwargs)
                        observed_counts.append(len(list(output.glob("watch-*/frames/*.jpg"))))
                        return result
                    with patch("subprocess.run", side_effect=observe_process):
                        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                            result = watch.main([str(self.media), "--detail", mode, "--max-frames", str(cap),
                                                 "--subtitles", str(self.captions), "--no-dedup", "--out-dir", str(output)])
                    self.assertEqual(result, 0)
                    self.assertLessEqual(max(observed_counts), cap)
                    data = json.loads(next(output.glob("watch-*/manifest.json")).read_text())
                    self.assertGreater(data["frames"][-1]["timestamp_seconds"], 8.5)

    def test_efficient_fallback_keeps_requested_fps(self):
        sparse = self.root / "sparse.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "color=c=blue:size=320x180:rate=10:duration=10", "-c:v", "mpeg4", "-g", "1000",
                        str(sparse)], check=True, capture_output=True, timeout=30)
        for fps, expected in (("0.01", 1), ("1", 10)):
            with self.subTest(fps=fps):
                output = self.root / f"sparse-{fps}"
                result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "watch.py"), str(sparse),
                                         "--subtitles", str(self.captions), "--detail", "efficient", "--fps", fps,
                                         "--max-frames", "20", "--no-dedup", "--out-dir", str(output)], capture_output=True,
                                        text=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(next(output.glob("watch-*/manifest.json")).read_text(encoding="utf-8"))
                self.assertEqual(len(data["frames"]), expected)
                self.assertTrue(all(f["reason"] == "uniform" for f in data["frames"]))
                if expected > 1:
                    self.assertGreater(data["frames"][-1]["timestamp_seconds"], 9.8)

    def test_cue_frames_reserve_budget_during_complete_operation(self):
        real_run = subprocess.run
        for mode in ("balanced", "efficient"):
            with self.subTest(mode=mode):
                output = self.root / f"reserved-{mode}"
                counts = []
                def observe_process(command, **kwargs):
                    result = real_run(command, **kwargs)
                    counts.append(len(list(output.glob("watch-*/frames/*.jpg"))))
                    return result
                with patch("subprocess.run", side_effect=observe_process):
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        result = watch.main([str(self.media), "--detail", mode, "--max-frames", "3",
                                             "--timestamps", "2.04,7.04", "--subtitles", str(self.captions),
                                             "--no-dedup", "--out-dir", str(output)])
                self.assertEqual(result, 0)
                self.assertLessEqual(max(counts), 3)
                data = json.loads(next(output.glob("watch-*/manifest.json")).read_text())
                self.assertEqual(data["warnings"], [])
                self.assertEqual(len(data["frames"]), 3)
                pinned = [frame for frame in data["frames"] if frame["reason"] == "transcript-cue"]
                self.assertEqual([frame["requested_seconds"] for frame in pinned], [2.04, 7.04])
                self.assertEqual([frame["timestamp_seconds"] for frame in pinned], [2.1, 7.1])

    def test_cue_uses_decoded_source_time_and_cannot_cross_end(self):
        for label, end in (("cue-inside", "8.7"), ("cue-outside", "2.05")):
            with self.subTest(end=end):
                output = self.root / label
                result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "watch.py"), str(self.media),
                                         "--subtitles", str(self.captions), "--detail", "transcript",
                                         "--start", "2", "--end", end, "--timestamps", "2.04",
                                         "--out-dir", str(output)], capture_output=True, text=True,
                                        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(next(output.glob("watch-*/manifest.json")).read_text(encoding="utf-8"))
                if label == "cue-inside":
                    self.assertEqual(len(data["frames"]), 1)
                    self.assertAlmostEqual(data["frames"][0]["timestamp_seconds"], 2.1, delta=0.001)
                    self.assertEqual(data["frames"][0]["requested_seconds"], 2.04)
                else:
                    self.assertEqual(data["frames"], [])
                    self.assertIn("Some requested cue frames could not be sampled within the requested range.",
                                  data["warnings"])

    def test_capped_cue_coverage_reports_every_omitted_request(self):
        for mode in ("transcript", "balanced", "efficient"):
            for cap in (1, 2):
                with self.subTest(mode=mode, cap=cap):
                    output = self.root / f"cue-coverage-{mode}-{cap}"
                    result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "watch.py"), str(self.media),
                                             "--subtitles", str(self.captions), "--detail", mode,
                                             "--start", "2", "--end", "8.7", "--max-frames", str(cap),
                                             "--timestamps", "2,3,6,7,8.7,10", "--out-dir", str(output)],
                                            capture_output=True, text=True,
                                            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    data = json.loads(next(output.glob("watch-*/manifest.json")).read_text())
                    selection = data["cue_selection"]
                    self.assertTrue(selection["sampling_attempted"])
                    self.assertEqual(selection["requested_seconds"], [2, 3, 6, 7, 8.7, 10])
                    self.assertEqual(selection["in_window_seconds"], [2, 3, 6, 7])
                    self.assertEqual(selection["dropped_out_of_window"], 2)
                    self.assertEqual(selection["dropped_for_budget"], 4 - cap)
                    self.assertEqual(selection["selected_count"], cap)
                    self.assertEqual(selection["sampled_request_seconds"], [2] if cap == 1 else [2, 7])
                    self.assertEqual(len(data["frames"]), cap)
                    self.assertTrue(any("frame budget" in warning for warning in data["warnings"]))
                    self.assertTrue(any("outside the requested range" in warning for warning in data["warnings"]))


if __name__ == "__main__":
    unittest.main()
