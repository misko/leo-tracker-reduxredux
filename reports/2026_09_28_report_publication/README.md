# Report publication audit

This snapshot publishes the completed local reporting updates for sequence
semantics and DS8/DS9 ARM validation, together with their scripts, numerical
results and receipts. It also publishes the updated DS7/DS8 correspondence
overview and its plot. It does not declare the unresolved header semantics or
sub-kilometre localization research goals complete.

The separate [timing recombination report](../2026_09_28_timing_recombination/README.md)
was already published at `82bce0fcee666caf2863baf452b2d3faa01c3707`, including
284 files and 520 verified evidence bindings. Its 38 scientific processes
completed, with explicit optimizer failures and retained source fallbacks.

## Outstanding reporting updates

| Report | Publication action |
|---|---|
| [ARM validation](../2026_09_28_arm_ds89_validation/REPORT.md) | Publish final result and evidence; replace the obsolete in-progress status. |
| [Full-frame regions](../2026_09_28_sequence_semantics/FULL_FRAME_REGIONS.md) | Publish findings, controls and remaining ambiguities. |
| [Dataset header coverage](../2026_09_28_sequence_semantics/DS789_HEADER_COVERAGE.md) | Publish dataset coverage accounting. |
| [Header block rank](../2026_09_28_sequence_semantics/HEADER_BLOCK_RANK.md) | Publish rank/constraint tests with their limitations. |
| [Local reference parity](../2026_09_28_sequence_semantics/LOCAL_REFERENCE_PARITY.md) | Publish reference comparisons. |
| [Local header recovery](../2026_09_28_sequence_semantics/LOCAL_HEADER_RECOVERY.md) | Publish recovery observations and constraints. |
| [Local header relations](../2026_09_28_sequence_semantics/LOCAL_HEADER_RELATIONS.md) | Publish relationship tests without assigning unsupported field meanings. |
| [DS9 last-visit validation](../2026_09_28_sequence_semantics/DS9_LAST_VALIDATION.md) | Publish later-visit controls, including negative results. |
| Sequence README, semantic checkpoint, short parity and pilot follow-up | Publish the current local revisions and supporting result files. |
| [DS7/DS8 correspondence](../2026_09_28_ds7_ds8_correspondence/README.md) | Publish overview updated to 85 validated words and the matching plot; follow-up evidence is already on main. |

## Verification and boundaries

All 128 paths in the ARM report's existing SHA256SUMS inventory match their
recorded bytes. Its eight historical source hashes also match the local
baseline sources. Four of those sources differ from current remote main;
their exact bytes are archived under this audit's `historical-sources/` so
reproduction does not silently substitute newer implementations. No production
source is overwritten.

All 102 focused tests across the sequence and ARM report directories pass.
The successful command uses an isolated `uv run --no-project` environment with
NumPy, SciPy, h5py and pytest, explicit report-directory/source import paths,
and `--import-mode=importlib`. Earlier test collection attempts failed because
of missing import paths, SciPy or h5py; their logs are retained. No scientific
replay or new radio collection was run to resolve those environment failures.
This is a publication/integrity review, not a new independent replication of
every research result in these reports.

The archive includes report text, scripts, tests, JSON/JSONL numerical results,
logs and figures. Git-ignored binary working inputs (`.npz`, `.npy`, `.ci16`)
remain local, along with the downloaded third-party PDF. They are listed with
hashes and sizes in `local-inputs.json`; they are not claimed to be available
from a clone. The source corpus remains available through the original
read-only storage paths. Historical text describing files as ignored refers
to the working-tree policy; this explicit publication includes the selected
numerical JSON evidence beneath `local/`.

Older local copies of four August/September reports and two RX-geometry
documents differ from main, which already carries later corrections and
follow-ups. They are retained locally and do not replace newer remote reports.
No reports or artifacts already on main are deleted.

`publication-inventory.json` records the exact selected file hashes and the
excluded local-input inventory. `evidence-sha256.json` binds all files in this
audit and every file selected for publication, excluding itself. These are
publication-time bindings; the existing experiment-time seals remain intact.
