---
name: security-best-practices
description: Use for authorized secure coding or security review in Go backends and JavaScript or TypeScript frontends. Apply framework-specific guidance to the actual trust boundary and deployment model.
---
# Secure coding guidance

Identify the languages, frameworks, trusted entry points, and deployment
assumptions in the authorized change. Read the matching references in
references/; this package includes Go backend and general browser guidance.
Load both only when both are in scope. For unsupported frameworks or languages,
consult their official documentation instead of inventing specific rules.

Use the guidance to prevent or remediate demonstrated problems at the boundary
that owns the security rule. Treat reference recommendations as context-dependent
guidance: confirm reachability, data sensitivity, existing controls, and
compatibility before proposing a change.

- Keep work focused on the authorized defensive outcome and relevant technical
  detail. Do not disguise requests or attempt to bypass safeguards.
- Check all supported callers of the affected rule, including direct composition,
  recovery, and replay when present.
- Test rejection and absence of forbidden effects as well as successful behavior.
  Preserve necessary audit evidence and distinguish local cancellation from
  confirmed reversal of an external action.
- Do not report a missing optional capability or a deployment assumption as an
  exploitable path without evidence. State prerequisites and uncertainty.
- Follow existing authorization for fixes and issue handling; do not ask again
  merely because a skill was invoked. Ask when a material scope or product
  decision is actually missing.
- Preserve the repository's threat-model format and update requirements. Do not
  create a competing threat model or a separate authoritative vulnerability list.
- Local use of this skill is not the independent security review required by the
  repository. Keep general/security review ordering and wait rules intact.

For an explicitly requested report, use the requested destination and naming
convention, cite exact code locations and concrete effects, and distinguish
confirmed findings from hypotheses. Keep private diagnostics out of tracked
files unless the user intentionally approves a sanitized deliverable.

Source and license: [provenance.md](provenance.md).
