# DS21-039: matched observation-weighting control

The original all-band solution has 60.47% of its windows in CH1–4 and 64.01%
in its larger receiver stream. The completed frozen-state diagnostic found that
equal acquisition-block weights weakened the high-band comparison without
reversing either within-band ranking. The subsequent geographic continuation
improved training objective substantially but position error only from 4.291 to
4.073 km. These findings justify testing weighting in an actual fit; they do not
show that a weighting change will improve localization.

Three predetermined alternatives will each receive four identical initializers:

| Weight scheme | Construction before fitting |
| --- | --- |
| Equal band | Each band receives half the total likelihood weight |
| Equal acquisition block | Each represented original 20-second observation-center block receives the same total weight |
| Equal band, then block | Each band receives half the weight, divided equally among its represented observation-center blocks |

Weights are constant within the named groups and normalized to sum to the
original **2,798 training windows**. This keeps the aggregate likelihood/prior
scale matched. Blocks use the existing diagnostic's center-time convention;
this experiment does not change the observation partition or claim that these
blocks, receivers or native alternatives are statistically independent.

The likelihood is the weighted sum of the original normalized singleton-window
mixture NLLs. Its gradients receive the same weights. The conditional satellite,
native-branch and clutter posteriors retain their original probability meaning.
The existing common/relative timing and group-calibration priors are counted once
with unchanged strengths. The weighted implementation must reject temporal edges
rather than treating a coupled sequence as independent windows.

All arms use the original 43-satellite bank, source measurements, native receive
times, recorded RF, calibration frame, ambiguity convention and **fitted c**.
The four starts are exactly the original all-band winner and the three sealed
cold-profile winners used by the completed seven-call refinement. They are fixed
before any weighted fit and use the original physical seed-5 center and 25-km
disk. Each gets 20 seconds and 600 iterations: **12 new calls**, at most 240
optimizer seconds, inside a separately frozen bounded run.

The four unweighted free continuations already completed under the same starts
and budgets supply the matched baseline. Unit-weight objective, likelihood and
gradient closure must pass before the weighted control. The baseline's retained
fully stationary incumbent remains a valid baseline candidate; it is not assumed
stationary under a changed objective. Each weighted arm selects only from its
new stationary free fits, by that arm's training objective. Failed or
nonstationary outcomes stay visible; no reference-based winner selection occurs.

Weighted objective values are comparable between starts within an arm. Across
arms, report the weighting change explicitly and retain unweighted NLL and prior
costs as separate diagnostics. Position error is joined only after each selector
is sealed. No improvement claim may be based solely on weighted fit or conditional
residual RMS, and no error-tuned search over weight strengths is part of this test.

The implementation and exact source/input/parent bindings will be frozen before
execution. The prior diagnostic, 18 cold profiles and seven continuations remain
immutable. No new RF collection, held scoring or locked evaluation is involved.
