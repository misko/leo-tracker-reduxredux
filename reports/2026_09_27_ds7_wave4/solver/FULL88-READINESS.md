# DS7 exact-baseline full-88 readiness and group8-02 execution spec

This is a reference-free, read-only feasibility review. It uses sealed runtime
receipts, the frozen runner and optimizer source, and candidate-bank sizes. No
score, pose, reference coordinate, or raw IQ artifact was read.

## Decision

The current exact full-88 joint fit is **not credibly runnable** within both the
runner's 1800-second ceiling and the previously declared 4 GiB memory envelope.
This is a resource/readiness conclusion, not a scientific abstention. The
unchanged eight-recording panels remain feasible and have measured substantial
budget margin.

## Measurements

- Frozen group8-01: 486 tracks, 63 total objective/gradient evaluations,
  170.304 seconds.
- Frozen group8-11: 484 tracks, 62 evaluations, 165.016 seconds.
- Prefix-4: 239 tracks, 56 evaluations, 84.932 seconds.
- Prefix-2: 115 tracks, 49 evaluations, 32.983 seconds.
- Loading the first-eight documents through the active adapter retained
  550,825,293 bytes of candidate/observation arrays and reached 620,172 KiB
  maximum RSS. This measurement used CPU1/BLAS1 and did not run optimization.
- The first-eight compressed NPZ banks total 494,855,917 bytes. The later
  group8-11 banks total 512,562,536 bytes.

The memory measurement includes the Python process, NumPy/SciPy, all eight
loaded documents, and their decompressed arrays. It does not include an
optimizer run. The runtime measurements are sealed end-to-end adapter times and
include input loading, three starts, optimization, and the final training RMS
audit.

## Full-88 estimates and limits

The adapter loads every document and retains every candidate position and
velocity array for the entire fit. Linear extrapolation from the measured
first-eight arrays gives about 6.06 GB of retained arrays for 88 recordings;
linear RSS extrapolation gives about 6.82 GB. These are estimates, and actual
track/candidate counts vary, but both exceed 4 GiB before allowing optimizer
workspace or allocator overhead.

At eight recordings, end-to-end cost is 2.66–2.70 seconds per total evaluation.
With approximately eleven times as many tracks, a linear estimate at the same
62–63 evaluations is 1,815–1,873 seconds. That already straddles or exceeds the
hard 1800-second runner maximum. It is optimistic because the parameter vector
grows from ten dimensions to ninety, and the full fit may require more line
search or optimizer evaluations. It is also possible that common overhead and
different tracks reduce the ratio; no full-88 measurement exists, so that
possibility is not evidence of feasibility.

The runner enforces `0 < unit_seconds <= max_seconds <= 1800`. Raising the cap
inside the current runner contract is therefore unavailable. A credible future
full-88 attempt requires an exact, measured execution change that keeps the
objective, gradients, starts, masks, candidates, normalization, bounds, and
optimizer unchanged. At minimum it needs:

1. peak retained memory below the declared envelope, likely by streaming or
   bounded document residency rather than holding all candidate arrays;
2. an end-to-end timing rehearsal or exact evaluation benchmark demonstrating
   margin below 1800 seconds; and
3. equivalence tests against the frozen adapter on 1/2/4/8 inputs before any
   full-88 launch.

Without those gates, launching full88 would most likely produce a timeout or
memory failure and would not add interpretable scientific evidence.

## Exact full-88 input and launch contract

A future immutable input must be a sealed `ds7-inputs/v1` document bound to the
frozen DS7 dataset and the budgets plan. It must account for all 88 captures,
with all 88 rows in `ready` state. Every row must contain exactly:

- one `observations` artifact using `ds7-baseline-track-export/v1`;
- one candidate manifest JSON bound to the observation-byte SHA-256; and
- one candidate NPZ bank with the exact 41-point timing grid.

The eligibility-aware loader must verify unique observation and manifest track
IDs, exact coverage of tracks with at least two training and one held
observation, finite arrays, declared shapes, session/manifest bindings, and
artifact hashes. The arm must remain
`config/ds7/baseline-wave2-ready-v1.json`, invoked directly by a privileged
runner retaining one UID/process group.

If the resource gates above are later passed, the concrete launch is:

```sh
sudo -n nice -n 19 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  /opt/leo-tracker/current-api/.venv/bin/python tools/ds7_eval.py run \
  --plan reports/2026_09_27_ds7_evaluation_setup/plans/budgets/plan.json \
  --inputs FULLY_FROZEN_ALL88_INPUTS.json \
  --arm config/ds7/baseline-wave2-ready-v1.json \
  --output NEW_SEALED_OUTPUT_DIRECTORY \
  --max-seconds 1800 --unit-seconds 1800 --unit full88
```

No `sudo`, timeout, environment, or session wrapper may appear inside the arm's
adapter argv.

## Frozen group8-02 execution specification

The next bounded panel is chronological `single-009` through `single-016` plus
`group8-02`. It uses the unchanged wave-two ready arm and science. Its adapter
lease is 900 seconds total and 300 seconds per unit, with CPU1/BLAS1 and nice
19. Controls remain coordinator-owned and are not part of this solver launch.

Execution is blocked until the coordinator supplies an immutable sealed input
that accounts for all 88 captures, marks exactly the required captures ready,
passes artifact-hash and eligibility-aware load validation, and leaves all
other unavailable rows explicit. Once that handoff is received, the exact
single-run command is:

```sh
sudo -n nice -n 19 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  /opt/leo-tracker/current-api/.venv/bin/python tools/ds7_eval.py run \
  --plan reports/2026_09_27_ds7_evaluation_setup/plans/budgets/plan.json \
  --inputs VALIDATED_GROUP8_02_INPUTS.json \
  --arm config/ds7/baseline-wave2-ready-v1.json \
  --output reports/2026_09_27_ds7_wave4/solver/group8-02-v1 \
  --max-seconds 900 --unit-seconds 300 \
  --unit single-009 --unit single-010 --unit single-011 --unit single-012 \
  --unit single-013 --unit single-014 --unit single-015 --unit single-016 \
  --unit group8-02
```

If inputs arrive progressively, each newly ready single may instead run once in
its own new sealed directory with the same arm and 300-second unit cap. The
completed singles must then be reused; they must not be duplicated when
`group8-02` becomes ready. The cumulative adapter elapsed seconds across those
runs and the joint run must remain at or below 900 seconds.
