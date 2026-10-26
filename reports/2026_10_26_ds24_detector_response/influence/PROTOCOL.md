# Accepted-owner measurement susceptibility panel

Select only DS24-0010 and DS24-0011, the first two chronological usable cases.
No evaluation coordinates/errors, target residuals, catalogue competition,
IQ or detector calls enter selection. These are exposed development scans.

Reuse the exact four saved parent local Gaussian designs from the original
nomination-information study. They retain all original curved and predictive
rows, shared nuisance priors/covariance and frozen Gamma/noise conventions.
No geometry reconstruction, new optimizer or ablation fit. Original absent
physical-mode columns remain absent, with that model limitation exported.
The calculation is a local frozen-mean surrogate, not the full variational
objective's derivative or calibrated achieved accuracy.

Let G=prior+U'WU, C=U'WJ, R=J−U G^-1 C and I the saved marginal position
information. Response to a data perturbation is H=I^-1 R'W. Recheck
J'WR=I. Use each arm's ORIGINAL saved weak unit axis, not one axis selected
after examining changes. All old predictive observations enter once.

For a family or owner, construct degree<=2 Legendre functions of its original
times, QR orthonormalized under equal native-ID weights. Multiply by sqrt(N)
so coefficient unit norm produces 1 Hz RMS at reference RF11.5GHz, then by
native RF/11.5GHz. Susceptibility is ||weak' H_subset B||2, km per reference
Hz RMS. It is the worst response within this declared quadratic perturbation
space, NOT information gain, measured bias, an orbit error, or geographic
improvement. Report1Hz and20Hz linear movement proxies, both arms separately.

Inventory every original owner and complete native ID set. An owner is
eligible only if it has>=20 points and ALL its IDs are in BOTH original
curved-likelihood sets. Partial curved owners, predictive-only, postfit-only,
and excluded owners remain explicit excluded rows. Family response uses all
its current position-likelihood rows, including old predictive rows; owner
selection is among the eligible complete curved owners only.

Rank families by the smaller c0/fitted-c susceptibility, descending, with
numeric family label tie break. Select the top family having an eligible
owner, then that family's top owner by the smaller arm score, component tie
break. A lower-influence control is selected from the bottom quartile of
positive-score eligible families (max(1,ceil(F/4)) families), excluding the
target family. Prefer a different receiver from the target when available;
then choose lowest paired family score, lowest paired owner score, component.
If no control exists, keep it unavailable; no replacement case or rule change.

Within each selected COMPLETE owner, sort by original time then native ID.
Request indices floor(.25*(N−1)+.5) and floor(.75*(N−1)+.5). Four owners give
at most8 physical window requests. Missing authority does not change selected
owners or time indices. Preserve all owner points in the ledger.

Each request binds tracking path/hash, original probe/receiver/candidate,
sample counter, RF, original native observation ID and winner CFO/margin.
Acquisition CFO is absent from these historical tracking contracts and stays
null. Raw authority comes from the sample's explicit source input manifest and
public FastSegmentSource/ShortWindowReader constructors plus typed declared
index references. Metadata only: do not call windows(), read/decompress IQ,
or claim detector parity. Preserve every missing/permission/contract failure.

Owned algebra/basis/permutation/quantile tests and actual saved-array shape,
hash and complete native-row mapping smoke precede B's matching preflight.
No actual susceptibility ranks before approval. One bounded run after PASS,
<=180 cumulative numerical seconds including metadata/setup/tests, one worker
and BLAS thread. Prior exploratory metadata reads charged conservatively2s.
No source replacement, positions, satellite changes or production edits.
