# New evidence verification and replay dependencies

The [publication index](publication_index.json) lists all new code, compact
results/figures and three raw-evidence assets with exact byte sizes, SHA-256
digests and member inventories. Download those assets from the
[fast-identifiability release](https://github.com/misko/leo-tracker-reduxredux/releases/tag/research-ds24-fast-identifiability-r01-20261025).
The archive includes every new synthetic generation/round/endpoint record,
transfer ownership/preflight/fit record and direct receiver-contrast native-ID
ledger. No raw IQ, new RF or credentials are included.

From this report directory, use Python 3.12 or later:

```bash
python3 verify_publication.py --assets /absolute/path/to/release-assets \
  --restore /absolute/path/to/new-restored-evidence
```

The standard-library verifier checks every direct report file, archive size,
archive SHA-256 and every decoded member. It restores exact relative paths into
a new directory and runs no inference. Omit `--restore` to verify only. Combine
the resulting raw subtrees with the Git report for saved-output inspection.

## What numerical replay still requires

This is a compact new-evidence publication, not a new full runtime/input capsule.
[input_bindings.json](input_bindings.json) preserves each branch's exact declared
protocol source/input hashes. The original frozen local DS25 corpus paths,
causal banks, tracks, observations, noise maps and original saved parent masks
remain numerical-replay prerequisites. The synthetic generating draws, per-ID
noise and observation hashes are archived; reconstructing their CFO values
requires the original banks and source geometry.
The 24 original sky banks and broad old source trees are not duplicated here.

The prior research sources/provenance are available from immutable reports at:

- R1 commit `82e608d8d3b254e737326058e601a4775f231135`,
  [movement/recovery report](https://github.com/misko/leo-tracker-reduxredux/tree/82e608d8d3b254e737326058e601a4775f231135/reports/2026_10_25_ds24_movement_policy),
  including the exact runtime source capsule in its release.
- R2 commit `7c11ca70240bbb029c2cb070992f3baa2979f288`,
  [new-family uncertainty report](https://github.com/misko/leo-tracker-reduxredux/tree/7c11ca70240bbb029c2cb070992f3baa2979f288/reports/2026_10_25_ds24_new_family_uncertainty),
  including the nonlinear adapter and two previously supplied 0095/0087 input
  sets. Those two sets do not restore all 24 scans used in this wave.

The branch protocols name the exact hashes and historical absolute locations.
No new runtime import discovery campaign was performed for packaging, and this
guide does not claim all original external inputs are newly redistributed.
Use isolated path aliases or a filesystem namespace to map exact frozen bytes;
do not overwrite an active production checkout or published output directory.
Frozen launch receipts describe this completed run, not authorization for a
fresh experiment.

The numerical environment is recorded in the branch protocols. The executed
research used repository `.venv/bin/python -B`, the pre-existing SciPy dependency
path `/tmp/algo03-feasible-deps`, and the named research/repository `PYTHONPATH`
roots. Numerical workers set `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1`. Preserve these settings for bounded
replay. The direct receiver contrast program itself imports only NumPy/SciPy
and reads its explicit archived-contract inputs.

All source and scientific versions remain unchanged. The superseded transfer
geographic plot is retained as provenance; the `geographic_transfer_caption02`
version is the primary view with corrected hatching semantics. No new ALGO or
operational position is promoted by this publication.
