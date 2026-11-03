# Why exact band-calibration transport can still leave a suboptimal fit

The existing public pipeline learns band contrasts in its A/B source stages,
transports them exactly, then freezes them during shared-q refinement. Changing
the other parameters can move the best band contrasts. A strict convergence
check on the restricted model does not test these omitted directions.

This audit uses only the S03 blocked training payload and saved training stages.
There is no fit, held measurement, station coordinate or parameter selection.

| Diagnostic | Actual result |
|---|---:|
| Strict joint B donor, selected source index | 2 |
| Donor transport maximum correction error | 7.28e-12 Hz |
| Donor absolute-band gradient, RX1/RX2 | 4.26e-8 / 2.62e-8 NLL per Hz |
| Legacy/shared uniform-q frequency-gradient disagreement | 3.47e-18 |
| Rebased donor band-gradient chain-rule disagreement | 1.78e-14 |
| Final shared learned-q band gradient, RX1/RX2 | +0.699 / −0.0405 NLL per Hz |
| Same final geometry/clocks, uniform q instead | +0.481 / −0.0469 NLL per Hz |

The donor is stationary in these directions, and its function is transported
without an appreciable numerical error. The final selected A source has
nonzero band gradients. Its learned q ranges from0.00432 to0.15332, so q changes
the gradient further, but the final uniform-q gradient is already nonzero.
The final A source and audited B donor are different source paths: this does
not isolate a causal effect of q alone or blame the donor selection policy.

An important negative control: with identical visibility and uniform q, the
legacy and shared conditional frequency gradients agree. Their normalization
differs, but that difference is independent of a constant frequency correction.
The conditional normalizer alone is therefore not an explanation of a band
gradient mismatch. Visibility-gradient effects are a different question.

For the old centered contrast column high−fraction and the new absolute-high
column, the relevant derivative relation is

`g_absolute_delta = g_centered_delta + high_fraction * g_receiver_intercept`.

That relation matches the actual donor to1.78e-14. Transport is not the bug
identified here. The measured concern is leaving contrasts fixed while the
coupled final solution changes. The separate training-only band profile improves
held likelihood and10 whole-scan held assignments, but no requested held points;
joint-contrast evaluation is still required before promoting this direction.

Public pinned source chain:

- `leo.application.channel_group_refinement.objective` builds the source model.
- `leo.analysis.hard60_joint_clock.JointClockObjective` uses the legacy likelihood
  by default.
- `leo.analysis.shared_scan_model.donor_state` transports the fitted correction.
- `SharedScanObjective` requires frozen contrasts and adds their once-only prior.
- `leo.application.shared_fast_position` selects sources and runs shared-q fits.

`results.json` binds the actual source receipts and script. Two component tests
verify uniform-q gradient equivalence and demonstrate that changing q can
change band gradients without changing predictions. No production code changed.
