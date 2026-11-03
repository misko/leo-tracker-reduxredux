# DS10 joint-mode residual diagnosis

This is a read-only, post hoc comparison of the two sealed DS10-F001 joint-v2
modes. Reference errors identify fit 0 as the 1.688 km mode and fit 1 as the
25.622 km mode; the reference was not used to refit either state or choose any
parameter. The analysis evaluates every track once at each saved state with the
same extended orbit bank, height surface, priors, and Gaussian covariance used
by the fit.

The Gaussian objective prefers the geographically worse fit 1 by 160.25 units
(2731.87 versus 2892.12). Recomputed maximum-branch log scores explain 160.01
of that difference; the small remainder is the shared-nuisance prior penalty.
Neither mode assigns any of the 44 tracks to background. Thus the preference is
not caused by a different count of null assignments.

| Diagnostic | fit 0, 1.688 km error | fit 1, 25.622 km error |
|---|---:|---:|
| Sum of per-track Gaussian max log scores | -2666.77 | -2506.76 |
| Background assignments | 0 / 44 | 0 / 44 |
| Median whitened residual norm | 2.08 | 2.30 |
| 90th percentile whitened residual norm | 7.27 | 5.62 |
| Tracks above 5 | 11 | 7 |
| Tracks above 8 | 4 | 1 |
| Exploratory Student-t(4) max-score sum | -2341.08 | -2313.35 |

The preference is concentrated. Three tracks contribute +131.23 of the
+160.01 Gaussian log-score advantage for fit 1. Their opaque track IDs begin
`3f2977`, `316edf`, and `31c7a7`; their whitened residual norms fall from
10.16, 9.37, and 8.76 at fit 0 to 1.37, 1.57, and 1.01 at fit 1. The seven
largest pro-fit-1 contributions total +226.44, while the three strongest
countervailing tracks total -63.67. Associations also switch between NORAD IDs
for most of these influential tracks. This supports the proposed mechanism:
hard association plus a Gaussian tail lets a small set of poorly explained
tracks dominate the choice between local modes.

As an exploratory diagnostic, I replaced only the Gaussian density calculation
with a normalized multivariate Student-t density with four degrees of freedom,
using the same covariance matrices and branch priors. This is a rescore of the
two fixed modes, not a robust refit. It reduces fit 1's advantage from 160.01 to
27.72 log-score units, but it does not reverse the ranking. The top three
pro-fit-1 tracks contribute +45.84 under this rescore. A heavy-tailed likelihood
therefore addresses much of the concentration, while these two fixed-state
scores do not establish that robust refitting will recover the better location.

The background model remains unused even for residual norms near 18–19. Its
smooth slope/curvature covariance is therefore not acting as a general outlier
branch. Robust signal residuals, an explicit broad contamination component, or
track-level downweighting are distinct model choices and require frozen
simulation checks before any location evaluation.

Machine-readable per-track values are in
`development/residual-diagnosis-data.json`. The sealed input receipt SHA-256 is
`b58a6b58bef620b96ad70c8250831a407c2511bf429afcf4ab4a745ff35883ac`;
the diagnostic data SHA-256 is
`c480986c2c0d31aeb58ee212ec0de3c9172e2884209dfe7131e8e51de384ba84`.
The evaluated acquisition source is preserved in `development/source-joint-v2`
with `11-acquire.py` SHA-256
`4027f13fb5aefa0f681ac3003acd40178c92ae676c987cabfb1665f7addf1a6f`.
