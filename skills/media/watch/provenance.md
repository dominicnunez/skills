# Provenance

Adapted from [bradautomates/claude-video](https://github.com/bradautomates/claude-video/tree/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch),
release v0.2.0, revision 83da59fa78c3eee9e20f515fe75c438bb5166efd.
The existing locally installed skill was compared with this release before adaptation.

Original author: Bradley Bonanno (bradautomates). Adaptation: Dominic, 2026-10-07.

License for this derivative: MIT; see [LICENSE.txt](LICENSE.txt).
This is a modified version; no upstream endorsement is implied.

Changes: Codex-compatible video analysis and document guidance; retains the
upstream frame-selection and VTT parsing helpers. Replaces automatic installers,
configuration/key lookup and cloud transcription with read-only preflight and
optional local audio extraction. Isolates runs and download attempts; disables
yt-dlp configuration, plugins and remote components; limits remote inputs to
HTTPS YouTube hosts and FFmpeg input protocols to local files/pipes. Requires
successful final downloads, validates CLI budgets/ranges, spans uniform frame
budgets across the interval and records range-checked decoded timestamps.
Uses current FFmpeg timing options; supports short and long WebVTT cue times
and keeps audio extraction independent of frame failures. Cue frames retain
their requested time separately from the decoded, range-checked source time.
Adds saved evidence reports/manifests, supplied-caption support, caption-language
selection, partial-evidence preservation and offline contract tests.

The repository's [sources.json](https://github.com/dominicnunez/skills/blob/main/sources.json)
records the upstream skill, helper and license SHA-256 hashes. The upstream
Whisper API clients, configuration reader and automatic installer are omitted.
