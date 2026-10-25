# Evidence replay and publication scope

This is a compact research report, not a standalone restoration of the radio
corpus or historical runtime. It contains the new code, owned tests, frozen
protocols, native-ID/array bindings, all completed and failed outputs, saved
diagnostics and independent audit receipts. It adds no position fits, RF/IQ
processing, operational associations or ALGO release.

The publication manifest inventories exact report bytes. Branch protocols and
seals retain their original absolute paths and SHA256 bindings; those paths are
provenance, not a claim that they exist in a fresh clone. The package excludes
Python caches except five tiny pytest metadata files explicitly bound by the
first failed-run RF seal, and excludes the publication staging directory. It does not duplicate
large unchanged external input or runtime trees.

## Three distinct replay levels

1. Tables and figures can be checked against the archived JSON, CSV and NPZ
   outputs, without new propagation, likelihood evaluation or GPS. Primary
   reports are [prediction findings](prediction/FINDINGS.md),
   [active-parent findings](parent_coupling/FINDINGS02.md) and
   [archival provenance](mechanism/FINDINGS.md). Their reporting sources are
   `prediction/report.py`, `prediction/report02.py`,
   `prediction/plot03.py`, `parent_coupling/report02.py` and
   `mechanism/archive_provenance.py`. The last source also reads historical
   inputs to establish the provenance, so its saved summary is the portable
   evidence for that check.
2. Replaying numerical evidence or the active-parent probes requires the
   exact external sources and scan inputs in the frozen protocols. Preserve
   the original directory layout, verify every binding, and use a separate
   output root: scientific writers deliberately refuse to overwrite outputs.
   Regenerating a report can also require remapping absolute seal paths to the
   identical archived bytes. Merely cloning this report does not satisfy those
   requirements or reproduce the scientific calculations.
3. Reconstructing the original graph/GLRT extraction or baseline position
   inference requires their earlier public input contracts and processing
   dependencies. That processing is not part of this report. Raw IQ, full TLE
   banks and all historical tracking inputs are not republished here.

## Exact local dependencies

The experiments ran from `/srv/bulk/leo/research/ds24-ch5-prediction-r01`, using
Python 3.12 in `/home/mouse9911/gits/leo-tracker-reduxredux/.venv`. The environment
used one BLAS thread per worker and:

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/tmp/algo03-feasible-deps:/home/mouse9911/gits/leo-tracker-reduxredux/src:/home/mouse9911/gits/leo-tracker-reduxredux/tools
```

NumPy is supplied by that environment and SciPy by
`/tmp/algo03-feasible-deps`. Matplotlib is needed for report generation.
The authoritative dependency inventories are
[the repaired prediction protocol](prediction/run02/protocol.json) and
[the active-parent protocol](parent_coupling/protocol.json), including actual
source hashes. Files in the shared `ds25-20261024` research directory are
**DS24 fast-scan inputs**, not evidence that this report evaluates a new DS25
cohort. The experiments also depend on the unchanged recovery/context and
numerical-support helpers in earlier research directories.

The prediction source imports the preceding RX2 scientific implementation at
`/srv/bulk/leo/research/ds24-rx2-witness-r01/scientific/witness02.py`, its original
CH5 candidate-union cavity, owner metadata and source arrays. The corresponding
[immutable published report](https://github.com/misko/leo-tracker-reduxredux/tree/392faed8c5119279c832a56443aae77d76eb090e/reports/2026_10_25_ds24_rx2_witness)
provides the earlier code and output evidence, with its own stated input limits.
The active-parent source additionally uses the existing RF information records
in `ds24-bottlenecks-20261024/information`, the family-cavity reference in
`ds25-20261024`, recovery helpers in `ds24-movement-policy-r01/recovery` and
visibility helpers in `ds24-identity-support-r01/scientific`. No reference
repository becomes a production runtime dependency through this research.

## Preserved failures and numerical qualifications

The first prediction preparation/run and its output-stem exception are retained.
The separately frozen `prediction02.py` changes the output-port string
conversion and charges the first run's worker time to the original 600-second
budget. Both CH4 final-reference timeouts remain unavailable; their primary
checkpoints are not promoted into completed comparisons. Ordering bounds,
absolute-score precision and posterior-moment stability are separate flags.

The active-parent branch retains the exact empty sealed `execution.log`, its
actual final stdout separately and the restoration receipt. Reporting version02
only improves tick readability; its original capsule and figure remain intact.
Its integration checks concern resolved conditional modes, not a proof that
all remote nonlinear modes have been found. The frozen-Gamma conditional Normal
comparison is not the full production hierarchical Student/VI evidence.

## Correction and immutable originals

The [provenance correction](mechanism/FINDINGS.md) withdraws the attribution of
the archived 2,442.510 Hz residual to a regenerated 57450 fit. It does not alter
the earlier catalogue/evidence calculations. Three Markdown notices are added
to the earlier published report; no sealed local study file, scientific array,
score, old manifest or old seal is changed.

[Original bindings](correction/original_bindings.json) and the
[annotation receipt](correction/annotation_receipt.json) identify exact original
and annotated hashes. Original Markdown is copied under
`correction/prior_at_392faed8/` for byte preservation. Its relative links retain
their original context and should be followed at the linked immutable commit.
The earlier publication manifest and seals apply to commit
`392faed8c5119279c832a56443aae77d76eb090e`, not the later annotated Markdown.
