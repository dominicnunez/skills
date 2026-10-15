---
name: verification-before-completion
description: Use before commits, review pushes, and claims that a change is fixed, complete, or passing. Check that the evidence covers the actual revision, behavior, and claim.
---
# Evidence before completion claims

For each substantive claim, identify its evidence and practical limits.

- Confirm the checked revision or working-tree content, command, exit status, and
  relevant output. A started or still-running check has not passed.
- Reuse successful checks when the relevant code and environment are unchanged.
  Repeat or broaden them only after changes, failures, or unresolved concerns
  invalidate the evidence. Do not rerun checks merely to accompany a message.
- A focused test supports the behavior it exercises. A linter does not prove a
  build, and a passing package does not prove all requirements or failure paths.
  For tool integrations, verify non-obvious options and settings at the owning
  operation of the pinned real tool, using a permitted fixture. A mock accepting
  those inputs, or a settings readback in another mode or directory, does not
  prove enforcement. When a loader can continue with defaults, inspect its
  diagnostics and effective settings: a zero exit after fallback does not prove
  the supplied configuration was applied. Report the gap if the owning operation
  cannot be exercised.
- For a defect regression, confirm the original symptom fails before the fix and
  passes after it where feasible. Use an isolated checkout or equivalent method
  that preserves user changes.
- For a claimed requirement, compare implementation and evidence against the
  actual acceptance criteria. Report missing proof as missing.
- Before a review push, inspect the full diff, affected callers and applicable
  checks. After review, require coverage of the final head according to the
  repository's rules; prior approvals do not establish later correctness.
- For changes spanning authority, persistence, filtered history or several
  lifecycle owners, use the [contract evidence gate](references/contract-evidence.md)
  before the review push. It turns broad audit claims into inspected boundaries
  and explicit missing evidence. Skip this procedure for documentation-only or
  low-impact mechanical edits.
- Match cost claims to the complete operation and its workload, including
  repetition or concurrency when relevant. State cold/warm conditions and
  remaining growth; a helper benchmark or cache's existence is insufficient.
  Investigate timed-out checks before increasing their budget, separating an
  algorithmic regression from instrumentation overhead or runner variation.
- For evidence handoffs, preserve captured stdout, stderr and exit status when
  needed. For delegated work, save required outputs where the recipient can read
  them and supply the paths before handing work back; the delegate's tool responses
  may be unavailable to the parent. Before storing or sharing, remove secrets and
  private material the destination or recipient is not authorized to receive. Label redactions as
  sanitized and summaries as summaries; retain the observed exit status and
  diagnostic meaning. Never reconstruct output and call it raw or describe
  sanitized evidence as raw. If required evidence is unavailable, report the gap
  and capture it again when needed.
- Treat a subagent's result as scoped evidence. Verify the inspected entry
  points, methods, exclusions and uncertainty before making a broader claim;
  skill use and a clean audit report do not establish untested coverage.
- Keep the user's update brief and accurate. Separate completed, verified work
  from work pending review or checks. Do not claim that installing or validating
  a skill proves it will reduce defects.

Source and license: [provenance.md](provenance.md).
