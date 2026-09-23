# Independent review: frozen causal phase-rate prior

Reviewed the frozen prior source and result without modifying or rerunning either
one. Scope was `learn_prior.py`, `results/frozen-prior.json`, the referenced
original learner, and the locally saved strict metadata and epoch export. No RF
measurements, position outcomes, reference coordinates, VAL, or TEST inputs were
opened.

## Confirmed numerical and selection semantics

The result hash is
`c301b762e6b47a2f8c75b8510fdaafa31195179415884a3d857c62e4c7f23f16`.
Its learner hash matches the current `learn_prior.py` hash
`f635eff8572a363ff2b40d5f3d101dbbdf1db2616a0d431d889b7397725d9c1e`,
and its original-learner hash matches
`tools/study_causal_orbit_phase_prior.py` at
`bac4742720aca1c8af020d914189db4e6ccd73c812cb0578db4c6d0a5daf45fb`.

The cutoff recomputes exactly to `1789948313177470833` ns: the earliest strict
TRAIN track support start minus the predeclared 505 seconds. All 589 archive
records in the saved result have collection time strictly before that cutoff.
The code additionally excludes every individual element with epoch at or after
the cutoff. It learns only from the 2,689 unique NORAD IDs in the fixed 6,988
track export; the result has the same 2,689 blind candidates and reports history
for every one. This is a candidate-identity population, not an RF or geographic
outcome filter.

The original learner reserves the last eligible transition for each satellite as
its temporal validation pair; all earlier eligible consecutive transition pairs
form training. It selects model class by the specified validation *median
absolute* phase-rate error, then refits that selected class on all pre-cutoff
transitions. The saved candidates confirm ridge features with alpha 0.1 wins
that rule (`0.0320859027 s/h` median absolute error); its separately reported
validation RMS is `0.1602932914 s/h`. Thus the intended semantics are preserved:
median absolute error chooses the model, while RMS is a scale to be used by the
later prior. RMS did not choose the model. The saved accounting is internally
consistent: 159,624 transitions, 154,246 training pairs, and 2,689 validation
pairs.

The saved epoch export binds the same strict metadata hash as the result,
`cf80a6bead25b991993b664b3607b8ebc7e80146bd0c942ab2b2f8cb4b5e8f60`, so the
executed result's two inputs are consistent. The learner contains no reference
position or RF-outcome input and reports both flags false.

## Publication-blocking provenance defect

The result binds only the report wrapper and
`study_causal_orbit_phase_prior.py`. That original module executes numerical
helpers imported from other local sources: in particular
`tools/study_orbit_update_modes.py` supplies `raw_state` and `rms`, and
`src/leo/sky/propagation.py` supplies `parse_element_sets` and
`parse_element_set_records`. The wrapper also executes
`src/leo/operations/tle_archive.py` for archive selection and digest-verified
read. None of these executable local dependencies is bound by the saved result.

Further, `learn_prior.py` reads both the epoch export and strict metadata but
does not assert that the export's recorded strict-metadata hash equals the hash
of the metadata it separately reads. The saved artifacts happen to agree, as
verified above, but a future invocation could combine mismatched inputs without
failing.

This means the current numerical result is internally consistent but is not yet
a sufficient reproducible execution authority for a dependent fit. Before use,
add fail-closed input-binding assertions and bind the executed local dependency
sources (and, if practical, numerical package versions). Then rerun the bounded
prior export to a fresh result, preserving this result as superseded. A post-hoc
hash sidecar would not truthfully change the source hash of the already executed
learner.

## Live amendment source review (`2026-09-23T22:22Z`)

The live amended learner has hash
`24e0af6c25688635ee9b64bd144822b9cef0b77a470b5d07f625528acc2aeb44`.
It correctly preserves the original result as
`results/frozen-prior-superseded-missing-transitive-bindings.json`, asserts the
epoch export's strict-metadata hash, both fixed-parent hashes, and paired
inference hash before learning, and records the original learner,
`study_orbit_update_modes.py`, `propagation.py`, `tle_archive.py`, and
NumPy/SciPy/SGP4 versions. Those changes resolve the prior review's primary
gaps.

One local executed dependency remains: `raw_state` in the bound
`study_orbit_update_modes.py` calls `julian_day_from_utc_ns` from
`src/leo/sky/frames.py`. Add that file to `transitive_sources` and make one
fresh export after the currently running replay ends. The running process must
remain unmodified; its output cannot claim to have bound a source it did not
record. This is source approval pending that final small provenance addition and
its fresh result, not result approval.

## Reassessment: explicit post-run supplement is sufficient

After the replay completed, I checked `src/leo/sky/frames.py` without changing
the learner. Its worktree has no diff; SHA-256
`b6c98c11d25957c8f535d09a4f4cc47f3f82745b63ca57c61f9e8d5949fbb8e0`
equals the current `HEAD` blob exactly. Its most recent committed change is
`65ec1f5a908fb38de561473adce0604661e7edb5` from 2026-08-20, before this
run. The only relevant executed dependency is the deterministic
`julian_day_from_utc_ns` conversion called by already-bound
`study_orbit_update_modes.raw_state`; numerical package versions are recorded
by the amended learner.

Accordingly, no replay is needed solely to add this bookkeeping hash. A separate
post-run supplement may bind the completed result hash, executed learner hash,
already-recorded original/transitive hashes, this file path/SHA/commit evidence,
and the exact runtime statement. It must explicitly say that it was recorded
after execution, changed neither source nor numerical outputs, and is not a
pre-execution source binding. The only residual uncertainty is a hypothetical
unobserved temporary source modification and restoration during execution, which
git cannot disprove; there is no evidence of one. This supersedes the preceding
fresh-replay recommendation for `frames.py` alone.
