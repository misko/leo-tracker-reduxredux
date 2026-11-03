# Broad-prior likelihood diagnostics

This diagnostic evaluates the frozen 64-scan observation bundles and orbit banks with the
hash-bound legacy physics callback. It does not run localization, change priors, or use the
recorded roof coordinate in blind inference. The roof and roof-plus-1-km evaluations are
explicitly labeled reference-location diagnostics.

The development panel is the first eight chronological DS9 selections, capped at eight
retained tracks per scan (64 tracks total). All factors have seven contrasted observations.
Track spans range from 11.53 to 61.10 seconds. The orbit interpolation support margin ranges
from 5.12 to 77.10 seconds and is recorded per track so a later model can reject marginal
support explicitly.

At the Sacramento blind center, 55 of 64 tracks assign background probability at most 0.01
and 9 assign at least 0.99; none lie between. At the recorded roof, 63 are at most 0.01 and
one is at least 0.99. Conditional on a signal, the median effective candidate count is exactly
one at both locations despite roughly 500–640 visible candidates. This is a sharply saturated
likelihood on this development panel and motivates an explicit calibration test. It does not
by itself prove miscalibration: catalogue mismatch, track identity, or representation error
can produce the same pattern.

The configured background model uses a 100 Hz/s slope prior and 5 Hz/s² curvature prior.
Across this panel, adding those terms increases the covariance log determinant relative to
the signal model by 4.36–13.02 nats, while the observed background log likelihood per
dimension ranges from -156.19 to -44.16. Candidate plus background prior mass nevertheless
normalizes to one within 2.23e-16. The prior accounting is sound; the likelihood and its
support still require independent calibration before choosing a model change.

Changing only the diagnostic height from 0 to 1 km changes visible counts by at most a few
candidates and leaves the same 63/1 saturated split at the roof. That is evidence against
height support being the main cause on this panel. The roughly 119 km roof-to-Sacramento
offset materially changes eight background decisions, but that reference result must not be
used to select or tune the blind location prior.

The synthetic identity result is only a same-callback wiring check: the chosen candidate's
own predicted mean is scored by the same callback and ranks first. It is not independent
forward-model validation and makes no recovery claim.

Recommended next tests are to calibrate background slope and curvature scales from held-out,
location-independent residual summaries, measure signal coverage with independent synthetic
and known-identity cases, and make the orbit support margin an explicit eligibility rule.
Tempering or flooring is only a proposal until those tests show undercoverage. A robust
background proposal is a heavy-tailed Student-t over the same slope/curvature-marginalized
contrasts, with degrees of freedom and scale frozen from location-blind held-out residuals.
It must be compared with the Gaussian background on the same 64 scans before adoption.

Artifacts:

- `ds9-first8-max8tracks.json`: per-track priors, likelihoods, support, and state diagnostics.
- `ds9-first8-max8tracks.png`: background probability at Sacramento and the roof reference.
- `summary.json`: concise aggregate metrics bound to the detailed JSON SHA-256.
- `synthetic.py` and `synthetic-results.json`: independent closed-form forward oracle.
- `diagnostics.py`: reproducible diagnostic and plot generator.
