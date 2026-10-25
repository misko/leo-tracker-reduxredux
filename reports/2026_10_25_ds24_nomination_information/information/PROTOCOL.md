# Count versus conditional local information

The panel is the first four chronological usable DS24 development cases,
0010–0013. They and their geographic outcomes have been exposed previously.
The frozen inventory keeps every original curved graph row and every excluded
row. The common comparison pool has 7/6/5/8 complete owners, 26 total, with the
canonical reference-node causal candidate and alias. No source overlaps the
complete accepted-ID union of either parent arm, including postfit extensions.
No new nominee, source trimming, identity qualification or position fit occurs.

This is a **local Gaussian mean-design information diagnostic**, conditional on
archived identity, fixed RF endpoint, phase references, fitted Gamma precisions,
physical-mode linearization and fixed covariance. It does not compute nonlinear
phase-mixture Fisher information, covariance-derivative information, calibrated
position uncertainty, a clutter/identity score or an operational selection rule.
The previously demonstrated first-order phase limitations remain applicable.

For old curved plus *all* old predictive data, stack position Jacobian J,
shared nuisance design U, noise precision W and nuisance prior precision P.
Keep curved powers/precisions; old predictive noise is sqrt(2) times original
per-ID nominal sigma, with independent 300 Hz source constants. The local
baseline I0 is the stable augmented-prior orthogonal projection of J off U.
Let G=P+U'WU and A=U'WJ. For one complete proposed owner with mean design Jt,
shared nuisance design H, diagonal noise R and independent prior design B:

```
D = Jt - H G^-1 A
S = R + H G^-1 H' + B B'
Delta I = D' S^-1 D
I1 = I0 + Delta I
```

This equals one joint old/new nuisance elimination. It conditions jointly on
the existing predictive evidence rather than adding independent old and new
scores. New noise uses sqrt(2) times the original per-ID nominal sigma: the
unseen Gamma(2,2) inverse-moment factor is explicit and is never learned from
the candidate. A new whole-owner 300 Hz source constant is always included.

An incumbent family shares the original parent phase and physical-mode columns.
If those full physical modes are absent, the candidate is blocked rather than
silently assigning zero shape uncertainty. An inactive family receives separate
causal-width Gaussian phase and full three-mode physical uncertainty. Its
dormant parent phase/mode slots are zero in the target design, avoiding prior
duplication. This uses the existing unit-marginal-variance Gaussian phase-width
approximation, not exact Student/nonlinear integration. Repeated family sources
are alternative one-source additions, never independent geometry claims.

Jacobians use central steps .02 km and .01 km, requiring relative difference
<=1e-5. Prior/covariance factors and 2x2 position information must be finite and
positive definite. Candidate visibility must be nonnegative at the fixed local
reference. Changing only a candidate's CFO values must leave its design and
information exactly unchanged; this is checked on every scored context. The
archived identity and source pool were nevertheless RF/label selected earlier.

Each c arm retains its own fixed baseline weak eigenvector. The score is the
fractional decrease in variance along that *unchanged* direction after inversion
of I1. The paired score is the minimum of the two arm scores. Sort decreasing
score, then points, duration and component. Count ranking sorts decreasing
points, duration and component; duration ranking reverses those first two keys.
Both see the identical 26-owner pool. Every failure remains explicit; a blocked
owner receives no information rank and cannot be silently replaced in a later
top-one comparison. No score threshold is tuned and no accuracy gain is claimed.

The numerical cap is 600 s cumulative inventory/tests/ranking, excluding review
wait, at most 120 s per case, one worker and one BLAS/OMP/MKL thread. No retries,
alternative phase refreshes or expanded labels rescue an unfavorable result.
The independent preflight binds exact source, inventory and protocol bytes
before ranks are computed. Saved arrays include old sufficient statistics and
designs, each target's covariance/design and 2x2 information for independent
joint-Schur/dense audits. No GPS or position error is read by this branch.
