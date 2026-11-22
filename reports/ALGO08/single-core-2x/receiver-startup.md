# Cold ALGO08 Python startup

Lazy package reexports saved **0.58–0.67 CPU seconds before acquisition** in two matched fresh-process replays. The replays verified a 40-visit sealed DS30-0016 prefix, completed the active solver on existing saved detections and rendered all eight figures. Raw authority, ordered probes, both fit arms, scientific position grid and path, and PNG bytes matched in both run orders. [Measurements](receiver-startup-results.json)

## Where the time went

Fresh trace processes used the installed release virtual environment, the actual launcher import paths and `-X importtime`. They had zero filesystem input blocks. New Python state on these runs therefore measures interpreter startup and import execution with available file pages.

| Fresh process | CPU | Elapsed | Max RSS |
| --- | ---: | ---: | ---: |
| Released `tools.algo08_scan` import | 1.88 s | 1.94 s | 233 MiB |
| Candidate launcher module import | 1.89 s | 1.95 s | 231 MiB |
| Candidate module with lazy reexports | 0.92 s | 0.94 s | 167 MiB |

In the ordinary candidate trace, importing the read-only archive pulled in 408 ms of the operations package, including 254 ms of catalogue initialization through the operations service. The research package cost 427 ms through the Standard analyzer registry. The contracts, storage and scanner package initializers cost 189, 143 and 113 ms respectively in that trace. Those cumulative entries overlap where one package imports another. The detector qualification module and newly reached dependencies took another 60 ms in this import order. It imports historical build, roster and comparison helpers alongside the active binding. The prototype keeps that detector binding and its current import closure.

The experimental launcher recognizes seven package initializers consisting of absolute reexports, a docstring and a literal `__all__`. It resolves a requested export from its original submodule and caches that object. The import hook only applies to the allowed facades and falls through to the stock loader when package setup contains other statements. The implementation is isolated to a fresh experimental Python process. [Lazy reexport loader](/tmp/leo-algo08v2-2x/tools/pipeline_eval/variants/experimental/lean_startup.py)

On both lazy runs, SQLAlchemy, the catalogue package, operations retention and service, the Standard and Research analyzer registries, and persistent-hop scanner and storage modules stayed absent through rendering. The TLE reader and phase-history preparation did execute through their actual modules. The successful solver and renderer also retain NumPy, SGP4, SciPy linalg and optimize, and Matplotlib Figure and Agg. SciPy stats still loads through the localization application dependencies. These retained costs are outside the measured reexport savings.

## Matched bounded replay

The normal experimental setup selected the frozen packed detector, compressed input, track-moment solver and shared-pixel renderer. The harness changed only the analysis entry point to cap raw acquisition at 40 scheduled visits, then used the existing complete detection artifact for the same physical recording. It ran the normal solver and rendered its eight figures in memory. Grid comparison uses the same timing-field exclusion as the publication comparator.

| First arm | Import and setup CPU, ordinary → lazy | Whole bounded replay CPU, ordinary → lazy | Whole bounded replay elapsed, ordinary → lazy |
| --- | ---: | ---: | ---: |
| Lazy | 1.376 → 0.800 s | 8.230 → 7.493 s | 8.361 → 7.625 s |
| Ordinary | 1.452 → 0.778 s | 8.444 → 7.477 s | 8.638 → 7.623 s |

The fixed saving explains part of the interval from process launch to detections. The full publication also includes inventory, native acquisition and sealing. The separate acquisition profile measures CPU, so subtracting it from elapsed launch-to-detections does not isolate import time. This experiment covers one completed physical replay and the seven reviewed facade initializers.

## Reproduce

From the research checkout, use the exact release venv and pinned host settings. The archive must be readable by the normal service account. The replay uses the saved candidate detection artifact and reads only the first 40 scheduled visits from the physical I/Q recording.

```bash
algo08_repo=/tmp/leo-algo08v2-2x
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
algo08_env="$algo08_repo:$algo08_release/src:$algo08_release"
algo08_module=tools.pipeline_eval.qualification.experimental_publication

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 timeout 80s "$@"
}

algo08_lock env PYTHONPATH="$algo08_env" "$algo08_release/venv/bin/python" \
  -BPs -X importtime -c "import $algo08_module"
algo08_lock env PYTHONPATH="$algo08_env" "$algo08_release/venv/bin/python" \
  -BPs -X importtime -c "from tools.pipeline_eval.variants.experimental.lean_startup import install; install(); import $algo08_module"

algo08_replay() {
  algo08_lock sudo -n -u leo -- env PYTHONPATH="$algo08_env" \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 "$algo08_release/venv/bin/python" \
    -BPs "$algo08_repo/reports/ALGO08/single-core-2x/startup_trial.py" "$1" \
    "$algo08_work/integration-tables/pairs/DS30-0016/pair.json" \
    "$algo08_work/integration-moments-v2/spec.json"
}

algo08_replay lazy
algo08_replay stock
algo08_replay stock
algo08_replay lazy
algo08_lock env PYTHONPATH=src:. /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python \
  -m pytest -q tests/pipeline_eval/test_lean_startup.py
```

Six component tests passed. The isolated launcher can also invoke the ordinary experimental command via `python -BPs -m tools.pipeline_eval.variants.experimental.lean_startup` under the same release environment.
