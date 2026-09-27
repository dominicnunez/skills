# Contract evidence before review

Use this for changes where a local fix can leave another reader, lifecycle phase,
or selection path inconsistent. This is a decision gate, not a larger test quota.
Keep the evidence with the task's working notes, following repository policy.

## Establish the contract independently of the patch

Write each changed invariant in observable terms. Derive its rules from the
owning writer, authoritative validator, storage constraints and public caller;
do not derive the expected behavior only from the proposed implementation.
For each invariant record:

| Invariant | Owners and entry points | Independent failure cases | Evidence at revision | Decision |
| --- | --- | --- | --- | --- |
| Concrete behavior | Inspected symbols or paths | Cases derived from the contract | Test, experiment or code trace and limits | Proven, contradicted, missing, or inapplicable with reason |

One row may cover several equivalent cases if the equivalence is explained.
An excluded path needs a scope or contract reason; absence from the diff is not
one. Existing successful evidence is reusable when relevant code is unchanged.

## Follow candidates before validating them

For filtered readers, inventory every independent identity channel that can
make retained evidence relevant: envelope fields, typed payloads, record keys,
record bodies and reverse references. Determine whether each identity is global
or tenant-scoped from its owner, not its spelling. Compare the selected set with
the full validator before relying on that validator to reject bad evidence.

Exercise independent loss or inconsistency of the channels the contract owns,
both traversal directions, and an unrelated-history control. Include relevant
duplicate, absent and forbidden metadata; a check on selected rows cannot prove
that omitted rows were unrelated. Preserve valid history semantics when indexing:
candidate predicates, multiplicity, order, time boundaries and foreign claims.

For cached or derived evidence, separately prove source correctness, selection
completeness and freshness. Guard definitions do not prove continuous guard
installation or correct cache contents. State the trusted-storage assumptions.

## Measure the complete operation

For cost-sensitive changes, vary the number of actual operations as well as
supporting history. Distinguish unrelated history from work inherently required
by a selected dependency or candidate set. Use the same fixture, code baseline,
runtime and benchmark settings for before/after comparisons; exclude setup only
when that matches the claimed operation, and record its cost separately.

A helper benchmark cannot establish public-operation improvement. A theoretical
complexity concern is not a measured regression. Report latency and allocation
changes at the tested sizes; do not call a change an optimization when those
measurements regress without an explicit, justified tradeoff. Investigate the
cause before adding indexes, caches, larger timeouts or narrower fixtures.

## Audit the evidence, then decide

For a high-risk cross-boundary change, obtain an independent pass over the raw
contract, sources and tests when delegation is available and authorized. Ask the
reviewer to identify missing or contradicted rows, not merely inspect the patch
for obvious bugs. Do not seed it with the implementer's conclusions. Its output
must identify inspected paths and exclusions; a clean response is not coverage.

Before a ready review push, required rows must be supported or explicitly
inapplicable for a defensible reason. Missing or contradicted required evidence
holds the push while work continues; it does not require additional user approval
or prohibit logical local commits. Do not remove a requirement to make the table
green. Track genuinely separate defects under the repository's issue policy.

After an external finding, map it to the missed boundary or evidence row and
correct that gap before pushing again. Record whether the next review repeats
that class. Judge the procedure by prevented misses and verification cost, not
by the number of instructions, tests, reviewers or green checkmarks added.
