# Fresh profile for prepared rejection thresholds

The scorer is rebuilt with the threshold change described in
`../prepared-threshold-v1/`. Training uses only the four previously designated
training sites and one worker. The 16 evaluation sites remain disjoint.
The build recipe verifies source hashes and immutable/vector/128-MiB modes;
GCC profile-use completes without profile warnings or suppressed mismatches.

Physical ARM control/new/new/control CPU means are **10.5776765 versus
10.400582 seconds**, a **1.674%** saving. Every held-out output byte matches the
frozen reference. Location, interpolation-stencil, session and immutable-orbit
tests pass on ARM. This is an isolated short benchmark; full positioning and
original-cadence qualification are separate gates.

The initial training invocation referenced a missing remote TSV and exited 2.
That profile is excluded. After staging and hash-checking the intended training
TSV, successful training used a fresh `qualified-profiles` directory. Both
protocols and the failure explanation are retained. The final `score.gcda`
comes only from successful training.

Rebuild commands, using fresh absolute output directories:

```sh
TMPDIR=/var/tmp bash tests/native_adaptive/location/research/build_arm_score_pgo.sh \
  generate /var/tmp/leo-modular-location-arm /var/tmp/leo-threshold-pgo-v1 immutable vector 128
# Execute training-protocol.json on ARM; retrieve qualified-profiles/score.gcda
# into the same local output directory, then:
TMPDIR=/var/tmp bash tests/native_adaptive/location/research/build_arm_score_pgo.sh \
  use /var/tmp/leo-modular-location-arm /var/tmp/leo-threshold-pgo-v1 immutable vector 128
```

`source/`, build logs, mode files, profile, executable payload hashes, artifacts,
per-run outputs and timings preserve the experiment. The full ARM position
trial is in `../prepared-threshold-full-v1/`.
