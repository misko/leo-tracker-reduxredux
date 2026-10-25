# Replay scope and external dependencies

This compact report preserves the new research code, owned tests, frozen
protocols, native-ID and input bindings, completed and failed outputs, saved
figures and independent audits. It is not a standalone restoration of the
original GLRT extraction, radio corpus or historical localization runtime.
No previous report is edited by this iteration. No position optimizer, GPS,
new RF/IQ acquisition or operational association is part of this study.

The publication manifest binds the exact packaged bytes. Scientific seals keep
their original paths and SHA256 digests as provenance; a fresh clone does not
make those absolute paths available. Preserve the original files and remap
paths to byte-identical inputs before any replay. Report writers may refuse
existing outputs, and scientific scripts must not be rerun over sealed files.
The frozen `audit/REVIEW.md` also retains six links relative to its original
research directory. [The external-link map](external_links.json) supplies
verified immutable published targets and matching source hashes; rewriting
that sealed narrative is unnecessary. The main report and cumulative review
use their publication-local or explicit published links.

## Ownership trace and existing prediction overlay

[The ownership findings](ownership/FINDINGS.md) preserve every selected source
ID, all local original probes, native winners, archived candidate records and
original graph memberships. These CSVs and the saved JSON support an independent
readback without orbit propagation or an inference fit. In particular:

- `ownership/native_winners.csv` contains the 162 original winners in the three
  declared windows; `probes.csv` also retains the windows without passing winners.
- `ownership/archived_peaks.csv` contains the archived candidate records with
  ranks, gate flags and same-probe provenance. They are not independent new
  observations, and record counts are not counts of distinct emitters.
- `ownership/graph_points.csv` and `point_provenance.json` bind original lane
  indices, native IDs and quality flags. The complete three-source ID sets are
  retained even when a reporting window shows only part of a source.
- `ownership/prediction_overlay.csv` stores the exact saved-prediction values
  restored to native CFO minus two periods, together with the fixed parent-radio
  offset used in that restoration.

Reconstructing the ownership checks from upstream inputs requires the unchanged
DS24-0013 exports in `/srv/bulk/leo/research/ds25-20261024/DS24-0013`:
`tracking.json`, `observations.json`, `tracks.json`, `prepared.json` and
`input_receipt.json`. These are **DS24 fast-scan inputs** stored in a shared
directory named ds25-20261024. Original accepted-ID membership comes from
`ds24-fast-identifiability-r01/transfer/ownership/DS24-0013/parent.json`.
[protocol02.json](ownership/protocol02.json) binds these exact files and sources.

The original fast adapter is repository
`tools/evaluate_ds22_merged_tracks.py:winners`, using
`src/leo/analysis/glrt_frequency_input.py:frequency_evidence`. It uses the fast
contract's `clock_anchor` and device counters. The adaptive
`public_tracking_points` timing schema is a different contract: the first
preparation failed before processing when it was used here. That preparation,
source, protocol and failure remain preserved. The correction does not change
the frozen windows, winning-peak policy, observations or ownership.

