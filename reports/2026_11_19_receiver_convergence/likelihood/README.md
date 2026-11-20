# Exact fitted-endpoint likelihood reuse

The candidate reproduced the compact v5 cavity coordinates and conditional Doppler RMS exactly in both calibration arms of all four recordings. Reuse eliminated 584 of 844 native endpoint solves and made that operation 1.9–2.4× as fast by CPU time. The scoped savings ranged from 0.09 to 0.74 CPU seconds per recording. Whole-worker CPU rose on two recordings and fell on two. [Protocol](PROTOCOL.md) · [Matched measurements](receipt.json)

| Recording | Logical CPU | Endpoint solves, stock → candidate | Endpoint CPU s, stock → candidate | Whole CPU s, stock → candidate | Whole wall s, stock → candidate |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0036 | 4 | 211 → 65 | 0.867 → 0.362 | 63.97 → 67.52 | 90.25 → 93.27 |
| DS29-0082 | 5 | 143 → 45 | 0.150 → 0.063 | 39.20 → 38.27 | 61.30 → 43.11 |
| DS26-0122 | 4 | 279 → 85 | 1.461 → 0.716 | 147.43 → 141.86 | 175.58 → 151.81 |
| DS29-0174 | 5 | 211 → 65 | 0.691 → 0.366 | 63.62 → 64.74 | 71.38 → 67.97 |

Endpoint time covers the native bound operation, including exact key construction and result copying on the candidate. Whole time includes the projector kernel build, native observation preparation, initial search, conservative recovery, phase-history and predictive fitting, and the signed and cavity decisions. Each method received the same archived inputs and ran on the same logical CPU as its control, with a single numerical thread, on an Intel Core Ultra 9 285K. Timing starts from the stored outputs of the native GLRT detector. The endpoint operation accounted for 0.38–1.36% of stock whole-worker CPU. Pipeline timings outside the measured endpoint operation varied by more than the savings at that operation. Native backend receipts independently record exactly 584 fewer native solves with the same fallback counts. [Per-stage CPU and wall recordings](receipt.json) · [Native backend counters](native-counters.json)

## Position and frequency

| Recording | Position error, c = 0 (km) | Position error, fitted c (km) | Conditional RMS, c = 0 (Hz) | Conditional RMS, fitted c (Hz) |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 1.278 | 1.208 | 74.7609 | 74.6823 |
| DS29-0082 | 0.567 | 0.517 | 97.0036 | 96.6836 |
| DS26-0122 | 0.751 | 0.747 | 76.2201 | 76.2146 |
| DS29-0174 | 0.885 | 0.917 | 95.4051 | 95.5177 |

The stock and candidate counts, conservative masks and assignments, history and linear admissions, signed choices, cavity nominations, and eligibility matched. DS26-0036 triggered a cavity fit. The other three retained their signed incumbents. Coordinates and RF RMS also matched the independently archived cavity checkpoints. Both datasets use the same roof installation and search tile. The receipt binds each prediction to its frozen input. [Candidate predictions](positions.jsonl.gz) · [Stock predictions](stock-positions.jsonl.gz) · [Frozen checkpoints](../../2026_11_19_receiver_simplification/README.md)

## Reused operation

The conservative, history, and linear-predictive stages ask the same fitted model for its state, residual and acceptance metrics after optimizing. Each original calculation still constructs its own geometry and metrics. The candidate retains a single native likelihood result and reuses it when the current fitted coordinate, native backend and every argument match by value and floating-point representation. The cache resets on the next fit and returns a private copy to each caller. The signed and cavity refinements already use their own cache. [Implementation](../../../tools/pipeline_eval/variants/v5_likelihood_reuse.py) · [Isolation and invalidation tests](../../../tests/pipeline_eval/test_v5_likelihood_reuse.py)

The initial observer treated the history gate's named track list as a flat list. All four setup attempts stopped before a cavity position. The corrected observer ran each method again on the same recording and CPU. [Setup outcomes](observer-setup.json) · [Reproduction code](../../../tools/pipeline_eval/qualification/likelihood_reuse_eval.py)
