# Provenance

Adapted from [obra/superpowers](https://github.com/obra/superpowers/tree/b36e0829c6d0140e93cfef2ca599b1b07d4a7797/skills/verification-before-completion), revision b36e0829c6d0140e93cfef2ca599b1b07d4a7797.

Original author: obra. Adaptation: Dominic, updated 2026-10-14.

License for this derivative: MIT; see [LICENSE.txt](LICENSE.txt).
This is a modified version; no upstream endorsement is implied.

Changes: Allows valid unchanged evidence reuse; distinguishes focused proof from full completion; preserves final-head review requirements. Matches cost claims to complete workloads, requires timeout diagnosis before budget changes, and treats delegated audit results as scoped evidence. Adds a conditional contract-evidence gate for cross-boundary changes: independent identity channels, source/cache proof, comparable measurements, independent coverage audit, and explicit hold decisions for missing evidence. Requires evidence handoffs to preserve captured stdout, stderr, and exit status when needed; remove secrets and private material the storage destination or recipient is not authorized to receive; label redactions as sanitized and summaries as summaries while retaining the observed exit status and diagnostic meaning; never reconstruct output and call it raw or describe sanitized evidence as raw; and report missing required evidence with a fresh capture only when needed. Requires non-obvious tool options and settings to be verified at the owning operation of the pinned real tool in a permitted fixture; mocked acceptance and settings readback in another mode or directory do not prove enforcement, and unavailable operation evidence remains an explicit gap.
