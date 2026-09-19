# Skills maintenance

- Organize skills as skills/<category>/<skill-name>/. Engineering is one category,
  not the repository's entire scope. Keep skills individually installable.

- Keep each skill narrow and useful. Prefer concrete decision guidance over
  persona prompts, repeated reminders, or compulsory ceremony.
- Use PR findings and review/verification costs to improve skills and maintenance
  guidance when they demonstrate a reusable lesson. Replace conflicting rules;
  check later decision behavior instead of equating more instructions with quality.
- User instructions and the target repository's requirements take precedence.
  Never infer authority to publish, spend, merge, or change external systems.
- Preserve upstream attribution, licenses, fixed revisions and adaptation notes.
  Update `sources.json` and the affected package's `provenance.md` together when
  changing its adaptations; installed packages must retain their own attribution.
  Review upstream changes before updating; never silently replace adaptations.
- Keep private workspace notes, credentials, personal paths and project evidence
  out of this public repository.
- Use Conventional Commits and the configured author and committer.
- Commit at cohesive checkpoints. Review all meaningful changes through ready PRs.
  Include the empty repository bootstrap commit in the initial review's scope.
- Let configured general review run; if absent, request `@codex review`.
  Wait for a requested review before editing, pushing, or requesting another.
  Security-sensitive executable changes require security review after clean general
  review. Do not duplicate an already running review.
- Verify final-head review coverage and applicable checks before merging.
- Validate skill frontmatter, local links, packaged dependencies, attribution, and
  decision behavior. Read instructions and examples as critically as source code.
  Examples must not disclose secrets or silently skip meaningful failure cases.
- Keep mandatory project rules in the target project's AGENTS.md. Do not duplicate
  those rules as competing skill policy.