The overlay uses only existing outputs from
`/srv/bulk/leo/research/ds24-ch5-prediction-r01/prediction/run02/{c0,fitted_c}`:
`joint_background.npz` and `Dposterior_GL64.npz`. Their producing code and prior
are documented in the [immutable previous report](https://github.com/misko/leo-tracker-reduxredux/tree/b4de477876ab879c29ef0ef2ffdd0e11339f1349/reports/2026_10_25_ds24_ch5_prediction).
`ownership/overlay_protocol.json` binds both arrays and the original background
construction source. Prediction restoration is
`saved_prediction + graph_CFO - saved_conditional_raw`; it introduces no new
parent fit or witness conditioning. Interpolation at other probe timestamps is
display-only, within saved support. No likelihood is evaluated from it.

Upstream raw tracking authority access was previously permission-limited; this
work reads the already verified exported contract. It does not claim to have
revalidated an inaccessible raw authority or recovered missing IQ.

## Historical support eligibility

[The eligibility findings](eligibility/FINDINGS.md) explain the original
20-second prerequisite without a new source or satellite fit. The extraction
uses `ds25-20261024/DS24-0013/{tracks,result}.json` and the hash-matched historical
`tools/run_algo01_ds23_sample.py`. It extracts and executes only the pure
`selected_supports` index-list function through its syntax tree; it does not
import or run the old CLI. Other historical support gates are not recomputed.

`eligibility/summary.json` preserves all duration tests and source hashes;
`eligibility/report.py` renders its saved metadata to `support_durations.png`.
The duration test is necessary, not sufficient for historical calibration
eligibility. It is not identity evidence or permission to use a short/linear
source to calibrate receiver offset or drift.

## Scientific competing-source comparison

The frozen [scientific protocol](scientific/PROTOCOL.md),
[successful source/input inventory](scientific/run02/protocol.json) and
[implementation](scientific/coherence02.py) define the new calculation. It imports
the previous `ds24-ch5-prediction-r01/prediction/prediction02.py` and that source's
hash-bound context, nonlinear physical-mode and numerical helpers. The preceding
report supplies much of this research source/output evidence; complete GLRT/TLE
input and runtime restoration still requires the external dependencies in the
new protocol. No large unchanged source or input archive is silently recreated.

Every model uses the same complete 57-point discovery plus 43-point witness,
fixed original CH5 cavity/background and saved c0 RF coordinate. Each c arm
retains its own original calibration. The four classes are whole physical,
whole proper polynomial, an edge physical portion with unresolved remainder,
and two-piece unresolved polynomial. Cuts after native W indices 14, 21 and 29
are fixed before the new scores. Six physical-prefix/suffix allocations are
averaged with prior 1/6; three piecewise-polynomial cuts have prior 1/3. This
is not an unpenalized selection of the best-looking prefix. A W alias and owner
constant remain shared across its portions. All 100 observations remain scored.

The phase prior and normalization are unchanged between classes. An archived
discovery-posterior window accelerates computation but is not a replacement
prior or a renormalized domain. Independent quadrature checks, local density
bounds and remote-phase bounds have distinct recorded roles. Window agreement
alone does not prove global order, absolute precision or a calibrated identity.
The original discovery and whole-polynomial calculations are explicit replay
prerequisites. The historical duration/curvature gates remain unchanged.

Each arm's `scientific/run02/{c0,fitted_c}/inputs.npz`, proposal, discovery
replay, cell quadrature/bound checkpoints and terminal result preserve its
execution. The total denominator is 22 cell-arm and eight class-arm slots.
Incomplete slots would remain unresolved. All 22 cells and eight classes
completed in the successful run; its whole-domain class ordering is distinct
from the stronger absolute-score precision test. The frozen cap is 600
cumulative worker-seconds, two workers with one BLAS thread each.

The [first execution](scientific/execution.json) failed before quadrature when
an existing helper's metadata path was referenced through the wrong module.
The original `coherence.py`, protocol and both failure records remain intact.
The separate `coherence02.py` repairs only that path and output/version/budget
bookkeeping. Its [two-arm real-input smoke check](scientific/run02/load_smoke.json)
verifies the exact 100 IDs, raw vector, covariance, RF factors and common
position; eleven owned tests precede the repaired run. The first failure and
smoke time are deducted from the unchanged cap, for 52.710 total worker-seconds.
No input, prior, allocation, tolerance or scientific budget was expanded.

The primary [saved report](scientific/report02/summary.json),
[class table](scientific/report02/class_table.csv) and
[cell table](scientific/report02/cell_table.csv) preserve the result. Its rendering
source is `scientific/report_coherence02.py`; reporting reads saved arrays and
JSON without another scientific score or fit. The independent terminal audit
is [audit/terminal.json](audit/terminal.json). The earlier report and its source
remain unchanged as presentation provenance.

## Historical review figures

`review_figures/` copies two PNG/PDF figure pairs, `figure_data.json` and the
original `make_figures.py` from `ds24-evidence-synthesis-20261025`, without
regeneration or changes. Its [provenance](review_figures/provenance.json) binds
each source path, size and digest. These are historical comparisons, not new
results from the current model. The plotting source remains a reference with
external saved-table dependencies, including that synthesis's fixed diagnostic;
this compact copy is not a complete regeneration closure.

## Recorded environment and reproducibility limits

The research environment is Python 3.12 in
`/home/mouse9911/gits/leo-tracker-reduxredux/.venv`; NumPy comes from that
environment, SciPy from `/tmp/algo03-feasible-deps`, and plots use Matplotlib.
The recorded runtime environment is:

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/tmp/algo03-feasible-deps:/home/mouse9911/gits/leo-tracker-reduxredux/src:/home/mouse9911/gits/leo-tracker-reduxredux/tools
```

Ownership tests were run with `python -B -m pytest -q -p no:cacheprovider`
on `ownership/test_trace.py` and `ownership/test_overlay.py`. Their three
tests check original winner/tie semantics, index/ID ownership and prediction
restoration under witness-value redaction. Source and result verification
does not imply a calibrated satellite-identity or position-accuracy result.

The complete original GLRT/TLE banks and historical runtime tree are not
duplicated in this compact publication. Protocol hashes identify dependencies;
they do not supply missing bytes or establish an executable clean-room replay.
Python caches and staging files are excluded unless an original scientific
seal explicitly binds a tiny metadata artifact, in which case that exact
artifact is retained and documented. The original ownership stdout log was
sealed while empty; emitted stdout is preserved separately and the exact
empty bytes restored with a receipt. No source or scientific result changed.
