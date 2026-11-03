# Control-calibrated frame support preserves weak signals and abstains on noise-like slots

**A past-only control envelope improves the research estimator's abstention
behavior.** It retains 750/800 evaluation frequency estimates and marks 50
unavailable. All 800 frames remain in prediction scoring: 48 improve, two worsen
and 750 remain exactly unchanged. No Doppler-truth or position-accuracy improvement
is established, and this is not a production detector qualification.

## Complete evaluation accounting

Each visit has 100 evaluation receiver-frames: two RXs × 50 frames. Training
uses the preceding 30 frames independently on each RX. Lower prediction NMSE
is better; an abstention predicts zero coherent mean and has NMSE exactly one.

| Visit | Control-envelope retained | Fixed 0.2 gate retained | Wrong-template accepted | Improved / worsened | Mean paired NMSE gain |
|---|---:|---:|---:|---:|---:|
| DS7 S02 | 100 | 100 | 1 | 0 / 0 | 0 |
| DS7 S31 | 71 | 70 | 1 | 29 / 0 | +0.003265 |
| DS7 S32 | 79 | 78 | 4 | 19 / 2 | +0.002392 |
| DS8 S13 | 100 | 100 | 1 | 0 / 0 | 0 |
| DS8 S28 | 100 | 0 | 0 | 0 / 0 | 0 |
| DS8 S29 | 100 | 0 | 1 | 0 / 0 | 0 |
| DS9 middle | 100 | 100 | 0 | 0 / 0 | 0 |
| DS9 first | 100 | 49 | 0 | 0 / 0 | 0 |
| **Total** | **750/800** | **497/800** | **8/800** | **48 / 2** | **+0.000707** |

The 8/800 wrong-template acceptance rate is descriptive for this dependent
control corpus; it is not a calibrated deployment false-alarm rate. The median
paired gain across all frames is zero. Improvements arise from replacing
unsupported fitted predictions with a zero mean, not from improving the retained
frequency estimates. Two abstentions worsen prediction and are retained visibly.

The fixed threshold rejected all S28/S29 observations and about half of DS9-first,
even though their fitted pilot predictions outperform zero. Their mean NMSE
changes under that fixed rule are −0.136, −0.121 and −0.059 respectively. Thus
low absolute coherence must not automatically be classified as absent signal.

## Method and claim boundary

The [protocol](PROTOCOL.md) precedes execution. Exact and wrong-template frequency
searches have the same six-candidate FFT/refinement procedure and use only symbols
22–221. Symbols 222–301 evaluate predictions. For each visit/RX, three fixed
template rolls (17, 41, 83) on the first 30 frames generate 90 control scores.
Their maximum is the frozen acceptance threshold for later frames. Thresholds
range from approximately 0.0151 to 0.0203. No geographic truth, satellite label
or evaluation outcome enters threshold fitting.

The baseline is the full-support frequency estimator from the
[peak study](../2026_09_29_frequency_peak_tracking/README.md). Parent source
hashes and pilot-cache hashes are checked; all 800 baseline held errors reproduce.
All chosen frames and receivers are retained. An unavailable frequency is stored
as null, never as zero Hz or an imputed physical jump.

These are previously examined visits, with dependent frames and receiver pairs.
The wrong-template sequences are controls, not a complete model of interference
or all false associations. Retained frequency errors remain unknown, and the
gate does not prove signal absence or validate satellite identity.

## Relation to the actual localization pipeline

Inspection of the current working-tree `src/leo/analysis/starlink/pilot_methods.py`
shows `conditioned_glrt64_score` selecting symbols 2–65 and `_glrt_pair` combining
frame evidence noncoherently. This differs from our per-frame research fits over
symbols 22–221. The GLRT does not automatically produce one geographic frequency
observation for every frame analyzed here. The working-tree source is also not
an attestation of the deployed version; it contains pre-existing unrelated edits.

Consequently, the earlier noise-like research-frame estimates must not be described
as a demonstrated production clock bug or the established cause of kilometre
position errors. Before integrating a support rule, compare matched multi-frame
frequency estimators on raw held waveforms with the actual deployed conventions.
No production source was edited by this experiment.

## Verification and reproduction

Three tests pass: control-envelope boundary and null-frequency accounting;
evaluation-error isolation from acceptance; and rejection of incomplete/nonfinite
calibration. A research import path was fixed before execution. The complete
experiment takes about 5.3 seconds. The summarizer independently reconstructs
every threshold and abstention, verifies all hashes and checks exact 800-row
membership. Ruff lint and formatting pass.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python -m unittest discover -s reports/2026_09_29_frame_support -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_frame_support/support.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_frame_support/summarize.py
```

The next gate is a block-level comparison with noncoherent multi-frame fitting,
using the same pilot support and held observations for all arms. Report frequency
changes, waveform predictions, coverage and wrong-template behavior before a
geographic rerun. Robust short-window sub-km accuracy remains unachieved.
