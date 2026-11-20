# Fresh synthetic supplied-tile acceptance

Use the corrected cold-scene generator unchanged, with fresh secret seeds.
It generates four 300 s sites, each with native GLRT peaks and a causal
Starlink catalogue, plus a lane-shuffled control. Freeze the new receiver
programs and this protocol before generation. Keep the development seed
and all truth out of the synthetic cue packets.

For each planted acquisition, independently draw a bearing and an
8–10 km radius for a single correct 25 km square. Draw a second bearing
and a 45–115 km radius for a matched omitted square of the same size.
The four pairs share exactly their native observation and catalogue
bytes, clock, and search budgets. Shuffle query order and IDs. The
shuffled acquisition receives the first planted site's correct tile
and has no geographic reference. Only the native packet and its one
offered tile reach the receiver sandbox. Score one published fix per
method, query and calibration arm, and keep diagnostic forced positions
separate from publications.

The primary experiment is supplied-tile inference in both calibration
arms. Report every attempt, the tile-center error, per-case position
errors, frequency-fit diagnostics separately, false publications when
truth is omitted, and the shuffle decision. Bound each worker at
120 s, using one numerical thread on CPUs 17–19. Seal all predictions
before reading evaluation coordinates, emitter labels or seeds.
