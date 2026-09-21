# Shared orbital corrections with uncertain satellite identities

This experimental extension **did not improve position accuracy** on the archived
campaign. In a matched comparison, adding identity uncertainty reduced residuals
slightly while changing horizontal error from 2,007 m to 2,040 m. It is not the
model that produced the formal fixed-identity 328 m result and is not promoted
for operational use.

## Matched experiment

Both arms use the same 622 episodes, 21,702 observations, strictly causal
catalogues, randomized fitting/evaluation split, fixed receiver UTC and altitude,
zero-mean Gaussian phase-rate prior (0.09176616 s/hour), ±0.25 s/hour rate bounds,
and iid pseudo-Huber signal scale of 250 Hz. Each NORAD has one shared correction.
The joint model sums over candidate identities and a broad unassigned component;
rates are MAP estimates, not integrated orbital uncertainty. Source offsets use
training arithmetic means before robustification, a declared approximation.

The fixed arm retains the strict winner; the joint arm contains 7,462 candidate
rows across episodes and 4,368 distinct candidate NORADs. Candidate prior mass
uses the full catalogue population rather than renormalizing the shortlist.
Both arms start at the same earlier RF-derived strict solution within a ±500 km
local box. This is local refinement, not global acquisition of unknown identities.
Receiver truth is applied only after both fits are saved.

| Metric | Matched fixed identity | Joint identity mixture |
|---|---:|---:|
| Horizontal error | 2,007.3 m | 2,039.9 m |
| Pooled training-leader training RMS | 78.55 Hz | 76.74 Hz |
| Pooled training-leader randomized held-out RMS | 83.03 Hz | 80.99 Hz |
| Held-out mixture log predictive score | −49,688.56 | −49,678.08 |
| Converged | yes | yes |
| Runtime, single BLAS thread | 6.6 s | 77.9 s |

Thirteen of 622 training-leading identities changed. The held-out predictive
score improves by 10.47 summed log units, but position error increases by 33 m.
No identities are reselected using held-out values. The pooled RMS scores above
use each episode's training-leading candidate with frozen fitted parameters;
the predictive score additionally includes identity uncertainty.

The formal 328 m model differs in its learned causal nominal phase predictions,
correlated Student-t noise, fitted noise scale, and iteratively relinearized
quadratic orbital states. Therefore the difference between 328 m and 2 km cannot
be attributed to identity mixing. The matched two-arm comparison above is what
isolates the effect of identity uncertainty in this prototype.

## Numerical validation and failed attempts

The ragged vectorized objective is checked against an independent loop oracle
and central finite-difference gradients. Additional tests cover candidate
permutations, shared satellite parameters, unassigned support, and strict
held-out isolation. Predictive scoring retains log probabilities even when a
displayed posterior rounds to zero.

An initial bounded Powell outer search left the useful local basin and returned
an unconverged joint fit. It is saved as a failed diagnostic. A common 10 km
Nelder–Mead simplex recovers converged matched fits. Solver choice and all
selection use the training objective, not known receiver coordinates.

The fast model uses first-order Doppler phase sensitivities. Exact propagation
and omitted-catalogue support checks govern whether its output is trustworthy;
an uncertified shortlist is not interpreted as an established satellite identity.
The audit artifacts retain those statuses explicitly. No production catalogue
association thresholds are changed by this experiment.

The completed [exact audit](artifacts/2026_09_21_shared_identity_orbit/shape-audit.json)
rebuilds 211 causal catalogues, verifies their cached digests, and propagates
every retained model candidate at its fitted rate with SGP4. The joint model's
linear approximation differs by 11.63 Hz RMS and up to 534.61 Hz. Even after
removing each error curve's training-fitted constant offset, the difference is
7.42 Hz RMS and up to 544.99 Hz. It fails the declared 0.2 Hz maximum tolerance.
The formal fixed-identity model's quadratic-state approximation passes that
tolerance; this first-order prototype needs the same treatment before adoption.

The omitted-population check allows every omitted candidate its maximum possible
likelihood after any phase correction. This is conservative but too loose: its
worst-case omitted fraction bound is approximately one. That does **not** mean
the omitted satellites actually have that posterior; it means this bound cannot
certify the shortlist. A tighter corrected full-population calculation remains
necessary. The prototype is retained as a tested negative experiment, not as a
qualified replacement for the formal estimator.

## Artifacts

- [Sealed matched fit and all episode posteriors](artifacts/2026_09_21_shared_identity_orbit/fit.json)
- [Evaluator-only position and RMS scores](artifacts/2026_09_21_shared_identity_orbit/evaluation.json)
- [Exact propagation and conservative support audit](artifacts/2026_09_21_shared_identity_orbit/shape-audit.json)
- [Retained causal TLE records used by the audit](artifacts/2026_09_21_shared_identity_orbit/shape-audit.retained-tles.json.gz)
- [Candidate phase-state cache](artifacts/2026_09_21_shared_identity_orbit/candidate-phase-states.npz)
- [Superseded failed Powell comparison](artifacts/2026_09_21_shared_identity_orbit/superseded-powell-fit.json)
- Estimator: `src/leo/analysis/research/orbit_identity_mixture.py`
- Runner: `tools/run_shared_orbit_identity.py`
- Separate audit: `tools/verify_shared_orbit_identity.py`

The independent per-episode Gauss–Hermite integration helper in the same
numerical module is a separate diagnostic. It does not represent shared
per-satellite orbital uncertainty across episodes.
