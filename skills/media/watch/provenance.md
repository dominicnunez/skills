# Provenance

Adapted from [bradautomates/claude-video](https://github.com/bradautomates/claude-video/tree/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch),
release v0.2.0, revision 83da59fa78c3eee9e20f515fe75c438bb5166efd.
The existing locally installed skill was compared with this release before adaptation.

Original author: Bradley Bonanno (bradautomates). Adaptation: Dominic, 2026-10-07.

License for this derivative: MIT; see [LICENSE.txt](LICENSE.txt).
This is a modified version; no upstream endorsement is implied.

Changes: Codex-compatible video analysis and document guidance; adapts the
upstream frame-selection and VTT parsing helpers. Replaces automatic installers,
configuration/key lookup and cloud transcription with read-only preflight and
optional local audio extraction. Preflight reports unsupported Python and
missing executables in text/JSON/check modes, including the enabled Deno runtime.
Isolates runs and download attempts; disables
yt-dlp configuration, plugins and remote components; limits remote inputs to
HTTPS YouTube hosts and FFmpeg input protocols to local files/pipes. Requires
successful final downloads, validates CLI budgets/ranges, spans uniform frame
budgets across the interval and records range-checked decoded timestamps.
Capped scene/keyframe selection counts candidates without JPEGs, then renders
only selected indices with bounded selection memory. The extra decode pass
trades CPU for bounded scratch storage. Uniform sampling preserves first/last
coverage, honors explicit FPS in both fallbacks, and retains endpoints during
deduplication. Native tests use built-in MPEG-4/AAC encoders.
Uses current FFmpeg timing options; supports short and long WebVTT cue times
and keeps audio extraction independent of frame failures. Cue frames retain
their requested time separately from the decoded, range-checked source time.
Range selection uses half-open boundaries for captions/cues, preserves caption
millisecond precision, finite positive cue intervals and identical rolling-cue
unions without moving added words earlier, and records all cue requests
with explicit range/budget omissions and sampling state, including media failure.
Adds saved evidence reports/manifests, supplied-caption support, caption-language
selection, partial-evidence preservation and offline contract tests.
Remote media admission requires a finite section of at most 30 minutes;
unknown durations need an explicit end and live streams are refused. Downloads
use FFmpeg section seeking, accurate MP4/AAC re-encoding, explicit duration and
256 MiB output-size guards with packet flushing, and reject media reaching that
size or empty/truncated sections without falling
back to a full download. Frame/cue/audio consumers translate between section
local time and source time; manifests retain the downloaded source range.
Refusal and failed-download paths retain known source metadata; the caption
publication boundary clamps every remote range to the known source end.
Shared display rendering visibly encodes C0/C1/DEL controls in reports,
transcripts, parser messages, tool logs and media failure diagnostics. Diagnostic
streaming requests UTF-8 Python output and uses bounded UTF-8 chunks; malformed
bytes become replacements. Machine JSON retains source values through
escapes. Original caption/media evidence is preserved.
These guards bound media output rather than total transport bytes or elapsed
time; FFmpeg can slightly overshoot its size guard during closing.

The repository's [sources.json](https://github.com/dominicnunez/skills/blob/main/sources.json)
records the upstream skill, helper and license SHA-256 hashes. The upstream
Whisper API clients, configuration reader and automatic installer are omitted.
