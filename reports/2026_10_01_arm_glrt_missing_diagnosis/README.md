# Cause of ARM GLRT losses in the five remaining long tracks

The dominant demonstrated cause is the native detector's **early coarse-score
gate**, which rejects candidates before their final GLRT is evaluated.
Disabling only this gate on physical PLUTO+ recovers **67 of 85** missing or
CFO-mismatched reference detections (78.8%). The remaining 18 still exhibit
candidate-search/refinement mismatches.

This audit covers refs #2, #30, #8, #34, and #47 from the same saved 300 s DS9
scan. It investigates detection coverage, not tracking changes or new RF.

| Reference | Missing matching ARM detections | Windows rejecting all eight coarse candidates | Recovered by disabling coarse gate | Still missing |
|---|---:|---:|---:|---:|
| #2 | 16 | 14 | 12 | 4 |
| #30 | 12 | 11 | 8 | 4 |
| #8 | 32 | 32 | 26 | 6 |
| #34 | 10 | 9 | 10 | 0 |
| #47 | 15 | 14 | 11 | 4 |
| Total | 85 | 80 | 67 | 18 |

For #34, nine source groups were absent from passing ARM output; one had
passing ARM output at an inconsistent CFO. The other missing entries are
source groups absent from passing ARM output. Raw detector receipts retain
some below-final-threshold candidates, so absence from tracker input does not
always mean zero raw detector output.

## Confirmed mechanism

The exact source used by the frozen ordinary binary was verified against every
source hash in its build receipt. In `kernel/private/full_search.c`,
`coarse_score_threshold()` returns **0.314 at 2.5 MS/s**. After retaining up
to eight coarse peaks and checking frame support, `coarse_score_allowed()`
rejects lower-scoring peaks and continues without evaluating their final
GLRT. The source describes these as exploratory thresholds selected on an
earlier frozen Wave4 cohort; they are not a mathematical lower bound on the
final GLRT margin.

The experimentally recovered candidates have coarse scores **0.28980–0.31375**,
below that cutoff. They pass the unchanged final **0.025 GLRT-margin gate**
and match the server source and CFO under the unchanged 2.5 kHz circular
normalized-CFO criterion. This is direct causal evidence that the early gate
discarded those 67 detections.

All 85 missing reference candidates already pass the server's **integer**
GLRT margin gate, with margins **0.0511–0.4554**. Fractional refinement is
therefore not required for their server acceptance. This does not imply that
integer and fractional CFO estimates are identical.

The gates compare different scores: 0.314 is a preliminary coarse score;
0.025 is exact-minus-control GLRT margin. They are not interchangeable scales.

## Remaining 18

After disabling the gate, the retained candidate searches still miss the
server-matching result:

- Ten cases have no emitted candidate epoch within two samples of the
  server-selected integer epoch, modulo the 3,333-sample period.
- Eight cases have a nearby epoch but no passing candidate at a matching
  CFO. Example: ref #2, visit 9, searches epoch 1106 on both sides, but the
  ungated native acquisition chooses about -388.4 kHz versus the server's
  +382.4 kHz; native final margin is about 0.001 rather than server 0.093.
- Ref #30 visit 775 is an epoch-search example: the server reference uses
  epoch 834, while the closest ungated native candidate uses epoch 948.

These observations localize the residual failures to candidate search and
refinement. They do **not** isolate the contributions of each reduced native
search setting. The frozen native build uses an eight-frame proposal budget,
half-size proposal FFT, a two-frame fine-search budget, and fine-direct
refinement mode. Additional controlled ablations are required before blaming
one of those settings specifically. No fractional-only explanation or hardware
floating-point failure is established by this audit.

Remaining visits are recorded per reference in `results.json`. Ref #2's
previously identified isolated point at visit 17 is already present in ARM
input, so it is a separate tracker-gap issue and is not among these 85 cases.

## Physical reproduction and runtime

Both the original frozen ordinary binary and the diagnostic gate-disabled
binary processed all **85 affected saved dwells**, dual RX, first 20 ms/RX of
each 120 ms dwell, on **PLUTO+ 192.168.1.15**. The source, templates, raw-IQ
hashes, and event identities were checked. All 170 original-binary receiver
rows reproduce the original full-scan scientific results exactly after
removing only timing fields. Server raw-IQ hashes/events match these inputs.
The diagnostic build changes only the coarse rejection condition; it uses the
same compiler flags and remaining settings as the ordinary build.

| Detector time per selected dwell | Original | Coarse gate disabled |
|---|---:|---:|
| Median | 54.36 ms | 101.64 ms |
| Maximum | 75.97 ms | 134.71 ms |
| Calls >=120 ms | 0/85 | 5/85 |

These are single-pass measurements on deliberately selected missed cases,
not a full-scan latency benchmark. Disabling the gate everywhere is **not**
qualified as a real-time fix. No production binary, firmware, tracker,
reference fixture, or evaluation threshold was changed.

## Consequence

The ARM hardware did not lose these IQ samples: the saved bytes are identical.
Most of the missing evidence was discarded by a speed-oriented detector
pruning policy before GLRT evaluation. The earlier native-control parity
result remains a different claim from parity with the full server detector.

A suitable next experiment is a bounded second-chance evaluation for rejected
coarse candidates, with runtime budgeting and independent-recording checks.
Track predictions could prioritize that work once a trajectory exists, but
blind discovery still needs coverage. Lowering the threshold based solely on
these 85 misses would be tuning to the evaluation cases, not validation.

Adding the recovered detections to the existing source inventory would leave
enough matching input for all five references to exceed 80% coverage. This is
an input-availability calculation, **not** a demonstrated five-track recovery;
the tracker was not rerun on such an augmented input in this diagnosis.

## Artifacts

- `missing.json`: join to original ARM/server per-dwell receipts.
- `results.json`: full per-source gate ablation, candidate fields, residual
  epoch/CFO diagnostics, recovery counts, and timing summary.
- `physical/`: both physical detector outputs, selected visits, binary hashes,
  and raw-IQ receipt.
- `build.json`, `source-change.patch`, `ungated-build/`: diagnostic build and
  exact source change. The original source root and receipt are recorded by
  `build.py`; no runtime dependency was added to the application.
- `audit.py`, `replay.py`, `evaluate.py`: reproducible audit, bounded replay,
  and result checks. `MANIFEST.sha256` binds final artifacts.
