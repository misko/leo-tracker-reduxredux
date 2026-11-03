# Conditional receiver geometry screening

Freeze this screen before fitting. Use donor 0 training visits for calibration;
report its held visits and donor 1 training/held visits separately. Labels and
positions are conditional Doppler hypotheses as documented in the donor protocol.
No DS11 position errors enter this screen.

Condition on at least one source-specific receiver hit. This screen tests which
receiver detects a nominated source; it does not estimate physical absence,
clutter, source lifetime, or absolute discovery probability. Exclude unknown
bits. A normalized three-state likelihood has log weights eta0, eta1, eta0+eta1
for RX0-only, RX1-only, both, respectively. There are eight receiver/RF offsets.
Compare receiver-only offsets, unsigned elevation, and signed nominal 10-degree
outward boresights. The latter two have one additional nonnegative slope.
Offsets have zero-mean Gaussian scale 5 regularization; slope scale 10, bounded
0..40. Offsets bounded -20..20. Optimize analytically differentiated likelihood
from zero offsets and slope 0, 5; select training objective only. No fitted
shared-strength or background parameter is identifiable from this conditional
screen; do not claim one.

Report transfer log score per detected opportunity and per source. A signed
geometry screen passes only if it beats receiver-only and elevation on donor 1
held visits, beats frozen swapped receiver directions and a seeded geometry
permutation, and improves more than half the supported validation sources over
receiver-only. Require successful optimizer convergence and gradient checks.
This is a development gate, not statistical significance or position validation.
If it fails, retain the controls and do not force signed geometry into the DS11
position objective. Any follow-up model requires a separately frozen protocol.
