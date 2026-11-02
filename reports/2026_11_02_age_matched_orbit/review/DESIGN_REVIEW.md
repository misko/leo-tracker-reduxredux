# Independent pre-fit design review

The next investigation should first validate its archive construction and
physical coordinate transport, without new position fits. The previous B model
mixed historical forecast age, signed catalog differences and variance. Its
revision spread is a proxy, not measured orbit error. Age matching removes one
confounder but does not establish a calibrated covariance.

The proposed old-to-new historical pair uses the newer TLE epoch as the common
forecast target and an arc with the current observation duration. Its horizon
should match the current nominal propagation age at the observation midpoint.
Record both element epochs and collection receipts: an older element available
only after the target time cannot be described as an operational forecast made
before that target. For historical covariance construction both records must be
available before the RF cutoff. Archive prediction validation has the stronger
requirement that every training input precedes the held prediction's issuance;
the held newer revision is an outcome and cannot also calibrate that prediction.

Historical standardized coefficients cannot be transported directly into the
current standardized bank. Infer innovations in physical mean motion (rev/day),
inclination (degrees) and RAAN (degrees) using historical nominal tangents, then
divide by the actual current declared physical mode SDs. Historical tangents
must use the intended phase-centered mean-motion perturbation. Keep the current
bank's incumbent phase convention unchanged; phase projection makes different
anchors equivalent only to first order. Check the transported current columns
against direct physical perturbations and report nonlinear/finite-difference
agreement, representability and column-normalized rank. No unsupported residual
state direction becomes a new coefficient.

Maintain the original zero prior mean. Report signed historical means and
centered variance separately; do not silently reinterpret a persistent signed
revision as random scatter or introduce a mean correction. One fixed shrinkage
strength toward the incumbent covariance and explicit support fallback are a
reasonable bounded first experiment. If shrinkage is learned globally, its
archive data must be available before the earliest evaluation cutoff it will be
claimed to serve. Later catalog revisions cannot calibrate an earlier scan's
prior while retaining a prospective causal claim.

The root's prospective support tiers are primary with at least three disjoint
pairs and exploratory with at least two. They reuse the same fixed .5 shrinkage,
variance floor, SD4 ceiling and RF qualifications, and require no duplicate
position fits. Keep their support/selection counts separate. With only two
innovations the centered sample spread has rank at most one and the uncentered
second moment rank at most two; shrinkage makes a proper covariance but supplies
no additional empirical calibration. The exploratory tier is a revision proxy,
not an estimated three-dimensional error distribution or a predictive success.

Randomize whole archive groups with a recorded seed. Reused TLEs/epochs and
overlapping forecast transitions belong to the same group. Repeated satellites
and shared catalog snapshots also carry dependence; grouping by satellite alone
does not eliminate common revision errors. Prefer disjoint update/source groups
or explicitly qualify the remaining dependence. If graph connectivity leaves
too few independent groups, report insufficient validation support. Do not
discard a disagreeing group or loosen eligibility after examining its score.
Use a normalized forecast density with an unchanged-prior control, and report
quadratic, covariance-volume and signed-innovation effects separately. A better
revision score is not a localization result.

The four-case old-B diagnostic is explicitly posthoc development evidence. It
may describe DS26-0309/0307 improvements and DS26-0315/FRSH-0004 regressions, but
must not turn these labels into classifier features, thresholds or exceptions.
Saved mode and receiver posteriors are absent from the old numerical receipts;
absence must remain explicit unless a separate bounded fixed-endpoint replay
is authorized. Saved phase vectors and historical projection coefficients are
available and can be compared without fitting.

For the replacement of C, first report a **prior sensitivity diagnostic**, not a
new acceptance threshold. At saved endpoints, use the identical other-family RF
rows and jointly reestimate/integrate their shared receiver, phase and orbit
nuisance under a predeclared physically calibrated range of finite priors.
Vary physical prior strength separately from receiver/noise assumptions. Show
the normalized contrast, residual quadratic, log determinant, nuisance pulls
and family-deletion sensitivity throughout that range. Do not freeze hardware
learned from the target. These are conditional support curves, not prior-free
proof, calibrated probabilities or a localization guarantee. The earlier
unrestricted projection remains a limiting diagnostic; it should not be
rescued by a lower threshold selected after geographic outcomes.

Any subsequent position experiment requires the root's approval, a frozen
model/roster and matched c=0/fitted-c inputs, identities, observations, starts
and maximum budgets. Preserve failures and fallbacks and seal RF decisions
before new geographic reporting. No production or previously frozen source
changes are part of this investigation.
