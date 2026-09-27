# DS6 matched position refit: receiver curvature

Quadratic receiver drift is not adopted as an accuracy fix. It improves
held-out predictive density on all four frozen development scans versus linear
drift, but geographic error worsens on three of four versus no drift. The
all-43 fixed-position residual improvement therefore does not establish a
geographic improvement.

| Sample rate | Scan suffix | No drift error, km | Linear error, km | Quadratic error, km | Quadratic minus linear held log-score |
|---|---|---:|---:|---:|---:|
| 2.5 MS/s | 5eaaa2a8f8c995b3 | 3.670 | 4.664 | 7.960 | +29.85 |
| 5 MS/s | c78fb2dba2465361 | 8.482 | 8.540 | 7.036 | +15.94 |
| 7.5 MS/s | c7e37f65ae9e08b0 | 0.505 | 0.901 | 0.853 | +1.64 |
| 10 MS/s | 3221795d82a1c7ec | 6.284 | 7.003 | 7.025 | +36.60 |

The four scans were selected by the earlier rate-representative development
protocol, before this experiment's outcomes. The new protocol binds all 43
inputs, but only these four were refitted. The other 39 are untested, not failed
or missing. The negative development result does not justify a full rollout.

All arms use the same inherited catalogue mixtures, training-only profiled
track offsets, fixed 100 Hz Student-t4 scale, starting positions, three timing
starts and location/timing bounds. Linear and quadratic drift share a 750 Hz
coefficient prior. Their training-centered polynomial basis is normalized by
11.2 GHz / actual RF; optimizer coefficients use 100 Hz units. No hard MAP
identity is substituted for the inherited candidate mixture.

Optimization uses penalized training likelihood only. The sealed random
whole-visit holdouts are used for prediction scoring. The separate summarizer
loads the operator roof coordinate only after a complete result exists and
records its hash and each result's hash. No reference coordinate is used to fit
or select optimizer starts.

All twelve selected winners converged inside the search bounds. Two of the
36 starts reported abnormal line-search termination and remain in the outputs;
neither was the selected winner. Exact propagation at each winner differs from
interpolated predictions by less than 0.05 Hz. Three tests passed: equality to
the original zero-drift model, synthetic curve recovery with held-data
isolation, and frozen real-data provenance/selection/propagation checks.

This remains a local conditional inference. The donor center is itself from a
DS6 development scan, and inherited no-drift candidate shortlists may omit mass
under more flexible drift. The results do not prove the fitted polynomial is a
physical receiver clock error. Repeated predictive gains without geographic
gains argue against adding still more unconstrained drift terms as the next
step; orbit/measurement systematics and their geometric confounding need
independent evidence.

A follow-up metadata audit (`audit_element_age.py`, `element_ages.json`) found
that the training-MAP candidates' median element ages at capture were 25.50,
20.69, 23.97 and 19.14 hours for the 10, 2.5, 5 and 7.5 MS/s scans respectively.
The oldest selected element was 71.09 hours old. These ages are descriptive:
they neither confirm candidate identity nor measure ephemeris error. The next
useful check is sensitivity to different causally available element sets for
the same satellite, with matched location refits if those orbit differences
are large enough to affect the observed residuals. Do not use later snapshots
silently or replace orbit uncertainty with a ground-truth correction.

The verified all-43 joint position remains 772 m from the operator reference;
the independent-scan baseline remains 6/43 sub-kilometre. Neither result is
replaced by this experiment, and the broader accuracy goal is not complete.
