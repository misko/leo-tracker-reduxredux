# Frozen-position prediction outside the 24-scan pools

Before target scoring, freeze five scans per DS7/DS8/DS9 from the full-ready
authority, excluding the corresponding 24-scan fitting pool. Sort by capture
start UTC then session ID; select indices floor(j*(N-1)/4), j=0..4. No quality,
posterior, reference error or target score enters selection. Fail on missing
inputs rather than substitute scans.

Compare the configured center, the qualified N24 fitted position, and an equal
mixture of the three qualified balanced N8 positions. Integrate each target's
complete-track q020 likelihood over one common timing offset uniformly on
[-5,+5] seconds. For the N8 mixture, average the three scan densities, not their
log scores. Do not fit location, timing, assignments or weights on targets.

Reuse scalar-audited scan_holdout/timing.py. Require replay error <1e-7 and
16/32-node-per-bank-interval log-integral discrepancy <=0.01. On numerical
failure only, preserve initial values and refine to 64/128 nodes, same gate.
Report all failures, and no aggregate unless all constituent scores qualify.
Bound each target subprocess to 180 seconds and concurrency to three.

Report per-scan and summed predictive log-score differences versus center and
the N8 mixture. Positive differences favor N24. Targets are disjoint from the
current fit, but have been explored previously: this is not a blind holdout.
Banks remain site-conditioned, timing prior is uncalibrated, and the inherited
reference is exposed and unsurveyed. No new RF or production changes.
