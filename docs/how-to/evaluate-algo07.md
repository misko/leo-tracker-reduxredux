# Evaluate algo07 on frozen DS26 inputs

Current candidate commands explicitly use
`--annotation-training-policy lbfgsb-gn-fallback-full5-v1` and
`--inclusion-control-policy native-complete-controls-v1`; the runtime control
section shows their combination. The independent opt-in
`--joint-schedule-policy defer-factorized-unless-retry-v1` adds conditional
joint scheduling and still requires complete-worker qualification.

Run these commands from the repository root. Use the pinned numerical environment.
The paths below describe the existing development host. Choose a fresh output
directory for each command. Outputs on QNAP are rejected.

```bash
ALGO_PYTHON=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
ALGO_SNAPSHOT=/srv/bulk/leo-dev/algo07v3-shortcuts-20261107
ALGO_EVAL=/srv/bulk/leo-dev/algo07-evaluation
export PYTHONPATH="$PWD/src:$PWD/tools:$PWD"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
```

## Build the full-budget algo07v4 backend

For a source checkout, build the existing packaged extensions before binding
the source tree. Installed wheels already contain these extensions.

```bash
"$ALGO_PYTHON" setup.py build_ext --inplace
```

```bash
"$ALGO_PYTHON" -B -m leo.cli.algo07v4 build-native \
  --output "$ALGO_EVAL/native"
```

The build emits `manifest.json`. The worker verifies the source, wrapper,
binary, compiler flags, original solver boundary and single-thread SciPy LP64
provider against this manifest. Compilation happens before inference.

## Check a few scans

```bash
"$ALGO_PYTHON" -B tools/evaluate_algo07.py run \
  --profile quick --version algo07v4 \
  --snapshot "$ALGO_SNAPSHOT" \
  --native-manifest "$ALGO_EVAL/native/manifest.json" \
  --output "$ALGO_EVAL/quick-v4"
```

The default quick cases are DS26-0002, DS26-0066 and DS26-0102. To check only
one scan, add `--cases DS26-0002`. These cases exercise distinct workloads.
Do not treat them as independent qualification scans after tuning on them.

Use `plan` instead of `run` to inspect requests without starting inference.
Add `--repeats 5` for repeated measurements. Each job has a 1,200-second
default deadline; change it explicitly with `--timeout SECONDS`.

## Plan and run the complete frozen inventory

First inspect the complete plan.

```bash
"$ALGO_PYTHON" -B tools/evaluate_algo07.py plan \
  --profile full --version algo07v4 \
  --snapshot "$ALGO_SNAPSHOT" \
  --native-manifest "$ALGO_EVAL/native/manifest.json" \
  --output "$ALGO_EVAL/full-plan-v4"
```

The plan retains all 159 expected members. It identifies 158 available inputs
and the unavailable DS26-0172. Inspect this count before starting the batch.

```bash
"$ALGO_PYTHON" -B tools/evaluate_algo07.py run \
  --profile full --version algo07v4 \
  --snapshot "$ALGO_SNAPSHOT" \
  --native-manifest "$ALGO_EVAL/native/manifest.json" \
  --output "$ALGO_EVAL/full-v4"
```

Jobs execute sequentially. The report records every missing, failed and timed-out
job. A batch with any incomplete member exits nonzero and retains its report.
The known missing input must remain visible in the denominator.

## Compare against frozen algo07v3

Run the same selected cases and repetition count with the original source.

```bash
"$ALGO_PYTHON" -B tools/evaluate_algo07.py run \
  --profile quick --version algo07v3 \
  --snapshot "$ALGO_SNAPSHOT" \
  --source-root "$ALGO_SNAPSHOT/baseline-src" \
  --output "$ALGO_EVAL/quick-v3"

"$ALGO_PYTHON" -B tools/evaluate_algo07.py compare \
  --baseline "$ALGO_EVAL/quick-v3/report.json" \
  --candidate "$ALGO_EVAL/quick-v4/report.json" \
  --output "$ALGO_EVAL/quick-comparison"
```

Use `--profile full` for both sides to compare the complete available inventory.
The comparison excludes incomplete pairs from timing arithmetic and reports
their counts separately. It reports CPU and wall ratios, aggregate time saved,
per-arm GPS error distributions, frequency scores and ownership changes.
GPS distances in these reports use kilometers. Raw saved scientific evidence
and stage events remain available for deeper audit comparisons.

Supply `--references FILE` to use a case-to-GPS-reference JSON map for scoring.
Otherwise the frozen template's evaluation reference applies. Inference requests
always receive `evaluation_reference=null`; scoring happens after committed
results are loaded through the public store interface.

For timing qualification, alternate versions externally rather than run all
baseline repetitions before all candidate repetitions. The CLI runs one version
per invocation. Retain the order, affinity, host load and timing ranges. A quick
single pair is a smoke test, not a repeatability or DS26 population claim.

## Screen provisional algo07v5

