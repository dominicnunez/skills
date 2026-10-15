# Provenance

Adapted from [mattpocock/skills](https://github.com/mattpocock/skills/tree/3cca18b368ae95cdbdebbff572ccafa662551015/skills/engineering/tdd), revision 3cca18b368ae95cdbdebbff572ccafa662551015.

Original author: mattpocock. Adaptation: Dominic, updated 2026-10-15.

License for this derivative: MIT; see [LICENSE.txt](LICENSE.txt).
This is a modified version; no upstream endorsement is implied.

Changes: Infers authorized test boundaries; permits contract-relevant durable state and forbidden-call assertions; avoids forced approvals and unavailable skill dependencies. Adds ordered-history corruption cases and complete-operation growth checks for relevant workloads, preserving cache correctness and avoiding universal scale-test requirements. Covers lifecycle phases through durable completion and tests cancellation through the owning runtime or transport, preserving required accounting and committed decisions. For container or privilege transport doubles, prevents privileged production shell payloads from running on the host, distinguishes command fakes from isolation, and permits typed unprivileged helpers with private paths or permitted real isolation while retaining direct tests of unprivileged scripts and harmless commands.
