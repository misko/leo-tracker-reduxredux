# Ephemeris uncertainty: source audit, not a new prior

**An anisotropic orbital prior is not yet justified by the available evidence.**
General radial/cross-track/velocity uncertainty is absent from B7, but its
absence is not proof of a position-error floor or a usable prior width. This
review reads source and existing reports only: no recordings, reference-error
queries, archive enumeration, propagation or model evaluations were performed.
No experiment is frozen and running work is unchanged.

## Causal inputs actually available

The operational [regional CLI](../../src/leo/cli/regional_position.py) selects the
latest snapshot strictly before `prepared.start_utc_ns - 505_000_000_000`.
[Clean reconstruction](../2026_10_09_position_error_iter131/inference_loader.py)
uses the same rule and verifies the frozen snapshot digest. The cutoff is a
collection-time causality rule, not a statement about orbital accuracy.

The public [TleArchiveReader](../../src/leo/operations/tle_archive.py) exposes
`list_snapshots`, `select_latest_before` and digest-verified `read`. Earlier
snapshots can therefore be identified through the port without constructing
archive paths or using future catalogues. `select_nearest` also exists but does
not supply the required strict causal policy. The parsed
[ElementSets epoch property](../../src/leo/sky/propagation.py) exposes actual
per-satellite epochs, separately from snapshot collection times. Neither field
supplies an accuracy covariance. Source-level availability does not prove a
usable earlier changed element set exists for every current candidate.

The [regional bank](../../src/leo/analysis/regional_position_bank.py) contains
position/velocity arrays on quarter-second nodes and NORAD identities, not
per-element covariance or calibrated update-error statistics. Operational timing
shifts traverse that trajectory. [The phase alternative](../2026_10_10_position_error_iter141/PHASE_REVIEW.md)
changes the Earth-frame interpretation of relative timing, not the dimension of
the orbital uncertainty model. B7's satellite-common frequency slopes are not
general physical orbit corrections.

## Previous tests already cover part of this question

- [Causal catalogue variability](../2026_09_23_causal_orbit_variability/README.md)
  compared actual earlier archive snapshots. The immediate pair contained
  identical elements for all 880 candidates. A bounded backward search found
  an earlier changed boundary with 858 common candidates and 22 missing. Its
  median absolute radial/along-track/cross-track differences were approximately
  57/2694/96 metres. The source explicitly calls these update differences, not
  errors against orbital truth or prior widths. They cannot be pooled as
  independent error draws: adjacent catalogues can share measurements and
  systematic errors, and update intervals differ.
- [Element-age analysis](../2026_09_23_train_orbit_age_diagnostic/REPORT.md)
  found weak conditional age/residual-slope association. It did not establish a
  scalar age correction or a causal error law.
- [The earlier orbit-arm experiment](../2026_09_24_ds1_orbit_arm/REPORT.md)
  implemented age-multiplied per-NORAD phase rates with Earth rotation held at
  receive time plus global timing. Improved frequency criteria did not produce
  a new position; negative transfer evidence remains documented.
- [Iteration 112](../2026_10_09_position_error_iter112/ORBIT_MODEL_AUDIT.md) already audited
  the explicit radial/cross-track/velocity omission and proposed a causal
  prediction-space comparison after removing existing nuisance directions.
  Repeating that proposal under a new name would not be a new scientific model.
- [Satellite offset/slope testing](../2026_10_08_position_error_iter24/README.md)
  showed that added frequency flexibility can improve residual fit while
  worsening position. An RTN label on a nuisance does not prevent that problem.

Within this scoped source/report review, no completed full DS16/17/18 B7 test of
an independent radial/cross-track state prior or causal catalogue replacement
was identified. That is not a repository-wide proof of absence.

## Identifiability and computational cost

For satellite-to-site unit vector u, satellite velocity v and range R,
first-order Doppler perturbation is

```
df = -(RF/c_light) * [u dot delta_v
                     + ((v - (u dot v)*u)/R) dot (delta_p_sat - delta_p_rx)]
```

A satellite position correction aligned with a receiver displacement can cancel
its Doppler signature. Allowing independent corrections for every satellite can
therefore absorb the receiver position rather than identify it. Radial and
cross-track directions vary over the pass; a physically meaningful state model
must couple position and velocity evolution, not add unrelated constant ECEF
components. Along-track modes overlap timing/phase, short-arc frequency trends
overlap existing satellite slopes, and common RF/time signatures overlap shared
c and receiver clocks. More rows alone do not resolve those nearly dependent
directions.

A prior makes an algebraically singular problem solvable but does not calibrate
the resulting position. A six-component state per satellite adds substantial
nuisance dimension to a model already shown to have weak profiled spatial
information. A low-rank update-disagreement direction would be cheaper, but its
amplitude and sign remain uncalibrated; a single catalogue difference is not an
independent covariance sample. Selecting the catalogue that gives smaller
in-sample frequency residuals also changes the effective model-selection
problem and does not establish better position.

## Decision and prerequisite

Do not add an anisotropic state prior, replace the causal catalogue policy, or
claim ephemeris error explains the 0.4 km gap from this evidence. No genuinely
new, justified position variant is proposed here. If the full phase comparison
leaves an unresolved common error, the existing iteration 112 diagnostic is the
appropriate prerequisite: a bounded, globally fixed earlier-changed-snapshot
rule with full missing/unchanged-candidate accounting, at ordinary reference-free
hypotheses, separating changes inside and outside existing geometry/nuisance
spans. That remains a diagnostic of catalogue sensitivity, not a prior fit.

Any later model test needs a physically coupled low-dimensional state basis,
explicit data-rank and prior dependence, one global policy with no per-scan
reference guidance, original-catalogue controls, matched c=0/fitted-c arms and
full member/failure reporting. Common c and every RF-time coefficient must be
locked in the c=0 arm. Frequency fit must remain separate from position accuracy;
consumed scans cannot establish independent validation or calibrate an orbital
error distribution solely because their receiver references are known.
