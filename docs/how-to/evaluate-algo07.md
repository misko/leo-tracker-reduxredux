# Evaluate algo07 on frozen DS26 inputs

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

Algo07v5 is not registered yet. Add its versioned runtime and evaluator registry
entry before using it as a candidate. Keep the algo07v4 backend and source
bindings fixed. The [proposed goal](../analysis/algo07v4-v5-goal.md) names the
accuracy and speed evidence required from the next investigation.
