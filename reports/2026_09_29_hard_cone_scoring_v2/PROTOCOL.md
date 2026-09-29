# Fixed-position hard and soft receiver cones: corrected execution

This version preserves the original scientific plan exactly. The first version
aborted before loading data because its entry point imported another report's
study module. That failure and all original frozen sources remain in
../2026_09_29_hard_cone_scoring/. Load local study before dependency bootstrap;
require a tenth, fresh-process entry-point test as well as the nine model tests.
The successful ten-test receipt is test-v2-receipt.json and tests-v2.log.

Compare hard40, soft40, hard50 and soft50 with the no-cone q=0.20 trend model
on all eighteen fixed consecutive DS7/DS8/DS9 panels. Keep each panel's
published no-cone training-selected location and one timing per scan exactly
unchanged. No optimizer, beamwidth selection, new association labels or
geographic accuracy result is produced. This is the scoring diagnostic
proposed before the two-track inspection; the two tracks are not the test set.

Use nominal RX0 west/RX1 east axes, each 10 degrees from zenith. Widths are
half-angles. World orientation and cable mapping remain uncalibrated. For
hard gates g_k is one if every training angle is <=width, otherwise zero.
Soft gates use the published 2-degree sigmoid edge, with no floor. In both
cases satellite mass is (1-q)g_k/K and background mass is
q+(1-q)(1-mean(g)). K is the retained training-horizon-visible candidate count.
Require K>0; preserve explicit abstention otherwise. All-excluded hard tracks
have only the unassociated trend explanation, not a satellite explanation.

Reuse the tested Student-t4 frequency-contrast signal and marginalized linear
trend background, noise scale 100 Hz and slope scale 2000 Hz/s. Full/training
density ratios use the same training-only geometry weights. Held geometry is
a separate diagnostic and must not modify training or frequency-predictive
weights. Thus even a hard training gate is not a reception/non-reception
likelihood or a claim of hard consistency at all held observations.

Before dataset execution, nine synthetic tests must pass: whole-track and
inclusive-boundary gating; all-inside equivalence including q=0/1; all-outside
background invariance; held-geometry isolation; held-frequency isolation;
conditional held density integrates to one; empty horizon bank abstention;
disabled smooth-gradient interface; and real-geometry agreement with direct
dot-product thresholds at all four widths. Initial new-test mock dimensions
were corrected without changing the published fixture. A subsequent import
ordering failure is preserved in the original directory's tests.log; its corrected
nine-test run is tests-fixed-imports.log. No dataset scores were evaluated during
those fixes or the original dataset launch, which failed before data loading.

Freeze all sources, plans, baseline selections, baseline held results and bank
artifacts before launch. For each panel replay no-cone training/held scores,
signal responsibilities and candidate weights against the published q020 rows
within 1e-7, preserving exact observation IDs/counts. Require each mixture's
satellite/background responsibilities to sum to one within 1e-10. Independently
check zero hard-gate weight for every outside or invisible candidate, and
background responsibility one for unsupported hard-gated tracks. Preserve all
per-track outcomes and both training and held support masses.

Report all eighteen panels, hard-minus-soft and each-arm-minus-no-cone held
scores, unsupported tracks/scans, background responsibility, reassociation,
and held geometric support. Aggregate unique-track counts from the nine
nonoverlapping eight-scan sets (72 scans, 4,328 tracks); do not double-count
nested four-scan sets. Counts across panels are dependent. Inspect the two
previously excluded RX0 tracks explicitly, but do not select rules from them.
Count dominant-candidate changes only among tracks with signal responsibility
above 0.5 in both the scored arm and the no-cone baseline; retain that denominator.

One sequential worker, BLAS1/nice19, 4 GiB address-space cap, 90 seconds per
child, at least 5 GiB available RAM before each admission. Verify execution
sources and a child's own inputs before and after that child; verify the full
seal before first execution and at reporting. Preserve failures and do not
retry completed jobs. No RF collection, raw IQ, new propagation, provider
fetches, archive reads or production changes in this scoring experiment.
