# Continuation quality and conditional variance on unfiltered short detections

The saved weak and northern recordings supply **zero independent forecasts for short factors that fail both continuation directions**. The full unfiltered graph also filters almost all of that class before orbital estimation. The sealed fitted likelihood used **zero** such conditional rows per arm on DS30-0016 and **one** per arm in the north. These inputs establish neither a positive variance increment nor enough affected observations to justify a weighted position run. [Frozen protocol](continuation-quality-protocol.md) · [Calibration and availability receipt](measurements/continuation-quality.json.gz)

## Existing noise and placement of a possible intervention

The installed `fixed_window_noise` estimates a 40–600 Hz conditional scale from leverage-adjusted radio-polynomial residuals on active curved tracks. It compares a common scale and a `floor + strength/margin` variance using a BIC improvement. The normal likelihood consumes the selected per-observation scales and joint Gamma noise precision per track. Predictive linear geometry reads the same metadata. Changing that shared map would affect both types of evidence. A conditional-only candidate would need a separate scale at construction of the normal-position likelihood, after the unchanged graph and cold discovery, and the same scale when replaying endpoints and rendering the grid. Existing fixed-owner repair adds noise metadata for new IDs under the original margin law. Earlier score audits and synthetic covariance trials did not measure continuation as a separate conditional variance term. [Original noise law](../../../src/leo/analysis/localization_v3/noise.py) · [Conditional input](../../../src/leo/analysis/localization_v3/position.py) · [Predictive consumer](../../../src/leo/analysis/localization_v3/predictive_linear.py) · [Existing added-row policy](local_future_repair.py)

## Held-epoch calibration

Both original short packets contain every verified selected factor before continuation. The calibration reconstructed independent donor graphs on alternating four-second groups of whole stereo visits. A held point could be scored only if the same receiver, channel and exact RF supplied a uniquely predicted curve with three donor measurements on each side. Only donor data chose the curve. Afterward, the held measurement was lifted to its donor alias and scored with prediction leverage and the selected donor margin-law or constant variance. This can measure the spread of predictable cross-time innovations. It mixes any measurement noise with tracking, identity and trajectory errors. [Calibration implementation](continuation_quality.py)

| Case | Supported short factors | Supported with unique forecast | Short factors failing both directions | No independent track on exact lane | Track available, no valid bracket | Unsupported with unique forecast |
|---|---:|---:|---:|---:|---:|---:|
| Weak DS30-0016, 475 total measurements | 361 | 71 | 40 | 17 | 23 | **0** |
| Northern simulation, 1,078 total measurements | 460 | 0 | 536 | 321 | 215 | **0** |

The two independent physical folds supplied 13 tracks each, and the two northern folds supplied eight and six. Among the physical supported short rows that did receive a prediction, median absolute leverage-corrected error was 90.14 Hz. Eight periodic CFO differences exceeded 450 Hz. Five exceeded 8 kHz and all five occurred on the same receiver and channel. A unique time bracket can still connect a different transmitter. The northern donor graphs licensed zero predictions on either short class. The preregistered minimum was 12 unsupported measurements on at least four distinct visits and two exact lanes, plus 24 supported measurements per recording. With zero unsupported measurements in both, neither the variance ratio nor its independent cross-record score exists. [Fold clocks, per-row predictions, and absent ratios](measurements/continuation-quality.json.gz)

## How much evidence would the weights affect?

| Case | Unsupported short rows with any occupied full slot on each side | Unsupported short rows in whole Graph | In published conditional fit per arm | In published predictive fit per arm |
|---|---:|---:|---:|---:|
| Weak DS30-0016 | 12 / 40 | 2 / 354 graph rows | **0 / 93** | **0 / 23** |
| Northern simulation | 1 / 536 | 1 / 485 graph rows | **1 / 287** | **0 / 60** |

The full-slot check allows any occupied nearby 20 ms factor on the same RF and antenna within eight seconds on each side. It grants a bracket even if the two full factors describe different transmitters. The northern held population therefore lacks even the minimal full-slot timing witnesses for a broader aperture-only calibration. The sealed owner counts agree between `c = 0` and fitted `c`. Reading those archived maps occurred in the availability audit and did not feed the disturbance ratio. [Full-slot census and archive bindings](measurements/continuation-quality.json.gz)

Marking the entire forward-rejected class would change the intervention. It would also reach four weak and 32 northern conditional short observations that pass reverse continuation. The availability audit records those rows separately. Reverse support supplies evidence about nearby observations. It supplies no independent scale for inflating or deflating their variance. The existing protected-selection comparisons already address what happens when some such rows are dropped and restored. [Protected repair](local-future-repair.md) · [Full-aperture crossover](full-confirmed-future.md)

The paid calibration stages took **0.118 / 0.108 CPU seconds** for weak/north, with the separate availability audits taking **0.102 / 0.290 seconds**. No weight was applied. No new position comparison, dense trial, or waveform replay was warranted by this evidence. The result applies to the tested directional definition and exact saved cadence, where missing independent brackets dominate. It does not establish a universal relationship between continuation and measurement precision. [Receipts](measurements/continuation-quality.json.gz)

## Reproduction

```sh
tree=/home/mouse9911/gits/leo-tracker-reduxredux
slot() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock nice -n15 ionice -c2 -n7 taskset -c 2 timeout 40s \
    env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD/src:$PWD" \
    "$tree/.venv/bin/python" -BPs "$@"
}
slot reports/ALGO08/v3/continuation_quality.py "$new_receipt"
slot -m pytest -q tests/pipeline_eval/test_continuation_quality.py \
  tests/analysis/test_localization_v3_noise.py tests/pipeline_eval/test_short_primary_epoch_audit.py
```

Sixteen focused tests passed. The receipt's uncompressed SHA-256 is `d56d276b3226b5e610e761288514cfd3c64a58dfb271ba1935cdbcc62bbe95ab`. [Component tests](../../../tests/pipeline_eval/test_continuation_quality.py)
