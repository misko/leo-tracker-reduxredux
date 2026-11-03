# Sequence-assisted frequency estimation: bounded raw-IQ prototype

**The generated sequence can assist short-interval estimation, but this assay
does not establish a useful improvement over a stronger pilot-only baseline.**
Do not promote it into geographic fitting yet. No absolute Doppler, frame-TOA,
satellite identity, or position-accuracy improvement is demonstrated.

We replayed cached raw IQ from one previously examined visit each in DS7, DS8
and DS9, both receivers, twelve consecutive frames per receiver: **72
receiver-frames**, representing 36 paired frames from three visits. Samples
and receivers are dependent; these are not 72 independent trials.

## Main comparison

The strongest comparison gives both estimators the same long pilot support,
then adds only independently selected sequence samples to the hybrid. Both
predict the same later pilot observations without refitting. Lower normalized
mean squared complex prediction error (NMSE) is better.

| Dataset | Receiver-frames | Long pilot-only median NMSE | Hybrid median NMSE | Hybrid wins | Median paired gain |
|---|---:|---:|---:|---:|---:|
| DS7 | 24 | 0.643620 | 0.643767 | 14/24 | +0.0000134 |
| DS8 | 24 | 0.731852 | 0.731540 | 9/24 | −0.0000549 |
| DS9 | 24 | 0.624505 | 0.624515 | 14/24 | +0.0000080 |

The difference of medians is not the median paired gain. The hybrid wins
37/72 held-pilot comparisons and changes the frequency estimate by median
absolute amounts of 0.87 Hz, 1.58 Hz and 1.05 Hz respectively. Those changes
are **not frequency errors against truth**. Improvements are tiny and mixed.
The corresponding held-sequence comparisons are also nearly unchanged.

![Matched held-pilot comparisons](comparison.png)

## Why the initial result looked more favorable

The primary protocol used a short 40-symbol fit with frequency and phase
timing drift both free. Adding the generated sequence improved held pilots
in 59/72 cases and held sequence samples in 63/72 cases. However, pilot-only
drift reached its imposed boundary in 29/72 fits; sequence assistance did so
in 4/72. This indicates that the comparison includes an underconstrained baseline.

| Dataset | Short pilot, free drift | Short sequence, free drift | Short pilot, fixed drift | Short sequence, fixed drift |
|---|---:|---:|---:|---:|
| DS7 | 0.707298 | 0.665586 | 0.6861 | 0.6659 |
| DS8 | 0.792323 | 0.770921 | 0.7837 | 0.7701 |
| DS9 | 0.673067 | 0.636219 | 0.6572 | 0.6349 |

Cells are median held-pilot NMSE. Fixing drift shrinks the advantage; using
longer pilot support removes almost all of the incremental benefit. A
wrong-state k+1 control is included in every primary row: the selected sequence
outperforms that control on held pilots in 62/72 cases. This is a useful control,
not a calibrated false-alarm probability across the 60-state search.

## What was implemented

- Re-demodulate the original native-rate raw excerpts using their cached
  acquisition epoch/CFO. Do not reuse the old per-symbol phase/timing corrections.
- Remove published pilots and the empirical reference template; select one
  frozen generated sequence state on separate earlier non-pilot observations.
- Profile one constant complex channel gain per carrier. Estimate residual
  frequency and, in the primary assay, frequency-dependent phase drift.
- Predict later pilots and sequence symbols with all parameters frozen.

The complex phase model is
`2π * t * (frequency_hz - offset_frequency_mhz * drift_ppm)`.
The carrier offset is relative to the captured pilot-band center. Drift is a
differential phase parameter, not a measured calibrated sample oscillator.
Static timing is confounded with free carrier phases, so this prototype does
not estimate absolute frame start. Residual frequency includes receiver,
transmitter and demodulation effects; it is not isolated orbital Doppler.

Primary symbol partitions (OFDM numbering): pilot initialization 22–121;
state selection 142–181; parameter fitting 182–221; evaluation 222–301.
The long pilot arm fits 22–221. The hybrid uses those same pilots plus sequence
symbols 182–221, weighted by sample count in the profiled likelihood. Its
sequence gains, and all evaluated tail gains, use only 182–221.
Longer sequence intervals and probabilistic state marginalization remain untested.

## Inputs and scope

| Dataset | Excerpt | Rate | Both-RX frames | Training-qualified receiver-frames |
|---|---|---:|---:|---:|
| DS7 | S02, visit 1452, scan-fw-02511088637aaaea | 5 MS/s | 12 | 24/24 |
| DS8 | S13, existing ds8-2 export | 10 MS/s | 12 | 13/24 |
| DS9 | DS9-middle, visit 50, scan-fw-fad62f2672600b46 | 10 MS/s | 12 | 24/24 |

Qualification requires initial pilot coherence and sequence selection coherence
above 0.5, both computed without held samples. Main tables retain all inputs;
qualified-only summaries are in `summary.json`. This is a selected convenience
sample with prior exploratory exposure, not unseen-recording validation or a
controlled sample-rate comparison. The constant sequence state is retained.
The 60-state generator is frozen, but this prototype does not marginalize state
uncertainty or require cross-RX state equality.

## Verification and provenance

Five synthetic tests pass: signed frequency/drift recovery with nuisance gains,
state recovery/wrong-pattern rejection, held-sample mutation isolation,
partition separation, and fixed/hybrid frequency recovery and isolation.
Ruff lint/format pass. All 72 primary optimizer calls per arm report success;
boundary solutions are retained and explicitly marked.

Injecting a post-FFT +137 Hz / +7 ppm ramp checks equivariance. In the 68
nonboundary sequence fits, maximum recovery discrepancies are below 0.00013 Hz
and 0.00013 ppm. Bounded fits cannot reproduce a perturbation beyond their
drift bound; all-row injection discrepancies remain in `results.json`.
This test is not absolute real-signal accuracy, a raw-RF injection, or a check
of intercarrier interference. It does not justify extrapolating to acquisition.

Original raw array digests match their extraction records; source files,
references, protocol and scripts have SHA-256 bindings. `summarize.py` verifies
all bindings, row joins and primary optimizer statuses. The primary replay
after formatting exactly reproduced every scientific result row. Replays each
took only a few seconds; no collection, source-storage writes, application
changes, or geographic jobs were started.

The [primary protocol](PROTOCOL.md) preceded execution. The
[follow-up protocol](FOLLOWUP_PROTOCOL.md) records why extra baselines were
added after inspecting the first results. The initial follow-up incorrectly
extended tail gain calibration into earlier symbols; corrected follow-up
results restrict all tail gain fits to the valid fitting interval. Initial
outputs are retained under ignored `local/`; held-pilot comparisons were
unaffected. `results.json` and `followup-results.json` contain final evidence.

## Reproduce and next decision

From the repository root, with the already cached inputs present:

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python -m unittest discover -s reports/2026_09_29_sequence_estimator -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_sequence_estimator/run.py
OPENBLAS_NUM_THREADS=1 timeout 120 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_sequence_estimator/followup.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_sequence_estimator/summarize.py
```

The next discriminating test is longer, independently qualified sequence
support against the same strong pilot baseline, on additional recordings.
Measure usable coverage as well as error. Only then consider full-frame timing,
joint RX estimation, or geographic propagation. The current result supports
feasibility of the waveform model, not deployment or a sub-km improvement.
