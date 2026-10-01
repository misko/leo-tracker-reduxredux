# First fresh one-start comparison

Both DS9-B01-S1 arms pass the independent numerical audit. One start takes 30.93 seconds wall / 29.70 seconds CPU; three starts take 35.57 seconds wall / 34.63 seconds CPU. Both yield exactly the same reported 659.44 m reference error. This is a 4.64-second observed wall-time reduction on one single, not an established corpus-wide speedup.

Both arms freshly acquire using the original implementation. Acquisition proposals match each other and the original baseline; first-fit states, labels and objectives match within the frozen equivalence tolerances. The one-start arm fits exactly one seed. Sources, physical inputs, launch budgets and audit outputs are sealed separately for each arm. The audit checks stationarity before reference scoring.

This validates the first implementation gate only. The pair and quad comparisons are next, in the predeclared orders (3,1) and (1,3). Runtime includes fresh process startup and inference from prepared observations/orbits, but excludes preparation and the separately timed audit. OS caches and host load are uncontrolled; neither arm means a flushed-filesystem-cache benchmark. There is no faster-acquisition change in this comparison.

The [full-panel saved-fit screen](SEED_PREFIX_SCREEN.md) found material position changes from extra starts in some windows, so this identical single endpoint does not justify removing starts globally. All 112 original outcomes and continuation results remain unchanged.

Evidence: [sealed single comparison](cold-seed-limit-v1/DS9-B01-S1/comparison.json), with sources, launches, fitted receipts and evaluations in its `1/` and `3/` directories. [Runner](run_seed_limit.py) differs from the original only in its description, explicit seed-limit argument, recorded limit and loop bound.
