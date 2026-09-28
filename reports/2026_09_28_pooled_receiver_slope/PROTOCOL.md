# Paired eight-record fits with two pooled receiver slopes

Compare the first eight chronological records of DS7, DS8 and DS9 as three
separate pooled observation budgets. Use all eight records in each fit or mark
that dataset unavailable. DS8 requires the separately documented preparation
and bootstrap; earlier missing-result ledgers stay unchanged. Reuse the frozen
DS7 and DS9 joint baseline requests/responses, with their existing candidate
banks and full mixtures. Do not combine independent positions by averaging.

Both arms fit one horizontal position and eight recording timing offsets. The
control fixes both residual slopes at zero. The augmented arm adds exactly two
native-Hz/s linear frequency residual slopes, indexed by software receiver 0/1
and shared across all eight recordings/channels. Use the established canonical
conversion 11.2 GHz / track RF and time relative to each recording's start;
per-track stationary frequency offsets absorb intercept differences. These are
phenomenological nuisance terms, not measured receiver clock drift, calibrated
hardware corrections or receiver-tilt geometry. No independent drift prior is
claimed. Bounds ±20 Hz/s are a declared sensitivity range, not hardware limits.

Retain Student-t(4,100 Hz), candidate normalization/visibility, stationary offset
penalty, masks, nominees, origin, position bounds ±12 km and timing bounds ±5 s.
Both arms start from the qualified historical joint baseline position/timing,
with common timing perturbations 0, -0.25 and +0.25 s, clipped to timing bounds;
augmented slopes start at zero. This is a paired local search. Historical
DS7/DS9 fits and the new DS8 bootstrap retain their original broader starts.

Replay historical training score at zero slopes within absolute 1e-7. Use
L-BFGS-B maxiter100, maxfun180, ftol1e-10, gtol1e-5, maxls30. Persist every start;
select highest training score among successful starts. Qualification requires
success, no coordinate within 1e-3 of a bound, and max absolute coordinate score
gradient <=0.01. Report unqualified estimates and all failures without choosing
an alternate solution by held or geographic score. Each arm has a separate
300-second/4-GiB cap, one thread, nice19; at most two numerical jobs overlap.
No retries, cap extensions or replacements.

Seal all fit outputs before reading geographic references. Score shared position
against the dataset's bound operator reference, report each record's held full
mixture and paired differences, and retain individual-baseline results separately.
These are already exposed, unsurveyed same-site panels. A pooled improvement
does not establish individual-record accuracy or new-site generalization.

At qualified interior augmented optima, audit the observed full-mixture Hessian
using central gradient differences with steps 0.02 km for position and 0.002
for timings/slopes, then half those steps. Preserve visibility changes, raw
asymmetry and step sensitivity. Profile all eight timings and both slopes via
the Schur complement and compare position information with slopes held fixed
at the same augmented point. Positive nuisance/position information is required
for an interior identifiability claim; report two-step stability with a 3%
relative-matrix tolerance, not as calibrated confidence intervals. Each dataset
curvature audit is separately capped at 180 seconds/4 GiB. Missing, unstable or
nonpositive curvature blocks an identifiability claim, not result reporting.

Geographic and held improvements, coverage, start sensitivity and curvature
must all remain visible. This research comparison cannot on its own promote a
calibrated clock model or fulfill reliable sub-kilometer performance across
the datasets. No new RF, IQ or bank propagation is used beyond the separately
bound DS8 preparation.
