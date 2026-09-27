# Fixed early/middle/late proposal diagnostic

Use every inactive receiver from the completed 64-visit local-tracking
development replay, including reference-negative receivers. Do not select only
known misses. Freeze this target list and seed windows 0,5,10 before IQ reads.
Each window uses the existing ten-candidate Python acquisition and raw Python
margin gate, then native tone-conditioned confirmation and three-integer raw
early-symbol scoring. Confirm at seed+2, except late seed10 confirms at8.
Require positive evidence, nonoverlapping windows, transported timing within
2us and physical frequency within8kHz. Keep all thresholds unchanged.

Search each fixed seed independently and stop at its first accepted candidate;
do not cherry-pick a later candidate using the reference. Reference inventory
is used only after search to assess the pair. Count time for input conversion,
acquisition, Python scoring, tone fit and local raw confirmation. No cached
reference output enters search. This is a proposal diagnostic, not a deployable
detector: targets come from saved candidate decisions and primary cost is absent.
Costs for hypothetical one/two-window schedules are planning evidence only.

CPU0, numerical threads=1,120-second total bound, row checkpointing outside
timing, immutable inputs and source rehash. No holdout IQ. Any integrated variant
must first pass controls including pure tones and swapped receivers, then causal
development replay and fresh final validation. Do not claim a search ceiling
from sparse window opportunity counts or assume first-positive selection is safe.
