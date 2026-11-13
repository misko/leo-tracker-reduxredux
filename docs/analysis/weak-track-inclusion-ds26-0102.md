# DS26-0102 weak-track inclusion diagnostic

One bounded attempt tested the independently validated 33-point RX2/CH6/T003
track nominated as NORAD 68106 at the saved genuine-previous recovery
checkpoint. The production `shared_family_route` selected `new_family`. The
unchanged primary paired fit and `audit_inclusion` completed, with all four
physical audit rows verified. The proposed target added 33 observations and
lost zero incumbent owners in both c0 and fitted-c arms. Its primary acceptance
gate failed solely because the c0 L-BFGS-B optimizer ended `ABNORMAL:` after
54 evaluations (`success=false`); the fitted-c candidate and both controls
converged. `numerical_only` was true, so the production-conditional Powell retry
began, then hit the 110-second inner deadline before producing a fit. The
120-second outer process-group cap was not exceeded. The attempt ended with
`StageDeadline`, no qualified inclusion and no association change.

| Arm | Stage | Endpoint E,N km | Evaluation error m | -2 ELBO | RMS Hz | Added/lost |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| c0 | baseline / published | 5.681084, -5.508375 | 942.645 | 34503.455576 | 64.746163 | 0/0 |
| c0 | control fit | 5.679940, -5.508640 | 941.838 | 34503.455525 | 64.746119 | 0/0 |
| c0 | proposed, unaccepted | 5.707353, -5.509814 | 954.968 | 34874.185424 | 64.745692 | 33/0 |
| fitted c | baseline / published | 5.709810, -5.533335 | 936.345 | 34497.854384 | 64.803662 | 0/0 |
| fitted c | control fit | 5.709966, -5.533601 | 936.205 | 34497.854398 | 64.803603 | 0/0 |
| fitted c | proposed, unaccepted | 5.752419, -5.536861 | 957.108 | 34868.618431 | 64.803635 | 33/0 |

The unaccepted proposal would increase reference error by 12.323 m for c0 and
20.763 m for fitted c relative to baseline. Actual accepted position-error
change is **zero in both arms** because the published endpoints did not change.
The reference was loaded only after inference, from
`/srv/bulk/leo-dev/algo07v3-shortcuts-20261107/template-request.json`
(latitude 37.849061591561885, longitude -122.48574968092912; SHA-256
`06b14bd3ccc8a38f5320c1ff48073de08288841ab9f2fe64e5484a62329b8300`).
Errors use the published-store Haversine radius of 6,371,008.8 m. The inference
request has `evaluation_reference: null`; no GPS, future TLE or target reference
entered nomination or fitting. The c0 candidate RMS improves by 0.000427 Hz
versus its control; fitted-c worsens by 0.000033 Hz. Full candidate objectives
include the added family and are not matched-observation fit comparisons.

Primary fit used 64.578 s wall / 60.202 s CPU, primary audit 1.860 / 1.848 s,
and incomplete retry 28.021 / 27.039 s. Terminal elapsed time was 110.003 s;
the three recorded stages sum to 89.088 s CPU. Full-process CPU was not captured
and is unavailable. The native backend recorded 1,043 calls, 1,041 cache hits,
two misses, and zero fallbacks. Raw primary fit and audit were persisted before
the retry; terminal `failure.json` and every raw artifact are in
`/srv/bulk/leo-dev/initial-discovery-20261113/weak-track-68106/inclusion-0102-001/`.
That directory's `README.md` gives file hashes and detailed provenance.
The saved independent annotation is in sibling `validation-0102-001/`.

Reproduce the **single attempt's command** from this worktree (a new execution
must use a fresh output directory; this outcome is already terminal):

```sh
timeout --signal=TERM --kill-after=5s 120s taskset -c 20 env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=/home/mouse9911/.cache/initial-discovery-20261113/component-screen/frozen-source/src:/home/mouse9911/gits/leo-algo07v5-investigation-20261112/tools /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python tools/probe_weak_track_inclusion.py --request /home/mouse9911/.cache/algo07v5-speed-20261112/worker-joint-schedule-0102-001/DS26-0102-r0/algo07v5/request.json --native-manifest /home/mouse9911/.cache/initial-discovery-20261113/component-screen/frozen-source/native/manifest.json --source-root /home/mouse9911/.cache/initial-discovery-20261113/component-screen/frozen-source/src --validation /srv/bulk/leo-dev/initial-discovery-20261113/weak-track-68106/validation-0102-001 --output /home/mouse9911/.cache/initial-discovery-20261113/weak-track-68106/inclusion-0102-001 --timeout 110 --run
```

Decision: **stop this weak-track inclusion lever for now**. Independent review
recomputed all six position errors from raw endpoints, verified the reference
and artifact hashes, and checked frequency metrics, owners and acceptance.
The attempt spent 110 seconds without qualification; its unaccepted proposal
worsened reference error in both arms, with negligible and mixed frequency-fit
changes. Merely extending the Powell deadline has insufficient demonstrated
benefit for the current accuracy–speed objective. This single development case
does not disprove weak-track inclusion generally. Reopening it would require a
new predeclared scientific hypothesis and independent holdout evidence; no
further attempt or policy promotion is part of this goal.
