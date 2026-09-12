---
name: property-based-testing
description: Use when parsers, serializers, validators, normalizers, or state transitions have meaningful rules to test across generated inputs, or when reviewing a property test that may assert too little.
---
# Test a rule across inputs

Find an independent property before introducing a generator. Good candidates
include roundtrips, idempotence, equivalence to a separate reference model,
ordering rules, and state invariants. Prefer examples when no meaningful
property exists; do not restructure unrelated code to manufacture one.

- Ensure the property can distinguish an incorrect implementation. Recomputing
  the same algorithm is a tautology; rejecting almost every input can make a
  passing test vacuous.
- Generate valid structured inputs directly. Explicitly seed known boundary
  cases so they run reliably rather than depending on chance.
- For invalid inputs, assert the documented rejection and absence of forbidden
  effects, not just lack of a crash.
- Keep a minimal reference state model independent of the production transition
  code. Compare both outputs and relevant durable effects for operation sequences.
- Shrink counterexamples, reproduce them deterministically, and check whether the
  property or implementation is wrong before changing production code.
- Use existing tools. Go's standard testing and fuzz facilities can exercise
  suitable properties without adding a library. A new third-party test dependency
  requires the project's normal dependency decision and authorization.
- Bound time, operation counts, and retained corpus size. Random generation
  complements deterministic regression and concurrency tests.

For stateful systems, useful candidate properties include tenant isolation,
rejection of a stale revision after a newer state, and recovery preserving the
same admitted state. These are candidate contracts to confirm, not universal
requirements invented by the skill.

Source and license: [provenance.md](provenance.md).
