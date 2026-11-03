# Longer sequence support: no robust improvement over strong pilots

**Do not promote sequence assistance into geographic fitting.** Extending
the generated sequence to longer regions and adding recordings does not
establish a substantial, consistent advantage over a strong pilot-only fit.
This is a completed bounded follow-up to the
[first prototype](../2026_09_29_sequence_estimator/README.md).

Eight previously examined visits contribute 192 receiver-frames, both RXs and
twelve consecutive frames per visit. Five visits are additional to the first
prototype, adding three session recordings (DS7, DS8 and DS9). Of the 192
receiver-frames, **81 qualify** using training-only pilot and sequence checks;
111 retain the pilot baseline unchanged. No raw-IQ source or application code
was changed and no new RF or location fit was run.

| Dataset / visit | Qualified / 24 | Held-pilot improvements | Unchanged fallback cases | Interpretation |
|---|---:|---:|---:|---|
| DS7 S02, original | 24 | 14 | 0 | Small mixed gains |
| DS7 S31, additional | 7 | 6 | 17 | Limited qualified support |
| DS7 S32, additional | 14 | 6 | 10 | More qualified cases worsen than improve |
| DS8 S13, original | 10 | 5 | 14 | Mixed |
| DS8 S28, additional | 0 | 0 | 24 | No qualifying sequence region |
| DS8 S29, additional | 0 | 0 | 24 | No qualifying sequence region |
| DS9 middle, original | 24 | 15 | 0 | Small mixed gains |
| DS9 first, additional | 2 | 1 | 22 | Mostly fails qualification |

The gated hybrid improves held-pilot prediction in **47 cases**, worsens it in
34, and leaves 111 unchanged. These correlated receiver-frames are not
independent trials. Failure to qualify an excerpt does not establish absence
of the repeating signal throughout its recording.

For the fully qualified original DS7 and DS9 visits, median paired held-pilot
NMSE reductions are only **0.000156** and **0.000300**. Their baseline median
NMSEs are approximately 0.644 and 0.625. These are small observable-prediction
changes, not absolute frequency errors or evidence of sub-km positioning.
The per-visit qualified-only and all-case results are in [summary.json](summary.json).

![Coverage and paired held-pilot gain](comparison.png)

## Method

The [protocol](PROTOCOL.md) was written before execution. Input membership
was fixed, including the known difficult DS9-first excerpt. The cached raw
arrays are hash checked and re-demodulated without reusing corrected soft
symbols. Cached pilot acquisition initializes the process, so it is not blind
acquisition or an independent assessment of acquisition error.

1. Fit a frequency-only pilot baseline on OFDM symbols 22–221.
2. Consider sequence suffixes beginning at 42, 82, 122 and 162, ending at 221.
   Even-numbered symbols select a frozen 60-state generator state. Choose the
   earliest region exceeding 0.5 coherence, or retain the strongest failed
   candidate for diagnostics if none qualifies.
3. Odd-numbered symbols independently verify sequence coherence. Qualification
   requires pilot initialization, selection and verification coherence above 0.5.
4. Fit the hybrid with exactly the same pilots plus the selected odd sequence
   symbols. Profile static complex gains separately for each carrier, weighted
   by sample count; fix the differential timing-drift parameter to zero.
5. Predict held symbols 222–301. No held samples select state, region or gate.
   An additional k+1 sequence control is retained in every result row.

The longest sequence fitting support has 90 odd symbols spanning approximately
0.78 ms; the shortest has 30 spanning approximately 0.26 ms. The pilot support
remains 200 symbols for both primary comparison arms. This avoids attributing
an improvement from additional pilot support to the generated sequence.

Both arms predict the same held pilots and the same selected-state tail
samples. Sequence interpretation in the latter depends on the selected model;
held pilots therefore provide the primary independent known-waveform target.
Neither observer prediction nor paired-RX state agreement identifies a satellite.

## Validation and reproducibility

Three tests pass: known-state and signed-phase-frequency recovery, held-data
mutation isolation, and baseline fallback for unstructured samples. The fallback
test uses a deterministic noise sample, not a calibrated population false-alarm
bound. The frozen protocol does not tune a false-alarm threshold.

All 192 requested rows returned in about 5.2 seconds with no substitutions.
`summarize.py` checks the exact membership, source SHA-256 bindings, and all
fallback decisions, then writes the summary and figure. Ruff lint and format
checks pass. The input and implementation hashes are stored in `results.json`.
Original IQ remains ignored; no downloaded data or new runtime dependency
is introduced.

From the repository root with the cached inputs present:

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python -m unittest discover -s reports/2026_09_29_sequence_long_support -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_sequence_long_support/study.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_sequence_long_support/summarize.py
```

## Consequence for the sub-km effort

The sequence representation is useful for recognizing and modeling signal
structure, but these two prototypes do not support it as the next major
accuracy improvement. Further frequency refinement on the same waveform
family should not displace physical error-source diagnosis. Prioritize
receiver/frequency common-mode behavior, timing discontinuities and independently
constrained antenna/orbit calibration; test whether they predict held data
before any new geographic optimization.

Absolute frame timing, probabilistic state mixtures, overlapping emitters and
longer coherent integration across frames remain untested. This negative
promotion decision is specific to the tested frequency estimators and data;
it is not proof that the recovered sequence can never improve navigation.
