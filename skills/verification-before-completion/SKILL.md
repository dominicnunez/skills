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
- For a defect regression, confirm the original symptom fails before the fix and
  passes after it where feasible. Use an isolated checkout or equivalent method
  that preserves user changes.
- For a claimed requirement, compare implementation and evidence against the
  actual acceptance criteria. Report missing proof as missing.
- Before a review push, inspect the full diff, affected callers and applicable
  checks. After review, require coverage of the final head according to the
  repository's rules; prior approvals do not establish later correctness.
- Keep the user's update brief and accurate. Separate completed, verified work
  from work pending review or checks. Do not claim that installing or validating
  a skill proves it will reduce defects.

Source and license: [provenance.md](provenance.md).
