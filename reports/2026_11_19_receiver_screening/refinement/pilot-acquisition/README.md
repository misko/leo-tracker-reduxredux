# Phase-consistent differential pilot acquisition

This scout cut the coarse stage by **4.06×** and reduced full-detector CPU by **46.95%** against the full-epoch Q10 detector. It recovered **4 of 26** original fractional positives across 15 processed held visits and lost eight receiver winners. The same counts hold for the integer positives. It added no unmatched held positives. The largest missed margin was **0.513** against the 0.025 gate. The scout failed both the 10× coarse-stage goal and the scientific acceptance criteria.

| Held capture | Scheduled / processed visits | Coarse speedup | Full detector CPU saved | Fractional positives retained | Highest-margin winners lost |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0036 | 8 / 8 | 4.14× | 46.9% | 4 / 10 | 3 |
| DS29-0082 | 8 / 7 | 4.01× | 47.0% | 0 / 16 | 5 |
| Pooled | 16 / 15 | 4.06× | 47.0% | 4 / 26 | 8 |

The paired baseline reproduced the installed capture-era result on every visit. The scout changed each processed public result. It kept the exact margin of every physically matched positive. Pooling the two timing pairs gave 15.859 s baseline detector CPU and 8.413 s scout detector CPU. Median CPU per 20 ms visit was 510 ms and 290 ms. The proposal and preparation took 0.926 s pooled, regional verification and suppression took 1.056 s, and the baseline coarse stage took 8.045 s. Even removing all regional verification would cap this proposal path at about 8.7× coarse on the observed timings. The existing full detector would gain at most about 2.03× from eliminating its coarse stage while holding its remaining work fixed.

## What the proposal measures

For raw complex samples `x`, lag `l` uses `x[n+l] conj(x[n])`. The code folds this product over known rounded frame starts and correlates the folded vector with the literal products of the exact Qin anchor templates at every raw epoch. A constant CFO writes the same complex factor `exp(i ω l)` into every correlation at that lag. With normalized outputs `Z1`, `Z8` and `Z15`, the score `abs(conj(Z1) Z8 + conj(Z8) Z15)` removes the phase `exp(i 7ω)` shared by both lag increments. Their sum retains evidence for a consistent progression between lags. This differs from the earlier ARM lag study's rank sum of three independent magnitudes and pilot power. [Earlier lag experiment](../../../2026_09_29_arm_lag_discovery/REPORT.md).

The 12 best proposals admit at most 108 raw epoch cells per CFO. The original 21-CFO direct scorer also computes the neighbors and complete SIMD tiles around them, a median of 6,720 cells per held call. The proposal computes 599,976 raw complex lag products and nine FFT operations per typical call. Its three stored lag-output arrays use 319,992 bytes. The underlying original preparation and direct tiles remain in place. Candidate ordering and suppression are exact inside the proposed regions.

For a linear chirp of 900 kHz/s, the longest 15-sample differential phase changes by at most 0.170 rad across a 20 ms window at 10 MS/s. This bounds phase drift for one ideal chirp. The score also scales with the fourth power of a single isolated pilot's amplitude. Together these properties supply no positive lower bound on recall for mixtures or intermittent support. For example, a coherent constant template present on alternating samples has normalized matched score `sqrt(1/2)` while both odd lag products vanish. The proposal score is identically zero. A component test verifies this structural counterexample. The held 22/26 miss fraction describes the bounded sample, and the selected visits are correlated within recordings.

The two configurations both recovered the amplitude-128 epoch-735 pilot and the fractionally shifted −745 kHz chirp on both receivers. Both methods recovered the stronger pilot in the dual-chirp control, and both missed its weaker positive-CFO pilot under the DS29 configuration. Empty and independent noise produced no positive candidates. Across the planted fixtures there were six unmatched extra fractional positives and one missed baseline fractional positive. The per-control truth checks use two circular samples and a CFO tolerance consisting of 1 kHz plus the modeled excursion over half the visit. The candidate disagreements remain visible in the full payloads.

## Experimental partial-IQ position comparison

Both DS26-0036 v5 computations are fresh. The scout uses actual detector outputs from eight held IQ visits and the archived detections for the remaining 6,757 valid visits. All 16 receiver rows in the substituted visits changed. The independent control uses the entire capture-era archive. The two worker inputs use the same authenticated archive and causal catalogue and have distinct native and request digests. Prepared observations, tracks and final owners changed. DS29-0082 was evaluated at the detector boundary only.

| Calibration arm | Archive error | Scout error | Archive conditional RF RMS | Scout conditional RF RMS |
| --- | ---: | ---: | ---: | ---: |
| `c = 0` | 1.278365 km | 1.270304 km | 74.760916 Hz | 74.777567 Hz |
| Fitted `c` | 1.208143 km | 1.199928 km | 74.682298 Hz | 74.698364 Hz |

Both positions moved about 8 m closer to the surveyed site while conditional RF RMS increased slightly. The observation, ownership and frequency fit changes describe this eight-visit substitution. Localization after using the scout on an entire recording remains unmeasured. [Experimental position](positions.jsonl.gz) · [Paired archive control](control-positions.jsonl.gz) · [Prediction seal](prediction-lock.json)

[Predeclared protocol](PROTOCOL.md) · [Source lock](source-lock.json) · [Qualification](qualification.json)

Reproduce the native detector blocks with `python -m tools.pipeline_eval.qualification.differential_gate_eval --case CASE --split SPLIT` with the designated original capture producer first on `PYTHONPATH`. Pin the appropriate core and numerical threads. Use the `differential_gate_position` module's `prepare --work WORK` action to authenticate the composite input, and its two named fit actions to run candidate and control on CPUs 1 and 21. The `package` action validates the evidence and writes the compact both-arm position bundles.