Run the v4 commands from the fixed v4 checkout. Run the following commands from
the v5 checkout, with the environment set above. Build a separate manifest for
each checkout because the manifest binds absolute source and wrapper paths.

```bash
"$ALGO_PYTHON" -B -m leo.cli.algo07v5 build-native \
  --output "$ALGO_EVAL/native-v5"

"$ALGO_PYTHON" -B tools/evaluate_algo07.py run \
  --profile quick --version algo07v5 \
  --snapshot "$ALGO_SNAPSHOT" \
  --native-manifest "$ALGO_EVAL/native-v5/manifest.json" \
  --output "$ALGO_EVAL/quick-v5"
```

Inspect the complete plan before starting the full batch.

```bash
"$ALGO_PYTHON" -B tools/evaluate_algo07.py plan \
  --profile full --version algo07v5 \
  --snapshot "$ALGO_SNAPSHOT" \
  --native-manifest "$ALGO_EVAL/native-v5/manifest.json" \
  --output "$ALGO_EVAL/full-plan-v5"

"$ALGO_PYTHON" -B tools/evaluate_algo07.py run \
  --profile full --version algo07v5 \
  --snapshot "$ALGO_SNAPSHOT" \
  --native-manifest "$ALGO_EVAL/native-v5/manifest.json" \
  --output "$ALGO_EVAL/full-v5"
```

Compare matched v4 and v5 reports with the same cases, timeout and repetition
count. Use fresh output directories for every alternating repeat.

```bash
"$ALGO_PYTHON" -B tools/evaluate_algo07.py compare \
  --baseline "$ALGO_EVAL/quick-v4/report.json" \
  --candidate "$ALGO_EVAL/quick-v5/report.json" \
  --output "$ALGO_EVAL/quick-v4-v5-comparison"
```

The provisional v5 policy reuses the winner's complete first-round initial
controls. Its native backend remains the full-budget v4 implementation.
Registration does not establish a worker speedup or DS26 accuracy qualification.
Keep the v4 source and backend fixed. The [investigation goal](../analysis/algo07v4-v5-goal.md)
names the evidence required before selecting a candidate.

## Evaluate the opt-in annotation optimizer

Add the explicit policy to select L-BFGS-B for annotation training only. It keeps
all five phase rounds and the full native precision budget. Every physical
residual evaluation, including finite differences, counts against a 625-call
ceiling. Termination, exhausted budgets and projected-gradient stationarity
remain separate in saved training metadata. Existing requests and commands
without this option retain their GN behavior.

```bash
"$ALGO_PYTHON" -B tools/evaluate_algo07.py run \
  --profile quick --version algo07v5 \
  --annotation-training-policy lbfgsb-full5-625-v1 \
  --snapshot "$ALGO_SNAPSHOT" \
  --native-manifest "$ALGO_EVAL/native-v5/manifest.json" \
  --output "$ALGO_EVAL/quick-v5-lbfgsb"

"$ALGO_PYTHON" -B tools/evaluate_algo07.py plan \
  --profile full --version algo07v5 \
  --annotation-training-policy lbfgsb-full5-625-v1 \
  --snapshot "$ALGO_SNAPSHOT" \
  --native-manifest "$ALGO_EVAL/native-v5/manifest.json" \
  --output "$ALGO_EVAL/full-plan-v5-lbfgsb"

"$ALGO_PYTHON" -B tools/evaluate_algo07.py run \
  --profile full --version algo07v5 \
  --annotation-training-policy lbfgsb-full5-625-v1 \
  --snapshot "$ALGO_SNAPSHOT" \
  --native-manifest "$ALGO_EVAL/native-v5/manifest.json" \
  --output "$ALGO_EVAL/full-v5-lbfgsb"
```

Use the same comparison command with matched fixed-v4 or frozen-v3 reports.
The experimental policy is not a qualified default. A successful component
screen does not establish complete-worker speed or localization accuracy.

The first full-worker attempt with this primary-only policy failed in
DS26-0066 annotation and produced no scientific result. The repaired primary
still reports unsuccessful optimization explicitly. The next experimental
policy is `lbfgsb-gn-fallback-full5-v1`: use that value with the same
`--annotation-training-policy` option after bounded component checks. It reruns
an unsuccessful primary attempt with full original GN48 from the original
phase start. Its worst-case budget is 625 primary plus 625 reference residual
calls, retaining five phase rounds. Receipts count both attempts and preserve
their stops, failures and score corrections. Completed GN fallback is recorded
separately from primary convergence. This policy also requires complete-worker
and independent DS26 qualification before becoming a default.

## Inspect exact inclusion-control reuse

This bounded diagnostic replays predictive recovery from a completed public
result. It keeps both calibration arms, full scientific budgets and geometry
fingerprints. It does not enable a cache in the worker or run a full DS26 batch.
Use a saved request and its own checkout-bound manifest.

