# Fitted-first constrained rescue on saved DS30-0402

The fitted calibration arm proved the constrained reassignment ineligible after **58 visits**. The earlier fixed-zero-first candidate needed **335 visits** to reach the same decision. The complete saved publication took **55.830 s**, compared with **65.646 s** for fixed-zero-first and **73.351 s** for the archived named solve. The final positions and RF fits, all **4,821 ordered owners per arm**, the path and complete grid, and all eight encoded and decoded PNGs reproduced. Fitted-first was chosen after inspecting this recording's earlier timings. [Frozen protocol](constrained-pair-arm-order-protocol.md) · [Verified publication receipt](measurements/constrained-pair-arm-order-0402.json.gz)

## Gate and arm work

The fixed arm-order option changes only the five-round constrained rescue loop, after the original unconstrained pairs and admission checks. A completed first arm can reject a candidate when an original conditional or predictive gate reports an incompatible track. Missing phase or gate evidence leaves the remaining original arm in use. A complete pair is returned in canonical `c0`, `fitted_c` order. Later hypotheses and the original adoption policy continue to run. The option defaults to `c0` and uses a caller-supplied order without looking at the recording, offer, ranked candidates or satellite labels. [Generic rule](constrained_pair_veto.py) · [Saved driver](paired_veto_0402.py)

| Saved configuration | Constrained `c = 0` visits | Constrained fitted visits | Constrained phases | Constrained CPU s |
|---|---:|---:|---:|---:|
| Exact prepared gates and full pair | 335 | 58 | 10 | 15.128 |
| Exact gates and fixed-zero-first veto | 335 | 0 | 5 | 12.766 |
| Exact gates and fitted-first veto | 0 | 58 | 5 | 2.301 |

The full-pair total of 393 was directly counted. Its per-arm split was inferred from the original fixed-zero-first run and then reproduced by observing the actual fitted-first history. The two veto orders encountered the same incompatible conditional track indexes, 37 and 49. The fitted-first rescue made **12,122** prepared polynomial screens, **7,192** white profiles and **4,930** whitening requests, with zero fallbacks. Both other trial results and the rejected proposal order matched the original three outcomes. The skipped constrained arm cannot surface exceptions from the work it would have performed. Genuine exceptions from executed code propagate. All final accepted fixes still carry both calibrations. [Exact-gates control](stock-exact-gate-0402.md) · [Named proposal census](named-roster-0402.md)

## Complete publication

| Saved variant | Solve CPU s | Solve elapsed s | Exit CPU s | Exit elapsed s |
|---|---:|---:|---:|---:|
| Named stock | 68.774 | 68.825 | 73.254 | 73.351 |
| Exact prepared gates | 64.041 | 64.084 | 68.508 | 68.589 |
| Exact gates and fixed-zero-first veto | 61.179 | 61.228 | 65.570 | 65.646 |
| Exact gates and fitted-first veto | 51.471 | 51.496 | 55.802 | 55.830 |

The fitted-first replay saved **9.816 s elapsed through exit** versus fixed-zero-first, **12.759 s** versus exact gates alone and **17.521 s** versus named stock. It used **9.708 fewer solve CPU seconds** than fixed-zero-first. These are single-process comparisons against archived runs from different sessions. Linux reported zero input blocks for fitted-first and 3,088 for fixed-zero-first. The original 20 ms detections, 25 km containing offer, causal archive and low-priority single-core settings were matched. [Original saved input binding and measured stock](prospective-0402-solver.md)

| Calibration | Reproduced horizontal error | Reproduced RF RMS | Conditional / predictive owners |
|---|---:|---:|---:|
| `c = 0` | 0.863651 km | 100.672203 Hz | 4,150 / 671 |
| Fitted `c` | 0.860302 km | 100.576460 Hz | 4,150 / 671 |

The verifier matched the original terminal digest and rank-one finalist, ordered owner and role rows, all 179 grid points and the optimizer path, both sidecar bindings, and the dimensions and decoded pixels of all eight unchanged PNG files. Twenty-seven focused tests passed. They exercise either first arm, a qualified complete pair, unresolved evidence, rejection of curved and predictive tracks, another proposal winning, and unrelated numerical failures. The choice of fitted-first requires independent transfers across a successful constrained pair and different first-arm failure patterns before any change in default. [Component tests](../../../tests/pipeline_eval/test_constrained_pair_veto.py)

The single candidate was frozen at `7b8be72c6`. Run `paired_veto_0402.py launch NEW_TMPFS_ROOT --first-arm fitted_c` under the shared Gauss lock and the existing release interpreter. Run `paired_veto_0402.py evaluate NEW_TMPFS_ROOT NEW_RECEIPT.json` to validate the original archived science and measure the same boundaries. The completed output and scored receipt remain at `/dev/shm/leo-v3-0402-fitted-first-run01` and `/dev/shm/leo-v3-0402-fitted-first-scored01.json`.
