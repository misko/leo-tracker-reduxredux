# Catalogue sensitivity decision

The completed diagnostic shows strong overlap between catalogue update effects
and existing nuisance parameters. It does not yet justify a new orbital prior,
extra orbit-fitting parameters, or a deployment change.

All twelve consumed development members completed. Eleven had an earlier changed
catalogue under the frozen causal rule; DS17-031 had no eligible distinct earlier
payload within the window. Both saved endpoint admissions passed for all twelve.
The eleven comparisons retained every original candidate. Selected catalogues
were approximately 1.01–19.97 hours older than their original snapshots.

At the fixed fitted-c endpoints, **99.9272–99.99998%** of the weighted prediction
change lies in the free local nuisance span. The corresponding zero-c range is
**99.9272–99.99998%**. The additional spatial span accounts for at most **0.0108%**
of total weighted change in either arm. These are separate arm-specific weights
on the same observations and fitted-selected satellite banks.

This is a local derivative calculation with nuisance priors and bounds omitted.
It does not show that the deployed constrained model can absorb these changes,
that the older catalogue is wrong, or that a newer catalogue yields better
localization. The unweighted frequency differences are large (about 511–8952 Hz),
so interpreting local spans as achievable finite corrections would be especially
unsafe. The calculation also freezes original responsibilities; changing the
catalogue can change association. Visibility changed in two recordings and is
reported separately, including the full-bank event-normalizer contribution.

The next useful catalogue experiment would need to measure the required
correction against the existing clock/timing priors and limits, and verify the
exact nonlinear objective under a fixed reference-free rule. A free-span fraction
alone cannot calibrate an ephemeris covariance. Prioritize the already-running
iteration 140 full-cohort phase comparison before expanding this diagnostic.

The diagnostic used zero optimizer calls. Summed member execution time was
162.458 seconds, excluding controller startup and preflight. Reconstruction
work is recorded separately from the 24 saved-endpoint evaluations. No reference
coordinates or position-error queries were used, and no RF collection occurred.

The official completed full-193 fitted-c mean remains **1.254810 km**. This
diagnostic changes no position estimate. Results are development evidence, not
independent validation. See [the report and plots](RESULTS.md) for membership,
frequency effects, omitted mass, visibility, and convergence admission coverage.
