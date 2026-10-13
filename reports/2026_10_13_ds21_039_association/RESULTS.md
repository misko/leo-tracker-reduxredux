# DS21-039 association findings

The frozen training-only diagnostic shows substantial association changes between the full-band and half-band endpoints, despite sharply concentrated individual satellite posteriors. Calibration and geography/timing have interacting effects. These receipts do not establish wrong satellite identities or missing catalogue support.

The coordinator completed V2 in **38.7288 seconds**, with **zero optimizer calls**, all thirteen stage receipts, and no held preparation, held scoring or reference use. All three historical fitted-c winners were start 5 and used the unchanged 43-satellite bank. An independent receipt-only audit verified the fifteen terminal-bound evidence files and all **319 live/source-archive hash pairs**, with no discrepancies. Saved source objective and likelihood replay deltas were zero; the packed native likelihood differed by at most 3.64×10⁻¹² and satellite/clutter probabilities by at most 7.22×10⁻¹⁶.

| Training endpoint | Windows | Native NLL | Signal mass / windows | Conditional native RMS, Hz | Satellite entropy, nats |
|---|---:|---:|---:|---:|---:|
| All | 2,798 | 32,969.500 | 73.91% | 104.40 | 0.1003 |
| Low | 1,692 | 19,619.152 | 76.33% | 91.47 | 0.1007 |
| High | 1,106 | 13,372.117 | 67.73% | 90.10 | 0.0715 |

Entropy is signal-weighted within-window satellite entropy. Divergence from the unchanged uniform satellite prior was 3.661/3.660/3.690 nats for all/low/high. This is descriptive posterior concentration, not a measured benefit from a different satellite prior. The model has **zero temporal edges and neutral waveform evidence**; neither low entropy nor occupied catalogue numbers establishes an emitter, beam or carrier identity. Frequency RMS and NLL are not position accuracy.

## Native candidate inventory

The original alias-cell winner port drops roughly half the passing detector alternatives before likelihood evaluation:

| View | Passing candidates | Retained | Discarded | Collision cells | Cells with CFO spread above source σ |
|---|---:|---:|---:|---:|---:|
| All | 7,622 | 3,714 | 3,908 (51.27%) | 2,298 | 913 |
| Low | 4,815 | 2,294 | 2,521 (52.36%) | 1,439 | 600 |
| High | 2,807 | 1,420 | 1,387 (49.41%) | 859 | 313 |

Maximum within-cell CFO spread was 218,983.56 Hz for all/low and 157,355.55 Hz for high. These are detector alternatives, not verified signals. This diagnostic counted the loss without reinserting or scoring discarded candidates. It did not evaluate omitted satellites, so it cannot attribute the endpoint differences to an incomplete bank.

## Matched endpoint comparisons

All 1,692 low and 1,106 high windows matched the full view exactly in native IDs and measurement values; none were excluded. Each comparison crosses the full or half **geography plus satellite timing** with the full or half frozen receiver/group correction, evaluated on the same band measurements. No nuisance coefficients are copied between differently centered frames, and no state is refitted. The following numbers are native likelihood NLL, excluding fitting priors; lower is better.

| Band | Full geography/timing + full correction | Full geography/timing + band correction | Band geography/timing + full correction | Band geography/timing + band correction | Factorial interaction |
|---|---:|---:|---:|---:|---:|
| Low | 20,075.964 | 20,359.687 | 19,925.118 | 19,619.152 | −589.689 |
| High | 12,893.536 | 13,045.543 | 13,536.480 | 13,372.117 | −316.370 |

At full correction, the low geography/timing state improves low-band NLL by 150.846, while the high state worsens high-band NLL by 642.945. Substituting either band correction alone worsens NLL, by 283.723/152.007. The negative interactions explain why these separate swaps cannot be added to predict the joint result. In particular, the high-band historical endpoint has worse same-support likelihood than the full endpoint; the prescribed fixed-position nuisance profiles are a concrete way to test whether its local calibration/association solution can improve under the unchanged objective.

| Band endpoint versus full endpoint on identical support | Mean native posterior TV, including clutter | Satellite-or-clutter MAP changes | NLL change, RX0 | NLL change, RX1 |
|---|---:|---:|---:|---:|
| Low | 0.1845 | 310 / 1,692 (18.32%) | −318.771 | −138.041 |
| High | 0.2059 | 225 / 1,106 (20.34%) | +611.486 | −132.905 |

Thus high-band receivers disagree in the direction of the likelihood change. High blocks 4 and 5 contribute +434.235 and +190.881 NLL respectively and together account for 48.47% of high-band posterior TV; other blocks partly offset their likelihood penalty. Low-band changes are more distributed: its largest TV contributions are blocks 14, 9 and 10. These grouped differences do not assume the receivers or bands observe the same transmitter.

Full-state RX0 occupancy is led by catalogue numbers 65640, 57789 and 59647; RX1 by 60368, 60376 and 67645. The low endpoint's largest occupancy is 62999, while the high endpoint's is 65640. Native coarse-cell occupancy also changes: low cell −1 signal mass moves from 622.34 at the full state to 668.19 at the low state; high cell −1 moves from 451.14 to 341.04. All reported posterior sampling-integer mass remains at zero. This describes the stored sampling-lift convention and does not remove the sampling-circle ambiguity.

## Failure preservation and next action

V1 remains a failed, source-archived diagnostic. Three low-band windows with subnormal signal mass exposed quantization in moments computed before conditioning, causing absolute mean to exceed RMS. V2 normalizes posterior weights before moment products; it changes no likelihood, posterior, signal/clutter mass, candidate, prior or physical prediction. Twenty-nine component synthetic tests cover likelihood replay and thirteen tail-moment regressions. No scientific fits were repeated for this repair.

The prescribed **eighteen fitted-only, fixed-geography nuisance profiles** have since completed, using the original six all-band physical seeds at each of the three training-selected anchors. Their [separate results](../2026_10_13_ds21_039_root_cause/OPTIMIZATION_RESULTS.md) establish an optimization deficit and retain the nonstationary attempt. The current association evidence supports neither blanket bank expansion nor identity-based association constraints.

Provenance: root terminal `reports/2026_10_13_ds21_039_root_cause/local/diagnostics-v2/terminal.json`, SHA256 `1e082d95de47715ef600d000adb9b89dbd4f722bda7b33754b560aa0388f15aa`; bound protocol SHA256 `d6ac7aa2e9b9fc32c9c1cb1713cc8a4b3ac1b63e167671ba5c56fae138c3fd52`; training handoff SHA256 `27bd4bbb567c6d16a819467f92924b813d5547928dc6c51bcaba743924917356`. Findings use only the terminal-bound `association-all`, `association-low`, `association-high` and `association-cross-view` receipts. This report author performed hash checks and receipt arithmetic only, with no numerical model replay, orbit calls, held/reference reads or optimizers.
