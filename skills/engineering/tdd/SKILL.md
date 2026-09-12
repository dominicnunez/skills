---
name: tdd
description: Use when implementing behavior changes or fixing bugs that need regression tests. Builds one meaningful failing test and a small implementation slice at a time; skips documentation-only and low-impact mechanical edits.
---
# Behavior-first tests

Identify the behavior and the real boundary that owns it. Infer test boundaries
from the authorized task, public contracts, and existing tests. Ask only when a
material product decision remains unresolved.

1. Write one test for an observable requirement, using an independent expected
   result. For an existing API, confirm it fails for the intended behavioral
   defect rather than broken setup. For an intentionally new API, a missing-symbol
   compile failure can establish the initial red state; add only the minimal
   declaration, then demonstrate a behavior-level failure before implementing
   the behavior. Unrelated compilation or fixture failures are not useful proof.
2. Implement the smallest complete behavior slice across its necessary callers.
   Do not omit a caller just to keep a patch small.
3. Run the focused check, inspect its result, then repeat for the next behavior.
   Refactor once behavior is protected; preserve appropriate verification.
4. Exercise realistic failures, identity boundaries, cancellation, recovery and
   persistence where the change affects them. A successful happy path is not
   proof that denied work produces no side effects.

Prefer real entry points and a real temporary database when persistence matters.
Inspect durable state or count forbidden calls when these are part of the
contract (for example, no spend after denial or no write before authorization).
Avoid assertions on incidental implementation details.

Test doubles must implement the actual production interfaces and failure
semantics. Prefer doubles at external boundaries; use internal fault injection
only when needed to expose an otherwise inaccessible failure.

Do not recompute the implementation as the expected answer. Avoid tests that
pass only because they duplicate the algorithm. Use documented examples, a
separate reference model, or relationships the implementation could violate.

Use the repository's existing test tools and meaningful regression requirements.
Do not add a dependency, coverage quota, or exhaustive suite just to follow this
skill. Record unproven behavior honestly.

Source and license: [provenance.md](provenance.md).
