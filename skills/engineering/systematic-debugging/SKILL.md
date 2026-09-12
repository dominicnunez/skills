---
name: systematic-debugging
description: Use for reproducible bugs, failing tests, unexplained runtime behavior, or performance regressions before choosing a fix. Trace evidence to the owning boundary and test a specific cause.
---
# Root-cause debugging

1. Read the complete relevant error and establish a focused reproduction.
   Record the tested revision, environment, trigger, observed behavior, and
   expected behavior. Distinguish failure to reproduce from proof of absence.
2. Inspect recent changes and a working comparison. Trace the affected data and
   control flow across entry points, callers, durable writes, and recovery.
   Determine where the invariant first becomes false.
3. State one causal hypothesis with evidence. Test the smallest discriminating
   experiment. A failed hypothesis requires reassessment, not another speculative
   patch stacked on top.
4. Add a regression that fails for the demonstrated defect, fix the root cause
   across required callers, and verify the relevant behavior and failure paths.
   Use the installed tdd and verification-before-completion skills as applicable.
5. Search for other instances of the confirmed pattern using variant-analysis
   where appropriate. Keep independent defects under the repository's issue policy.

Instrument only the boundaries needed to distinguish hypotheses. Record redacted
types, sizes, state transitions, identifiers safe for the task, and boolean
credential-presence checks when necessary. Never dump environment variables,
tokens, credentials, complete model context, or private payloads.

Several failed fixes are a reason to revisit assumptions and architecture.
Continue read-only diagnosis within the authorized scope; ask for a decision only
when the evidence calls for a material scope change or missing user information.
Do not treat a fixed attempt count as proof that the architecture is wrong.

For intermittent failures, use explicit synchronization or a bounded condition
check instead of arbitrary sleeps. Distinguish test synchronization from
production deadlines. Keep useful diagnostic evidence outside published source
unless the product needs the observability.

Source and license: [provenance.md](provenance.md).
