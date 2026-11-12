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
