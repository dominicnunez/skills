# Skills maintenance

- Organize skills as skills/<category>/<skill-name>/. Engineering is one category,
  not the repository's entire scope. Keep skills individually installable.

- Keep each skill narrow and useful. Prefer concrete decision guidance over
  persona prompts, repeated reminders, or compulsory ceremony.
- Preserve upstream attribution, licenses, fixed revisions and adaptation notes.
  Update `sources.json` and the affected package's `provenance.md` together when
  changing its adaptations; installed packages must retain their own attribution.
  Review upstream changes before updating; never silently replace adaptations.
- Validate skill frontmatter, local links, packaged dependencies, attribution, and
  decision behavior. Read instructions and examples as critically as source code.
  Packages and examples must not disclose secrets or private project data, or
  silently skip meaningful failure cases.
- Keep project-specific mandatory rules out of reusable skills.
