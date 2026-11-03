# Full-observation single-scan IID estimator

Declared before any position fit in this family. The question is whether using
all observations already available within one recording improves its position
over the historical training-only estimator. This changes the estimation data
budget, not the independent Student-t4/100Hz model. It is not a like-for-like
held-prediction comparison or a new noise model.

Keep every admitted track, candidate bank, full-catalogue divisor, original
training-mask visibility rule, profiled 1MHz CFO prior, geometry and timing
bounds. Copy masks in memory; never mutate original documents or exports.
The `original` control keeps the mask; `all` uses every available observation
to fit position, timing, CFO and candidate evidence. Candidate admission remains
conditional on the original training export and is a limitation of this test.

First test exact original score/gradient parity and mask isolation; test the
all-data score against direct normalized full-observation profiles, gradient
agreement, and dependence on previously held values. Run a control on index0.
Then screen only `all` on indices0,4,8,12,16,20,24,28 using the standard four
starts, 90second caps, at most three total single-thread workers and unchanged
numerical qualification. Select only the highest qualified fitting score.

Advance only with all8 qualified, at least5 paired geographic wins, at least10%
lower median and nonworse P90. Then evaluate unchanged on remaining24 and the
previously exposed additional12, retaining failures. Require lower matched
median and mean, nonworse P90, majority wins and no coverage loss in each before
fresh disjoint confirmation. Reference coordinates never enter estimation.

The harness's common-IID `held` diagnostic reuses fitting data for `all`; label
it in-sample and never count it as predictive validation. No new RF, pooled
recordings, production edit, reference shrinkage or fitted error correction.
