# Single-scan free-height feasibility pilot

Scans 0 and 16; full original independent candidate mixtures and per-track CFO
profiles. Add ellipsoidal receiver height to E/N/timing. No altitude prior,
shared height across scans, newer orbit data or geographic reference. Bounds
E/N +/-12km, timing +/-5s, height +/-1km are deliberately broad diagnostic
bounds, not a site-altitude claim. Two starts per scan: original IID endpoint
with height zero, and (0,0,0,0). Four processes, 90s each, <=3 single-thread
workers, no retries. Preserve original L-BFGS-B settings. Require successful
finite interior solution, gradient <=0.01, finite-difference discrepancy <=0.02;
height must remain at least 1m inside bounds. Replay zero-height training score
against original IID before fits.

Select only by qualified training score, seal all attempts, then compare held
prediction with original zero-height endpoint. Both scans must yield qualified
outputs and positive held gain to consider geographic evaluation. No reference
errors are computed in this pilot. Report selected heights, disagreement across
starts/scans and every failure. An estimated height may absorb model error;
held improvement would not authenticate height or prove location improvement.
