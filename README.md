# Skills

Reusable Codex skills organized by category. Engineering is the first category;
additional categories can be added as useful workflows emerge. These are personal
adaptations, not official releases or endorsements by their upstream authors.

## Engineering

| Skill | Use it for |
| --- | --- |
| tdd | Small behavior-first red/green test cycles |
| systematic-debugging | Reproducing failures and establishing their root cause |
| property-based-testing | Testing meaningful rules across generated inputs |
| variant-analysis | Finding other instances of a demonstrated defect |
| security-best-practices | Authorized secure coding and security reviews |
| verification-before-completion | Matching completion claims to verified evidence |

Repository instructions and the user's authorization remain authoritative.
Skills do not replace required PR reviews, authorize external actions, or grant
permission to spend money. Load only skills relevant to the current work.

Use `skills/<category>/<skill-name>/` for each skill. Install individual skill
directories, not a category directory, using Codex's Skill Installer.
The initial skills are under `skills/engineering/`.
The directories include their own licenses and provenance so they remain
attributed when installed individually.

See [sources.json](sources.json) for fixed upstream revisions, source hashes, and
the adaptation record. Updates should compare upstream changes with those
revisions and preserve local decisions; do not overwrite adaptations blindly.

The contents of each skill retain the license named in its `provenance.md`.
In particular, Trail of Bits derivatives remain CC-BY-SA-4.0 and OpenAI
derivatives remain Apache-2.0. Original repository documentation is MIT-licensed.
