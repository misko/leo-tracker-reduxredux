**Cross-family ephemeris dependence: existing tests and remaining scope**

This note is a read-only source/result inventory, not a new experiment. Historical
TLE innovations are imperfect orbit-error proxies; none of these tests uses
authenticated satellite truth.

| Existing test | Saved result | Interpretation |
| --- | --- | --- |
| Causal neighbor phase-mean forecast, lagged at least 300 s; global and orbital-plane weighting; temporal and satellite-disjoint qualification. | Full 410-case policy fitted-c mean 1.498002046 to 1.500346635 km; c0 1.508507217 to 1.510628594 km. 69 forecast-qualified, 67 paired-valid; other cases retain the reference. | Neighbor innovations were tested across satellites and propagated to position, without broad accuracy gain. This is a mean forecast, not a covariance model. |
| Publication-event exchangeable phase dependence. | Explicit implementation and qualification precede the geometry study; that study retains it as a trained control. | Publication-block dependence is already considered, not a newly proposed missing mechanism. The rotated independent-Student construction is not an elliptical Student law. |
| Geometry-dependent covariance, unit orbit-normal or concatenated radial/velocity kernels, rho grid 0,.01,.03,.1,.3,.6,.8. | 0/24 contexts qualify; two lack enough whole events. | Elliptical Student model preserves univariate marginals but adds shared-Gamma tail dependence even at identity covariance; independent-Student and common-Gamma/global controls are explicit. Failure does not establish cross-satellite independence. |
| Geometry-dependent Gaussian copula with unchanged univariate Student marginals and no shared Gamma. | 2/24 qualify: DS23-0082 and DS23-0385; both choose radial/velocity kernel and final rho=.03. | Some held-event and held-satellite proxy dependence exists under this model. R is latent-normal correlation, not physical Student covariance. The result does not itself establish a DS24 position gain. |

The covariance tests train on earlier update batches with NORAD mod 5 !=0 and
test later whole batches, including later held satellites with NORAD mod 5 ==0.
Prefix marginal/location models exclude those held satellites. Every declared
control must be beaten by log(N)+2 log(2), including training and both held
comparisons. Simultaneous validation groups may contain different nominal
publication times; geometry is evaluated from the historical forecast TLE, not
current RF-selected families.

The earlier DS24 phase/shape forecast tests concern correlation *within each
satellite's* timing/shape coordinates. They are distinct from the cross-family
tests above. Do not use their median timing/mean-motion correlation .054 as a
measurement of cross-satellite independence.

A future historical check would be new only if it has a specific uncovered
kernel or failure mode, new whole publication blocks, adequate independent event
count and unchanged marginal/tail controls. Repeating plane/publication pooling
on these overlapping histories is low priority. First inspect the two qualified
copula contexts and their dependence on the small number of events before
proposing any runtime covariance expansion. No such new check was executed here.

Exact source and result paths:

- [Neighbor forecast](../prior_art/source/ds23_neighbor_phase_forecast.py),
  [full matched runner](../prior_art/source/run_ds23_neighbor_phase_full.py),
  [full 410-case replay/statistics](../prior_art/results/neighbor_independent_replay_audit.json).
- [Publication-event density and qualification](../prior_art/source/ds23_shared_phase_events.py).
- [Geometry covariance and qualification](../prior_art/source/ds23_geometry_phase_covariance.py),
  [causal geometry/split protocol](../prior_art/source/probe_ds23_geometry_phase_covariance.py),
  [24 saved outcomes](../prior_art/results/geometry_qualification.json).
- [Student-marginal-preserving copula](../prior_art/source/ds23_geometry_phase_copula.py),
  [24 saved copula outcomes](../prior_art/results/copula_qualification.json).
