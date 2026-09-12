---
name: variant-analysis
description: Use after a confirmed defect to find other occurrences of the same cause across callers, storage, recovery, and alternate entry points. Does not turn speculative similarities into findings.
---
# Find related defects

1. State the demonstrated root cause and violated invariant. Identify the
   enabling inputs, operation, missing check, and relevant execution context.
2. Establish an exact search that finds the known instance. If it has already
   been fixed, calibrate against the prior revision and search current code for
   related cases. Do not assume a search is valid because it returns nothing.
3. Expand one dimension at a time: related identifiers, other callers, inverse
   boolean conditions, absent metadata, alternate composition, retry or replay.
   Ground expansion in identifiers and interfaces that actually exist.
4. Read all relevant matches with callers and guards. Record false positives and
   why they are excluded. Narrow noisy patterns rather than treating matches as
   proof of defects.
5. Confirm each candidate with evidence that a reachable, supported path violates
   the invariant. Check guards at other owning boundaries and the intended contract.
   A missing local guard or an artificial test that bypasses required admission
   does not alone prove a defect. Keep candidates with unproven reachability or
   violated behavior as hypotheses, not confirmed findings.
6. Audit the complete pattern family before pushing a fix. Handle independent
   confirmed findings under the repository's issue and sequencing rules.
7. Keep a compact record of patterns, scope, confirmed cases, exclusions, and
   remaining proof. Add a regression or automated rule only when it checks a
   meaningful behavior with acceptable false positives.

Work directly unless parallel agent work is separately authorized. This skill
does not require a plugin command, external scanner, or another skill to run.
Use the available repository search tools first.

Source and license: [provenance.md](provenance.md).
