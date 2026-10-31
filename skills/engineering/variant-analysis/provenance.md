# Provenance

Adapted from [trailofbits/skills](https://github.com/trailofbits/skills/tree/321ccfe628eca0d314b0ee4eaffcdd8a05639aaf/plugins/variant-analysis/skills/variant-analysis), revision 321ccfe628eca0d314b0ee4eaffcdd8a05639aaf.

Original author: trailofbits. Adaptation: Dominic, updated 2026-10-31.

License for this derivative: CC-BY-SA-4.0; see [LICENSE.txt](LICENSE.txt).
This is a modified version; no upstream endorsement is implied.

Changes: Self-contained direct workflow; no compulsory delegation, plugin command, report template, or CI rule. Includes repeated-operation and reader/writer coverage for cost defects, revisits exclusions after recurring findings, and limits audit claims to inspected paths. Extends lifecycle analysis across owners, phases, and distinct stop causes while distinguishing required bookkeeping and previously committed decisions from fresh admission. Distinguishes externally owned existing resources from managed resources that still need updates, tracing successful initial setup into later reconciliation without adopting unrelated state. Traces cached action identities across retry versus fresh admission, owner retirement/pruning/restart, disappearing in-process acknowledgments, and leaving/returning to the original selection; compares later explicit actions with the current owning validator.
