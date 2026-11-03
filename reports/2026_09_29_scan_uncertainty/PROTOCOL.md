# Local uncertainty sensitivity to scan and time-window disagreement

Use all 72 existing N24 source scans and their audited profiled training score
gradients/observed negative Hessians. No new fit or reference selection.
For each dataset sum the profiled Hessians to H. Compare inverse(H) with
H^-1 [K/(K-1) sum (g_k-mean(g)) (g_k-mean(g))'] H^-1, using K=24 scan groups
and K=3 pre-existing early/middle/late window groups. For window groups sum
scan gradients within each window before centering. The correction K/(K-1)
is explicitly a finite-group covariance correction, not a claim of calibrated
degrees of freedom for this fitted mixture.

Report covariance eigenvalues, axis scales in metres and generalized variance
inflation relative to inverse(H). These are local sensitivity proxies, not
validated confidence intervals or physical error estimates. Three windows
are too few for stable population covariance inference. Do not infer required
sample count by extrapolating an unverified independence assumption.

Verify source seals, positive pooled H and covariance eigenvalues. Test mean
model variance recovery and invariance to duplication within fixed clusters.
No RF, production edits, target-score use or publication.
