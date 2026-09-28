# Fixed-position temporal covariance shadow

Use all eligible tracks from the existing first eight records of each DS7,
DS8 and DS9 panel. Freeze each dataset's published polished baseline position,
timings, per-candidate stationary offsets, visibility and retained bank. No
position/offset refit, waveform reads, catalogue propagation or new RF.

Compare independent Student-t4 errors at scales 100/300/1000 Hz with one
multivariate Student-t4 per track at the same scales. The multivariate scale
matrix is sigma² [0.8 exp(-|dt|/tau) + 0.2 I], with tau 1/10/60 seconds;
tau=0 is defined as I. Its zero-correlation control still has one shared latent
track scale and therefore differs from independent Student-t observations.
All times come directly from frozen observation exports. The nugget preserves
positive definiteness for duplicate times. Marginal variance is twice the
scale matrix. These are 15 prespecified arms, not tuned on held outcomes.

Training candidate scores use the marginal training density and original weak
offset penalty; visibility and full-catalogue normalization are unchanged.
Recompute candidate weights separately for each arm. Held score is exact
log mixture joint density minus log mixture training density. This conditions
on training observations with the correct multivariate-t degrees of freedom
and scale; held values never enter fitting or arm selection. Training-only
offsets were fitted under the original iid likelihood, so this is a shadow
screen, not a fully optimized covariance model or new location estimate.

Select maximum summed training score separately within iid, multivariate
tau=0, and multivariate tau>0 families, ties by arm order. Also select donor
hyperparameters on the other two datasets' summed training scores and score
the target at its own already fitted position/offsets. This is covariance
hyperparameter transfer, not geographic leave-one-dataset-out validation.
Archive all arm scores and per-track scores. Evaluate selected arms vs the
original iid100 and tau=0 control. Promote only for a future position-refit
experiment if correlation adds held score beyond the shared-scale control
in all three datasets under both within-dataset and donor selection.

Diagnostic training-only variograms use the original training MAP residual,
clipped to ±500 Hz and divided by 100 Hz, for within-track pairs at lags
(0,1], (1,5], (5,20], (20,60], (60,infinity) seconds. Preserve zero-lag pairs
in a separate bin. Compare with one deterministic within-track shuffle
(seed 20260928); this is descriptive, not an uncertainty or significance test.

Run three sequential workers, each capped at 120 seconds and 4 GiB, BLAS one
thread. No retries. Record failures, resources, source/input hashes. Require
the iid100 replay to agree with stored per-track held scores within 1e-7 nats.
Check the multivariate-t conditional identity independently by Schur complement
in tests. Previously exposed outcomes make this exploratory research.
