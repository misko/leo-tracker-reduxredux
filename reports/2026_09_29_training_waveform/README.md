# Training-selected waveform frequency prototype

Long-pilot fitting predicts held pilot symbols better than the matched short-pilot
fit on **16/18 excerpts**, but improves over cached acquisition frequency on only
**11/18**. Improvements are concentrated in DS8. Keep this as a research candidate;
there is no demonstrated Doppler-truth or localization improvement.

All 18 frozen selections were recovered: nine recordings, two receivers each,
eight frames per excerpt, **144 frames total**. No failed or weak excerpt was
replaced or excluded; both corrected frequency arms had zero boundary fits.
No new RF was collected and no production analyzer was changed.

| Dataset | Excerpts | Cached mean NMSE | Short-pilot mean NMSE | Long-pilot mean NMSE | Long beats cached | Long beats short |
|---|---:|---:|---:|---:|---:|---:|
| DS7 | 6 | 0.874078 | 0.885623 | 0.873568 | 4/6 | 6/6 |
| DS8 | 6 | 0.919142 | 0.919349 | 0.908772 | 5/6 | 6/6 |
| DS9 | 6 | 0.822150 | 0.824372 | 0.822375 | 2/6 | 4/6 |
| All | 18 | 0.871790 | 0.876448 | 0.868238 | 11/18 | 16/18 |

Lower normalized mean squared prediction error (NMSE) is better. Each excerpt
has equal weight. This measures held pilot prediction, not position error.

![Per-excerpt pilot prediction comparison](comparison.png)

## What the comparison establishes

The short research fit uses pilot symbols 2–65; the long fit uses 22–221.
Both estimate one residual frequency across eight frames with independent
frame/carrier complex gains. Every arm, including cached frequency, calibrates
its gains on symbols 22–221 and predicts symbols 222–301. There is no assumption
of phase coherence between frames. The fixed residual search is ±1500 Hz.

The long fit's median absolute frequency correction was **12.12 Hz**, versus
**68.76 Hz** for the short fit. These are changes from the cached estimate,
not errors against a known frequency. The pooled long-fit mean NMSE reduction
was 0.003552 (about 0.41% relative), but the median excerpt reduction was only
0.000137. DS8 early RX0 and DS8 late RX1 contributed 0.061469 of the pooled
0.063933 sum of reductions, approximately 96%. DS9 late was near unit NMSE
and worsened under both fits; it remains in every aggregate.

Selection uses the earliest training observation of the earliest eligible
track per receiver in the first >=5 MS/s recording of each eight-scan panel.
Neither held scores nor waveform quality ranks these excerpts. However,
upstream track construction used full recordings, eligibility retains the
original train/held support requirements, and the panels have already been
examined in prior work. This is a matched exploratory assay, not a fresh blind
validation set. The 144 frames are clustered within 18 excerpts and nine
recordings, not 144 independent trials.

The short fit is **not** a reimplementation of deployed GLRT64. These results
cannot establish a regression in the deployed estimator. Known pilot templates
are used here; this experiment does not assign satellite identity to recovered
sequence states or demonstrate a sequence-assisted gain beyond long pilots.

## Implementation correction and validation

The initial assay omitted the deterministic symbol phase introduced by continuous
upconversion of symbol-local pilot references. Its near-unit NMSE and boundary
fits are not valid evidence against the method. `convention.py` removes the known
rotation without consulting measured or held symbols. The initial code/results
are preserved, and [EXECUTION-NOTE.md](EXECUTION-NOTE.md) explains the correction
and extraction checkpoint repair. The scientific selections and fit bounds did
not change. `results.json` contains the corrected evidence.

Four tests pass, including positive and negative injected frequency through the
raw-waveform demodulator at both band edges, held-symbol isolation, and selection
independence from held timestamps. Synthetic ±137 Hz is recovered within 0.1 Hz
with held NMSE below 0.0001. These synthetic checks validate the implemented
convention; they do not substitute for external calibration of real data.

## Next decision

Keep cached frequency as the operational baseline. The next useful bounded
experiment is a training-selected sequence of visits from the same tracks:
estimate frequency independently per visit, then compare prediction at later
visits under identical track membership and candidate hypotheses. Retain all
weak visits and report abstention coverage. This distinguishes a useful change
in trajectory shape from a per-track constant offset that localization already
removes. Only after that test should the revised observations enter a matched
geographic evaluation. Do not convert these 12-Hz corrections into meter claims.

## Evidence and reproduction

- [PROTOCOL.md](PROTOCOL.md): frozen selection, fitting and evaluation rules.
- [plan.json](plan.json): exact 18 selections and source hashes.
- [inventory.json](inventory.json): public-port bindings and raw-excerpt hashes.
- [results.json](results.json): corrected per-frame errors, estimates and hashes.
- [TABLE.md](TABLE.md): complete per-excerpt table, without quality filtering.
- `initial_results.json` and `initial_run.py`: preserved invalid-convention run.
- `prepare.py`, `extract.py`, `estimator.py`, `convention.py`, `run.py`,
  `summarize.py`, and the two test modules: reproduction and checks.

Use the installed public storage ports for extraction (read-only source access).
The numerical stage runs with NumPy and SciPy; plotting additionally requires
Matplotlib. Run numerical work with `OPENBLAS_NUM_THREADS=1` and a 120-second
timeout. The checkpointed extractor resumes completed entries only when their
selection, extractor and raw-file hashes match. Local raw excerpts are necessary
for numerical replay. This report and evidence are local; remote publication has
not been performed in this experiment.
