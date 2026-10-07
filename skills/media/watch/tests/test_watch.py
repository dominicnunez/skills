"""Offline contract checks; no video services or transcription APIs are called."""
import contextlib
import io
import json
import os
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
import watch
from transcribe import parse_vtt


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
                with patch("download.subprocess.run") as run:
                    run.return_value = subprocess.CompletedProcess([], 1)
                    with self.assertRaises(SystemExit):
                        download.download_url("https://youtu.be/new-video", output)

    def test_merge_component_is_not_a_completed_download(self):
        with tempfile.TemporaryDirectory() as folder:
            def incomplete(command, **kwargs):
                template = command[command.index("-o") + 1]
                Path(template.replace("%(ext)s", "f137.mp4")).write_bytes(b"component")
                return subprocess.CompletedProcess(command, 0)
            with patch("download.shutil.which", return_value="yt-dlp"):
                with patch("download.subprocess.run", side_effect=incomplete):
                    with self.assertRaises(SystemExit):
                        download.download_url("https://youtu.be/example", Path(folder))


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
        pattern = "color=c=black:size=320x180:rate=10:duration=10,drawbox=color=white:x=0:y=0:w=iw:h=ih:t=fill:enable='lt(mod(t,0.4),0.2)'"
        subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                        "-f", "lavfi", "-i", pattern, "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
                        "-c:v", "libx264", "-g", "10", "-sc_threshold", "0", "-c:a", "aac",
                        "-shortest", str(cls.media)], check=True, capture_output=True, timeout=30)
        cls.captions = cls.root / "captions.vtt"
        cls.captions.write_text("WEBVTT\n\n00:00.000 --> 00:01.000\nExcluded opening\n\n"
                                "00:02.000 --> 00:03.000\nIn-range evidence\n\n"
                                "00:09.000 --> 00:10.000\nExcluded ending\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

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
                        "-i", "color=c=blue:size=320x180:rate=10:duration=10", "-c:v", "libx264",
                        str(static)], check=True, capture_output=True, timeout=30)
        output = self.root / "uniform"
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "watch.py"), str(static),
                                 "--subtitles", str(self.captions), "--start", "1.3", "--end", "8.7",
                                 "--fps", "2", "--max-frames", "3", "--no-dedup", "--out-dir", str(output)],
                                capture_output=True, text=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(next(output.glob("watch-*/manifest.json")).read_text(encoding="utf-8"))
        self.assertEqual(len(data["frames"]), 3)
        self.assertTrue(all(f["reason"] == "uniform" for f in data["frames"]))
        self.assertTrue(all(1.3 <= f["timestamp_seconds"] <= 8.7 for f in data["frames"]))
        self.assertGreater(data["frames"][-1]["timestamp_seconds"], 6.0)

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
                    self.assertTrue(any("cue frames" in w for w in data["warnings"]))


if __name__ == "__main__":
    unittest.main()
