# Native C satellite-offset prototype qualification

The proposed constant satellite frequency-offset model passes real-data zero-tail and derivative qualification on the current C053 training state. This establishes implementation compatibility, not an accuracy improvement. The eight-call conditional development comparison is prespecified separately and has not yet run.

| Check | Result |
| --- | --- |
| Full 1,870-window zero-tail objective/gradient/posterior maximum discrepancy | 3.63798e-12 |
| Fold 0, 873 windows, zero-tail discrepancy | 0 |
| Fold 1, 997 windows, zero-tail discrepancy | 0 |
| All 58 nonzero satellite-offset coefficient derivatives, maximum finite-difference error | 2.53344e-9 |
| Objective evaluations / optimizer calls | 123 / 0 |
| Scientific elapsed time | 16.580 seconds |

The original attempt `model-c-offset-qualification-053-v1` stopped after one source replay because the prototype requires a plain native receiver-clock model while the actual source uses `NativeClockPriorView`. No fit ran. The failed namespace and source snapshot remain preserved.

Version 2 uses an explicit adapter that accepts only the all-window, unchanged-prior clock view. It rebuilds the plain native-clock layout and requires exact clock/group matrices, priors, bounds, baseline and initialization equality. It rejects band-masked views and changed clock priors. The original frozen source is evaluated before adaptation for the full zero-tail comparison. Ten component tests pass, including actual-layout adapter closure, every physical/calibration/offset derivative, exclusion of held-out native CFO measurements from fitting terms, and separate satellite-tail fitter metadata; Ruff passes.

The model uses a zero-sum catalogue basis, sigma 50 Hz prior and unchanged satellite timing priors. A fitted offset is a statistical correction, not an identified transmitter clock. The forthcoming comparison must report timing and offset penalties separately, since those directions can be strongly confounded.

Implementation commits: `ddbba146d` (model), `152d46aa6` (protocol and first qualifier), `22e7d0eb7` (explicit adapter and version 2). Frozen successful experiment: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-offset-qualification-053-v2`.

- Result SHA256: `95c9ea07cc358bc5ccca56164707c2a79f74f6615415c5a93e4ec0e2f538ddfa`
- Seal SHA256: `d40c23e81b20586c266d133e20855cc391e68a1464e8b56f14c73e9cfa81a520`

No reference or original held/locked observations were used. Original cohort results are unchanged.
