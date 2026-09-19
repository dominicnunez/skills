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
   For lifecycle defects, trace owners and phases from request admission through
   preparation, external calls, and durable completion. Compare distinct stop
   causes and their scopes; a guard for an authority change may not observe
   runtime shutdown. Include admission after a handler returns and the outer
   runtime/transport ordering that invokes the helper under review.
   For repeated-work defects, also trace complete operations, nested calls,
   repeated requests and concurrent callers. Cover reachable readers as well as
   writers. One call per transaction is not an exclusion when every poll starts
   another transaction. Distinguish required offline replay from runtime reuse.
4. Read all relevant matches with callers and guards. Record false positives and
   why they are excluded. Narrow noisy patterns rather than treating matches as
   proof of defects.
5. Confirm each candidate with evidence that a reachable, supported path violates
   the invariant. Check guards at other owning boundaries and the intended contract.
   A missing local guard or an artificial test that bypasses required admission
   does not alone prove a defect. Keep candidates with unproven reachability or
   violated behavior as hypotheses, not confirmed findings.
   Distinguish required stop bookkeeping and completion of an already-committed
   decision from newly admitted work; verify the durable boundary before calling
   a post-cancellation write a bypass.
   For cache costs, establish when reusable state should exist. A permitted cold
   start or eviction is not itself a cache bypass; show unnecessary work under
   the stated conditions or a violated workload/deadline requirement.
6. Audit the complete pattern family before pushing a fix. Handle independent
   confirmed findings under the repository's issue and sequencing rules.
7. Keep a compact record of patterns, scope, confirmed cases, exclusions, and
   remaining proof. Add a regression or automated rule only when it checks a
   meaningful behavior with acceptable false positives.

If a later finding repeats the same cause, revisit the search boundary and the
reason for each exclusion before another local patch. Report which entry points
were inspected; a bounded search supports "none found in these paths," not a
claim that the entire system has no variants.

Work directly unless parallel agent work is separately authorized. This skill
does not require a plugin command, external scanner, or another skill to run.
Use the available repository search tools first.

Source and license: [provenance.md](provenance.md).
