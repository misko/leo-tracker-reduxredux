# DS21-007 fitted-c joint baseline

CH1–8 achieved **3.524 km**, compared with **3.738 km for CH1–4** and
**4.325 km for CH5–8**. All 18 optimizer calls were stationary. None met the
0.5 km target. Combining bands improved this recording by 0.215 km versus the
low band and 0.801 km versus the high band; the DS21-039 combination penalty is
therefore not universal. This is a new baseline case, not a demonstrated model fix.

| View | Error km | Selected proposal | Fitted c Hz/GHz | Native residual RMS Hz | Calls / stationary |
| --- | ---: | --- | ---: | ---: | ---: |
| CH1–8 | 3.523663 | shape-all | -572.867601 | 86.133213 | 6 / 6 |
| CH1–4 | 3.738163 | cold-2 | -601.178546 | 76.420493 | 6 / 6 |
| CH5–8 | 4.324831 | cold-0 | -516.912183 | 92.098856 | 6 / 6 |

Each view used six physical proposals from the completed
[fitted-only initialization chain](PROPOSALS_007_RESULTS.md), the unchanged
joint objective at likelihood scale one, fitted c, and a maximum of 20 seconds
and 600 iterations per fit. Each start retained its original 25 km search disk.
The selected states were interior to their bounds. View runtimes were 75.117,
52.916 and 41.352 seconds, respectively; these exclude initialization and evaluation.

Receiver ambiguity lifts were derived once from each all-training proposal and
projected into all three views. Consequently, the half-band results inherit
all-band initialization information: they are not independently initialized
end-to-end half-band pipelines. No zero-c arm was run.

The all/low/high training window counts were 2,987 / 1,807 / 1,180, using a shared
32-satellite candidate bank. Each view selected its state using its own training
objective. All three selections and all 18 calls were sealed before reference
coordinates were joined. Neither reference nor held observations entered fitting
or selection. Accuracy uses the configured reference, not an independently
surveyed position. Likelihood values across views have different evidence counts
and are not accuracy comparisons.

The original matched A/B/C comparison remains five recordings. This additional
Model C case uses the explicitly fitted-only shape initializer; it does not
silently replace the historical initializer or add unrun A/B outcomes. Six of
34 fast development recordings now have completed proposal sets; 28 still need
initialization. The 20 locked fast recordings remain unopened for inference.

Implementation: `tools/ds21_fitted_joint.py`, commit `5fd13343c`.
Its 13 owned tests passed; four focused integration checks also passed, including
real small-model fitting and source-freeze checks. Compact source and result
bindings are retained in [JOINT_007_RESULTS.json](JOINT_007_RESULTS.json).
