# Adaptive spatial-map development

This prototype represents the intended Sacramento-centered 250 km uniform disk
with exact-area polar cells. Deterministic quadrature evaluates each cell. Every
track explicitly sums all geometrically admitted satellite branches plus the
background branch. Refinement requires both posterior mass and within-cell
spatial likelihood variation; it does not retain only winning points or discard
coarse sibling mass.

The state keeps the original area-by-nuisance prior and the complete factor
history. Refined children therefore recompute the original prior times the
product of all track likelihoods at their new quadrature nodes. This remains a
piecewise-quadrature approximation rather than an exact continuous posterior.
The factor history also preserves one global nuisance hypothesis across tracks.

Both real pilots are explicitly conditional diagnostics: height, receiver
drifts, and satellite epoch offsets are fixed at zero. The fixed-zero pilot also
sets the global clock offset to zero. These are not matched replacements for the
Gaussian-sum posterior. A declared three-point global clock bank is available,
but was not run after the spatial convergence gate failed.

The vectorized RF port was compared with the frozen physics implementation at
five deterministic disk points across three DS9-F001 tracks. Satellite and
background support agreed, and the maximum absolute log-likelihood difference
was 4.075e-10 against a 1e-6 tolerance.

The initial 128-cell, first-eight-track pilot took 32.30 seconds and was sealed
as a development artifact. It saturated after the first track; later
order-2/order-3 evidence differences reached 14.177, so it is unresolved. That
receipt predates the full-history and audit corrections and must not be treated
as a Bayesian posterior. Its embedded hashes preserve provenance, but exact
source snapshots were not captured before those corrections; this is an
explicit reproducibility limitation.

The corrected 512-cell pilot took 34.40 seconds for eight tracks and also
saturated after the first track. Same-leaf-partition order-2/order-3 conditional
log-evidence differences were 0.082, 0.202, 0.324, 0.698, 0.124, 0.448, 0.344,
and 0.253. Track 4 exceeds the frozen 0.5 tolerance, and the saturated leaves
retain large spatial likelihood variation. Its status is therefore
`spatial_convergence_unresolved`, even though all eight tracks were processed.
This audit compares the conditional evidence increment for each update. It is
not a bound or check on the full-history cumulative evidence, posterior mass, or
posterior discrepancy. A future convergence protocol must directly compare
total evidence and spatial posterior mass across resolutions.
The quadrature audit compares conditional evidence increments, not the full
cumulative evidence or posterior discrepancy. Passing that audit alone would
not establish posterior convergence; subsequent work must check those quantities
and account for spatial mass between quadrature nodes.

No 64-scan adaptive-map expansion is justified. A subsequent prototype needs
either a larger bounded representation with demonstrated convergence or a
mass-preserving coarsen-and-refine scheme. It must pass the spatial and
quadrature gates before reference-coordinate scoring.

Figures generated from the seal-verified corrected receipt:

- [`corrected512-conditional-spatial-mass.png`](corrected512-conditional-spatial-mass.png)
  shows area-normalized cell mass without a reference-location marker.
- [`corrected512-convergence.png`](corrected512-convergence.png) shows the
  same-leaf quadrature audit, cell saturation, and within-cell variation.

Regenerate both with `.venv/bin/python
reports/2026_09_30_broad_prior_acquisition/spatial/plots.py`.

`attempts.json` accounts for both review-interrupted max512 attempts and the
sealed corrected pilot. Receipts and states live on the SSD-backed cache under
`~/.cache/leo/research/broad_prior_acquisition/spatial/`.
