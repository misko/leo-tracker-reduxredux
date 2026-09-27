# Lag-4 phase-CFO experiment result

## Decision

Reject the lag-4 phase alias method without retuning or validation/holdout
access. It fails the frozen scientific retention gate and both frozen cost
gates. It is also slower than the independent FP64 V4 comparator over all
development visits.

## Scientific result

| Measure | Result | Frozen requirement |
|---|---:|---:|
| Reference positives matched | 31/36 | 36/36 |
| Lost reference positives | 5 | 0 |
| Additional candidate positives | 2 | reported; not a truth label |
| Supported control decision changes | 0/24 | 0/24 |
| Matched results fractional-complete | 31/31 | all |

The phase attempt itself produces 26 positives. Twenty-four directly match a
reference positive. Structural fallback recovers another seven reference
positives, leaving five losses. All five losses are complete phase results, so
the preregistered policy correctly does not use the independent reference
outcome to trigger fallback. Each selected the wrong CFO alias and became
margin-negative; their tracking-CFO errors are hundreds of kilohertz. The two
additional positives are also complete phase results and are not adjudicated
as physical truth.

The controls retain all eight injected-pilot receiver-controls and keep all
eight noise and eight tone receiver-controls negative. This useful controlled
behavior does not override the five development reference losses.

The strategy invokes 125 development fallbacks: 47 for no candidate and 78 for
fractional-incomplete attempts. By rate, 43 fallbacks occur at 2.5 Msps and 82
at 5 Msps. The 5 Msps development cohort contains no reference positives, so
its high fallback burden cannot be excused by measured sensitivity there.

## Cost result

| Rate | Reference full-call CPU | Strategy full-call CPU | Full-call speedup | Reference fine CPU | Strategy fine CPU | Fine speedup |
|---|---:|---:|---:|---:|---:|---:|
| 2.5 Msps | 190.785 ms | 182.740 ms | 1.044x | 17.240 ms | 18.916 ms | 0.911x |
| 5 Msps | 369.748 ms | 453.549 ms | 0.815x | 40.963 ms | 42.483 ms | 0.964x |
| All | 560.533 ms | 636.289 ms | 0.881x | — | — | — |

The frozen gates required at least 1.05x full-call CPU speedup and 2x fine-stage
speedup at each rate. Neither rate passes either complete set of cost gates.
Although the phase proposal itself is cheap, conditioned scoring and charged
fallback erase the removed broad FFT. The candidate costs 13.5% more CPU over
all development receiver-visits.

These totals sum each receiver-case's median of five complete calls. Call order
was counterbalanced. Strategy timing includes natural-stride phase processing,
selected-window packing inside its native wrapper, and an additional packed
FP64 V4 call whenever the structural fallback rule fires. The comparator uses
its own packed FP64 V4 workspace and is never reused as the fallback result.

## Why the algebraic proposal failed

Lag-product phase is a valid carrier statistic in the ideal single-signal
model, but a single lag does not reliably resolve the detector's real alias in
this corpus. The frozen three-cell neighborhoods cannot repair a wrong alias,
and the method intentionally does not add another lag or tune offsets after
seeing outcomes. A multi-lag estimator would be a different detector with new
arithmetic and cost; it is not inferred to work from this failure.

The experiment still measures fresh IQ on every visit and returns an explicit
detector outcome or charged blind fallback. It gains no coverage by skipping
quiet visits and makes no absence claim from reference-negative examples.

## Provenance and limits

- Frozen design SHA-256:
  `c2e1bdb514f148e7f74e01239dec7d5b9e699498b09e3538f161994ba951c4fc`
- Development manifest SHA-256:
  `4874540dfe94bd5ced2d5496d6c53635de22c8f5d59d8edf0a159c62a899d401`
- Control manifest SHA-256:
  `ce3a22f10abefca4623affe006331b770dad5d3788d99aa44bdad93d2f75af48`
- Independent FP64 V4 binary SHA-256:
  `8cdc21362e8cb98a21550b0ba2024674881ca106706d9c799b33e5d4f5a7e614`
- Phase-CFO library SHA-256:
  `5c343d82c823eccedc878fa59bb2d5ca637d24bcbf860bb505ce4d78fecd3846`
- Phase-CFO build receipt SHA-256:
  `1f5b0f8a109a345935d7cca05010ea6c5fe1a9f78946b744e808fe2906fe747f`
- Row-level result SHA-256:
  `d502c8bc1968f3e6fe246c25ff177a51e74d5bc4aeef5f972c1e4bdc87ef36d0`

This is a server experiment. It does not combine its ratio with the separate
FP32 result, establish ARM performance, alter production, or open holdout IQ.
