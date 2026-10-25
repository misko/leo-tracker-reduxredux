# Archive verification and restoration

The [publication index](publication_index.json) gives exact names, byte sizes,
SHA-256 digests and member inventories for the three new assets. Download them
from the [new-family uncertainty release](https://github.com/misko/leo-tracker-reduxredux/releases/tag/research-ds24-new-family-uncertainty-r01-20261025).
They contain 507 raw preparation/profile/fit records and 36 frozen input files.
No raw IQ, credentials or new RF collection is included.

The compact Git report holds the new source, protocols, tests, audit receipts,
summaries, geographic tables and 14 PNG/PDF files. The archive retains every
raw phase round, endpoint checkpoint, parent gate/ID ledger and endpoint
numerical qualification. The rejected first-order preparation, superseded
zero-run runner and failed initial adaptive-integration audit remain preserved.

## Exact prior dependencies

This report reuses five immutable assets from the
[R1 release](https://github.com/misko/leo-tracker-reduxredux/releases/tag/research-ds24-movement-policy-r01-20261025):
the two `recovery_DS24-*_original.tar.gz` files, the two
`recovery_DS24-*_support_versions.tar.gz` files and
`actual_runtime_source_capsule.tar.gz`. Their exact URLs and digests are in the
index. The unrelated 1.7 GB movement vectors are not dependencies of this pilot.
The prior Git files are bound to commit
`82e608d8d3b254e737326058e601a4775f231135`, not a moving branch.

[runtime_closure.json](audit/runtime_closure.json) maps all 334 actually imported
scientific Python files: 328 exact R1 capsule members, one immutable prior Git
file and five current files. The three previously dirty imported production
files are the exact R1 research snapshots; this publication changes no
production source. Installed third-party packages and their versions are
recorded, but their source distributions are not vendored.

Source restoration alone did not restore the scientific inputs in R1: that
report bound the DS25 frozen banks/tracks/observations by hash without shipping
their bytes. The two new `frozen_inputs_DS24-*.tar.gz` assets close this gap for
these cases. They include the actual causal-prior paths and phase histories,
frozen sky banks, track and observation contracts, saved cavity baselines and
additional declared bindings. [input_closure.json](audit/input_closure.json)
records safe saved-context reads; [publication_dependencies.json](audit/publication_dependencies.json)
adds exact declared parent/target bindings. It maps each original path to a new
archive, reused archive, immutable prior Git file or current report file.

## Verify without running inference

Use Python 3.12 or later. Obtain the exact prior report directory at the commit
above, and download the three new assets and five listed R1 assets into separate
directories. From this report directory run:

```bash
python3 verify_publication.py \
  --assets /absolute/path/to/new-assets \
  --prior-assets /absolute/path/to/r1-assets \
  --prior-report /absolute/path/to/r1-checkout/reports/2026_10_25_ds24_movement_policy \
  --restore /absolute/path/to/new-restored-tree
```

The verifier checks archive sizes and SHA-256, every new member, every required
prior source/input member, the direct report files and immutable prior Git
dependencies. It can restore only the required logical trees into a new
directory. It neither downloads files nor runs propagation, optimization or
geographic selection. Omitting `--restore` performs verification only.

Raw evidence restores under `current/scientific/` and `current/math_audit/`;
new frozen inputs under `current/input/ds25/`; required R1 sources and data under
`prior_r1/`. These paths preserve exact file contents. The dependency manifests
provide the mapping back to historical absolute paths.

## Scientific replay limits and original commands

The frozen research scripts retain historical absolute study/repository roots
and hash-bound launch receipts. They are research snapshots, not a relocatable
production API. Full numerical replay requires an isolated filesystem namespace
or explicit aliases mapping the manifest's original paths to the restored
bytes, plus the recorded third-party environment. Do not overwrite an active
checkout or re-use the published output directories. Protocol receipts are
records of this run, not authorization for a new experiment.

The execution used Python 3.12.14, NumPy 2.5.2, SciPy 1.18.1, Matplotlib 3.11.1,
sgp4 2.27 and Pydantic 2.13.4. Every numerical worker used:

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONDONTWRITEBYTECODE=1
```

The original branch runner was `scientific/execution03.py`, with the
`scientific/`, prior `recovery/`, repository `src/` and `tools/` directories on
`PYTHONPATH`, after the independent receipts and coordinator go were frozen.
It ran exactly 88 fixed profile records and eight fits under protocol03.
The saved outputs can be inspected and their reporting arithmetic checked
without repeating those fits. The phase preflight and source/input closure
programs are separately preserved; their imports are context reconstruction,
not a new localization campaign.

All geographic output is reporting-only on two previously examined examples.
The operational policy remains the exact saved baseline and every new target
association remains unqualified.
