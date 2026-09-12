# Go backend security checks

Use this as a focused source map, not a complete security standard or a new CI
policy. Confirm the target Go version and actual deployment before a finding.

- Process execution: Go's os/exec does not invoke a shell by default. Separate
  arguments avoid shell parsing, but the selected executable can still interpret
  flags or dangerous arguments. Check executable selection, the argument contract,
  and explicit shell invocation independently.
  [Go os/exec](https://pkg.go.dev/os/exec)
- HTTP bounds: a zero Server.MaxHeaderBytes uses DefaultMaxHeaderBytes (1 MiB);
  it does not mean unlimited headers. Header limits do not bound request bodies.
  Evaluate effective limits, deadlines, resource usage and workload together;
  choose explicit settings when the application needs a different bound.
  [Go net/http Server](https://pkg.go.dev/net/http#Server)
- Dependency and race checks: use the repository's existing verification
  requirements. Propose additional scanners or CI gates only when their value and
  adoption are in scope; this skill does not mandate installing them.
- Browser-facing headers: use the companion
  [browser checks](javascript-general-web-frontend-security.md) for CORS and CSP.
  Do not treat a missing explicit setting as a vulnerability without evaluating
  the effective behavior and relevant threat.

For an actual security change, consult official documentation for each affected
API and verify the invariant through the application's real entry points.
Keep claims narrower than their evidence.