```bash
taskset -c 0,1,2 "$ALGO_PYTHON" -B tools/probe_algo07v5_control_census.py \
  --request "$ALGO_EVAL/quick-v5/DS26-0066-r0/algo07v5/request.json" \
  --native-manifest "$ALGO_EVAL/native-v5/manifest.json" \
  --output "$ALGO_EVAL/control-census-0066" --timeout 180 --run

taskset -c 0,1,2 "$ALGO_PYTHON" -B tools/probe_algo07v5_control_census.py \
  --request "$ALGO_EVAL/quick-v5/DS26-0066-r0/algo07v5/request.json" \
  --native-manifest "$ALGO_EVAL/native-v5/manifest.json" \
  --output "$ALGO_EVAL/control-reuse-0066" --timeout 180 --reuse --run
```

The first command independently computes every control pair and checks any
matching keys against complete results. The second explicitly reuses matching
pairs through independent copies. Both must reproduce the entire saved native
recovery audit. Omit `--run` to plan without loading the scientific archive.
Reports separate recomputation, reuse, keying and copy costs. A component result
does not satisfy the complete-worker speed target.

## Evaluate opt-in runtime control reuse

Add `--inclusion-control-policy native-complete-controls-v1` independently of
the annotation optimizer. It reuses complete matching c0/fitted-c control pairs
within one recovery invocation. The key retains geometry and all mutable
scientific state and binds the known native backend. Unknown callbacks and
stateful numerical replay remain ineligible. No search budget is reduced.

```bash
"$ALGO_PYTHON" -B tools/evaluate_algo07.py run \
  --profile quick --version algo07v5 \
  --annotation-training-policy lbfgsb-gn-fallback-full5-v1 \
  --inclusion-control-policy native-complete-controls-v1 \
  --snapshot "$ALGO_SNAPSHOT" \
  --native-manifest "$ALGO_EVAL/native-v5/manifest.json" \
  --output "$ALGO_EVAL/quick-v5-control-reuse"

"$ALGO_PYTHON" -B tools/evaluate_algo07.py plan \
  --profile full --version algo07v5 \
  --annotation-training-policy lbfgsb-gn-fallback-full5-v1 \
  --inclusion-control-policy native-complete-controls-v1 \
  --snapshot "$ALGO_SNAPSHOT" \
  --native-manifest "$ALGO_EVAL/native-v5/manifest.json" \
  --output "$ALGO_EVAL/full-plan-v5-control-reuse"

"$ALGO_PYTHON" -B tools/evaluate_algo07.py run \
  --profile full --version algo07v5 \
  --annotation-training-policy lbfgsb-gn-fallback-full5-v1 \
  --inclusion-control-policy native-complete-controls-v1 \
  --snapshot "$ALGO_SNAPSHOT" \
  --native-manifest "$ALGO_EVAL/native-v5/manifest.json" \
  --output "$ALGO_EVAL/full-v5-control-reuse"
```

The option creates a separately bound schema-3 request. Commands without it keep
their schema-1/2 descriptors, identities and behavior. Provenance records each
cache invocation and its computed, reused, failed and unkeyable pair counts.
Cached fit histories describe the reused result; those histories are not new
physical solver evaluations. Native activation receipts retain actual calls.
Saved resume validates the bound work record without loading a native backend.
Use the usual `compare` command on matched reports; qualification is still required.

## Evaluate conditional joint scheduling

The bounded joint diagnostics accept a completed current v5 request. First
capture a complete predictive recovery with
`tools/probe_algo07v5_joint_start.py --mode capture`, then use its output as
`--reference` for `--mode warm` or
`tools/probe_algo07v5_joint_schedule.py`. All commands require `--request`,
`--native-manifest` and fresh `--output`; inference additionally requires
`--run`, three pinned CPUs and the single-thread environment below.
Capture allows at most 300 seconds; the tested warm and deferred schedules
use `--timeout 180`. Capture must match the entire saved recovery before
its content-bound reference is accepted. The deferred replay must match
every remaining trial and audit and both acceptance/retry decisions.
These diagnostics do not establish complete-worker speed or GPS accuracy.

To evaluate the new runtime schedule, add the joint flag to quick or full
commands while retaining the same annotation and inclusion policies:

```bash
"$ALGO_PYTHON" -B tools/evaluate_algo07.py run \
  --profile quick --version algo07v5 \
  --annotation-training-policy lbfgsb-gn-fallback-full5-v1 \
  --inclusion-control-policy native-complete-controls-v1 \
  --joint-schedule-policy defer-factorized-unless-retry-v1 \
  --snapshot "$ALGO_SNAPSHOT" \
  --native-manifest "$ALGO_EVAL/native-v5/manifest.json" \
  --output "$ALGO_EVAL/quick-v5-joint-schedule"
```

Use `plan --profile full`, then `run --profile full` with these same options
and fresh output paths for full qualification. Schema4 binds this policy
independently of the other two. The schedule retains both full control and
joint fits/audits, and computes factorized fits only when they can affect
numerical retry. Saved work distinguishes computed and omitted experiments;
native receipts retain actual physical calls. Unknown callbacks retain the
original order. A mismatched predictive checkpoint cannot be reused by
numerical recovery. Existing commands keep their original schedule.
