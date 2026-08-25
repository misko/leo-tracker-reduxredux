# Causal CFO/rate/acceleration development protocol

This protocol freezes a bounded development-only comparison before aggregate
odd-Qin forecast outcomes are computed. It is bound to repository commit
`2e17b4477b38494e14bab7ff39303cf3a219bb03` and the exact
`rate_development` role in
`config/analysis/doppler-experiment-dataset-policy-v1.json` (SHA-256
`5eb6751b5e006c23b5186fd3e57801c58fa79cd47e3c1d66f61af2d049c00a3e`).
No `holdout_foundation` capture is authorized or consumed.

## Frozen data disposition

The benchmark consumes only two digest-closed, already serialized parity-split
products:

- three recent dwell frame inventories, manifest SHA-256
  `4e63378b6d30ba94fac645516b7b3faae405fa1e39af7db4223a0814858b642f`;
- seven opened H-capture tile inventories, manifest SHA-256
  `4028d817aab24077d590fc380034babca7208dba9bee4b405b9ee0a5a4fecd3b`.

The six August-24 development captures remain in the capture ledger as
non-evaluable: their committed filter products do not separate even-Qin CFO
training measurements from odd-Qin response measurements. Raw IQ will not be
re-extracted to rescue them. All five failed H replay tiles in the pinned
checkpoint ledger are also retained; successful neighboring tiles do not erase
those failures.

The frozen upstream Standard source, epoch, alias, and trajectory hypotheses
were chosen before this experiment and were not end-to-end odd-Qin-independent.
The claim here is consequently conditional on those hypotheses. Within this
experiment, odd Qin is response-only: it cannot update or select a state,
define target membership, change a support mask, choose a mode, trigger a
gate, cause a retry, or define a segment.

## Frozen state and baselines

The candidate is a causal robust local-quadratic state
`[CFO, rate, acceleration]`. At every supported cutoff it fits the design
`[1, dt, 0.5 dt^2]`, centered on that cutoff. It defaults to a 500 ms history
and applies a zero-centered `1000 Hz/s^2` acceleration prior for stability.
Only sustained, same-direction evidence from past/current even-Qin data can
shorten the history to 125 ms: eight consecutive points spanning at least 8 ms
must have both a long-state one-step residual of at least 125 Hz and a
short-minus-long rate difference of at least 350 Hz/s. Recovery requires at
least 250 ms in short mode plus 32 calm points spanning 250 ms, with residual
at most 75 Hz and rate disagreement at most 175 Hz/s. This is deliberate
hysteresis, not a longest-compatible-history selector.

The identical-mask baselines are robust causal lines over 500, 125, and 20 ms.
All methods use a 50 Hz measurement scale, Huber tuning 1.345, minimum 95%
history span, at least 12 frames and eight effective frames. A new dwell, tile,
or supported-point gap over 100 ms is a hard reset.

## Frozen response and metrics

Targets are sampled every 15 frames and are eligible only from even-Qin
qualification. For 125, 500, and 1,000 ms forecasts, the causal cutoff is the
latest supported training frame no later than the target time minus the
horizon. Candidate and all baselines must exist at that exact cutoff. Future
odd-Qin CFO is read only after this paired mask is frozen.

Squared errors are averaged first in device-sample-anchored one-second blocks,
then with equal block weight within capture and equal capture weight overall.
The report will include capture/horizon rows, paired yield, rate and acceleration
stability/disagreement, mode occupancy, runtime, and past-even-only strong versus
weak/ambiguous strata. No covariance calibration is claimed, so NIS and 68/95%
coverage will not be reported.

This is development evidence, not a new holdout. The candidate is called
promising only if its equal-capture RMS is at most 95% of fixed 500 ms at all
three horizons, no supported capture/horizon is more than 10% worse, and at
least seven captures provide 50 targets in three blocks at every horizon.
Passing cannot establish physical Doppler truth, identify a satellite, or
authorize production promotion.

## Likelihood-gate disposition

A past-only gate is frozen as: invoke summed/full likelihood when the even-Qin
exact-minus-control log-likelihood or top-minus-second log-likelihood is below
`4.605170185988092`; otherwise retain the ordinary continuous profile. The
available serialized frame products contain neither per-frame even-Qin
likelihood surfaces nor both gate features. The real-data gate evaluation is
therefore frozen as **unavailable**, and raw extraction is forbidden as a
post-outcome rescue. Its causal decision logic will still receive unit tests,
but it will not be assigned a real-data performance number.
