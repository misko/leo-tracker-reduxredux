# DS1 TRAIN full-observation orbit and soft-association runner

`run.py --task task.json` runs one independent TRAIN task.  The minimum task
fields are `task_id`, `group_id`, `session_ids`, `prior`, `method`, and
`output_path`.  `prior` accepts `latitude_deg`/`longitude_deg`/`radius_km` (or
the short `lat`/`lon`/`radius` forms).  `options.cache_root` may bind a
nonstandard cache root.

Supported methods are `causal_per_norad_orbit_rate`,
`global_tau_per_norad_orbit_rate`, `soft_joint_association`, and
`soft_association_global_tau`.  The aliases
`global_time_plus_per_norad_orbit_rate`, `soft_association`, and
`soft_association_plus_global_time` are accepted.  The combined soft global
time and per-NORAD-rate method is explicitly rejected rather than silently
approximated.  All qualified observations in every selected scan are used. The
runner rejects task-level truth and observation-mask fields. It uses causal
cache receipts, performs a fresh geographic search from the declared prior
centre, and seals the output JSON and adjacent SHA-256 file atomically.

The causal-rate arms use exact receipt-bound SGP4 winner replay.  They choose a
hard identity using all observations at each evaluated position and only then
fit shared NORAD rates.  This bounded staged design is recorded in every
artifact; it is not represented as a full exact soft identity/rate marginal.

Geographic screening uses cache predictions and re-associates at every trial.
`options.exact_rate_finalists` bounds the number of final RF-selected basins
that receive expensive exact SGP4 rate fitting. Set
`options.exact_rate_workers` to run those independent fits in forked workers;
use one BLAS thread per worker.
