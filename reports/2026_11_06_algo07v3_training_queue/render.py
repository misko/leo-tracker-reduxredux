"""Publish measured queue occupancy and complete native stage clocks."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def main(root, native):
    out = Path(__file__).resolve().parent
    result = read(root / 'result.json')
    for name, digest in result['plan']['bindings'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    before, observed = result['trials']
    assert before['actual'] == observed['actual']
    assert all(r['exact'] and r['saved_vote_exact'] for r in result['trials'])
    assert not result['runtime_modified'] and not result['production_modified']
    training, scoring = observed['blocks']
    assert training['kind'] == 'training' and len(training['tasks']) == 6
    assert scoring['kind'] == 'scoring' and len(scoring['tasks']) == 3
    tests = Path('/srv/bulk/leo-dev/algo07v3-training-queue-final-tests-20261106.xml')
    suites = list(ET.parse(tests).getroot().iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in suites) == 9
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('failures', 'errors', 'skipped'))
    runs = []
    for label, directory in [('before', native / 'v3-run'),
                             ('after', native / 'after-reference/cli')]:
        clock = read(directory / 'attempt/supervisor.json')
        assert clock['returncode'] == 0 and not clock['worker']['resumed']
        lines = (directory / 'attempt/worker.log').read_text().splitlines()
        rows = [json.loads(line) for line in lines
                if line.startswith('{')]
        stages = {r['stage']: r['seconds'] for r in rows if r.get('event') == 'stage'}
        stages['evidence_save'] = clock['worker']['evidence_save_seconds']
        stages['publication'] = clock['worker']['publication_seconds']
        stages['other_process_time'] = clock['process_seconds'] - sum(stages.values())
        assert stages['other_process_time'] >= 0
        runs.append(dict(label=label, seconds=clock['process_seconds'], stages=stages))
        (out / f'{label}-worker.log').write_bytes((directory / 'attempt/worker.log').read_bytes())
        (out / f'{label}-supervisor.json').write_bytes(
            (directory / 'attempt/supervisor.json').read_bytes())
    for name in ('result.json', 'plan.json'):
        (out / name).write_bytes((root / name).read_bytes())
    (out / 'tests.xml').write_bytes(tests.read_bytes())
    (out / 'stages.json').write_text(json.dumps(runs, indent=2) + '\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    ordered = sorted(runs[1]['stages'],
                     key=lambda n: max(r['stages'][n] for r in runs), reverse=True)
    names = ordered[:14]
    for i, run in enumerate(runs):
        bars = axes[0].barh([n + i * .38 for n in range(len(names))],
                            [run['stages'][n] for n in names], height=.36,
                            label=f"V3 {run['label']}: {run['seconds']:.1f} s")
        axes[0].bar_label(bars, fmt='%.1f', padding=2, fontsize=8)
    axes[0].set(yticks=[i + .19 for i in range(len(names))], yticklabels=names,
                xlabel='Elapsed seconds', title='DS26-0002: largest complete-run stages',
                xlim=(0, 50))
    axes[0].invert_yaxis()
    axes[0].legend(fontsize=8)
    for i, task in enumerate(training['tasks']):
        duration = task['end'] - task['start']
        axes[1].barh(i, duration, left=task['start'] - training['start'],
                     color='#c16c2d' if task['item'][0] == 94721 else '#3b8394')
        axes[1].text(task['end'] - training['start'] + .4, i, f'{duration:.2f}s',
                     va='center', fontsize=9)
    axes[1].set(yticks=range(6), yticklabels=[f'{t["item"][0]} / {t["item"][1]}'
                                            for t in training['tasks']],
                xlabel='Seconds since training queue began', xlim=(0, 55),
                title='DS26-0066: six training tasks, three workers')
    axes[1].invert_yaxis()
    fig.text(.5, .015, 'Left: unchanged-code executions, not an optimization pair. '
             'Right: one prepared target; all folds and both calibration arms retained.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .05, 1, 1))
    fig.savefig(out / 'profile.png', dpi=160)
    plt.close(fig)
    stage_rows = '\n'.join(f'| {name} | {runs[0]["stages"][name]:.3f} | '
                           f'{runs[1]["stages"][name]:.3f} |' for name in ordered)
    task_rows = '\n'.join(f'| {r["item"][0]} | {r["item"][1]} | {r["training_points"]} | '
                          f'{r["end"]-r["start"]:.3f} | {r["cpu_seconds"]:.3f} |'
                          for r in training['tasks'])
    bounds = training['posthoc_bounds']
    text = f'''# ALGO07v3: runtime bottlenecks and predictive queue profile

2026-11-06. Observation only; no numerical/runtime or production changes.

**The next target is the cost of long nuisance-model fits.** Scheduling is
already close to the best possible arrangement of the measured tasks. A larger
position cache also has negligible opportunity. Preserve the exact scientific
result while optimizing the numerical kernels used by several fitting stages.

![Complete stage timings and difficult training task intervals](profile.png)

## Complete pipeline costs

Two current-code DS26-0002 executions take **{runs[0]['seconds']:.3f} s** and
**{runs[1]['seconds']:.3f} s** from prepared native GLRT through publication.
These bracket the fresh original ALGO07 run; they are unchanged-code observations,
not a new optimization pair. Each retains both calibration arms, exact science,
ownership, grid/path values and eight byte-identical PNGs against the original.
Capture, detector extraction and queue waiting are excluded. Three CPU slots
and one BLAS thread per process are used throughout.

| Stage | Before reference, seconds | After reference, seconds |
| --- | ---: | ---: |
{stage_rows}

[All stages](stages.json) account for the remaining preparation, catalogue,
recovery and process overhead without adding nested substages twice. Predictive
recovery is the largest stage in both executions. Initial position search is
second. Several other stages invoke related numerical fitting, so a kernel gain
could benefit more than one stage; this must be measured, not multiplied by an
assumed call count. Evidence save varies 15.067 → 4.504 s with unchanged code,
illustrating why isolated before/after wall clocks can overstate a code gain.

The [fresh original/current comparison](../2026_11_06_algo07v3_reference_recovery/README.md)
is **886.905 s versus 193.899 / 152.529 s**, observed ratios **4.57–5.81×**.
Removing original orchestration/verification gaps gives an explicitly different
worker-plus-publication subtotal of 811.989 s, or **4.19–5.32×**.
One reference serves both comparisons. These are one-scan observations, not a
dataset-wide guarantee or a capture-to-WebUI production measurement.

## Why the difficult predictive target takes so long

DS26-0066 target 1 runs unchanged random grouped holdouts, three seeds and both
c=0/fitted-c arms. Each retains five phase rounds and 48 available position
iterations per round. The timer covers the whole prepared annotation, including
training and scoring; context construction is outside it. No evaluation GPS
enters fitting. All source/input bindings are in [plan.json](plan.json).

| Fold seed | Arm | Training points | Elapsed seconds | CPU seconds |
| --- | --- | ---: | ---: | ---: |
{task_rows}

Training occupies **{training['seconds']:.3f} s**; held-out scoring takes
**{scoring['seconds']:.3f} s**. Overall observed annotation takes
**{observed['seconds']:.3f} s**, using **{observed['cpu_seconds']:.3f} CPU seconds**.
The unobserved control takes {before['seconds']:.3f} s / {before['cpu_seconds']:.3f}
CPU seconds. This is an instrumentation control, not evidence of a speedup.
Complete annotation fingerprints agree; both decisions also match the saved
qualified native scientific receipt. Inputs are unchanged. [Raw results](result.json).

Training slot occupancy is **{100*training['three_slot_occupancy']:.1f}%**.
However, scheduling alone cannot use most idle capacity: the two long tasks
are already running while short tasks finish. Exhaustively simulating all
orders with these measured durations gives FIFO {bounds['fifo_seconds']:.3f} s
and a prescient best {bounds['optimistic_best_seconds']:.3f} s: only
**{bounds['fifo_seconds']-bounds['optimistic_best_seconds']:.3f} s** potential
reordering benefit. Task costs might change under another schedule; this is an
optimistic model, not a tested speedup or a generalizable scheduling policy.

The long fold has only 1,560 points versus 1,544 in a short fold. Point count
alone does not explain its roughly twentyfold cost. The earlier exact hard-call
capture reaches the 256 precision-iteration ceiling in its nuisance posterior.
This is evidence to investigate convergence and dense matrix cost, not permission
to reduce the budget or proof that every call in this annotation hits the ceiling.

## Inside a hard numerical fit

The [post-workspace profile](../2026_11_05_algo07v3_lapack_workspace/README.md)
measures three exact captured likelihood calls with 175 nuisance columns:

| Operation | Share of captured likelihood time |
| --- | ---: |
| Inverse solve | 30.8% |
| Covariance multiplication | 14.8% |
| LU factorization | 12.8% |
| Cholesky factorization | 8.3% |
| Ordered matrix/vector assembly | 6.5% |

These are nested component costs, not percentages of the whole pipeline and
not additive to the stage table. Roughly two thirds of this captured call is
dense matrix arithmetic. A 2× improvement to that portion would at best make
this call about 1.50× faster, before integration overhead; it does not establish
the same gain for an entire scan. Earlier whole-process cProfile traces had
inconsistent fork accounting, so these conclusions use independent stage
clocks and targeted exact instrumentation instead.

## Recommended experiments, in priority order

1. **Profile precision convergence across the slow and fast folds.** Record
   nuisance width, precision iterations and likelihood calls by phase round.
   Keep the same stopping rule. Determine whether exact repeated terms can be
   reused before considering any different solver. A changed stopping rule,
   warm start or approximation would need separate scientific qualification
   and would not automatically meet the current identical-output requirement.
2. **Prototype ordered weighted assembly in compiled code.** It currently
   accounts for 6.5% of the captured call. Fuse temporary creation and scatter
   while preserving multiplication/addition order, signed zero and non-fused
   arithmetic. This has a bounded upside: even eliminating assembly entirely
   would save only 6.5% of this call. Test exact kernels, both complete training
   arms and native publication before integrating.
3. **Investigate dense-solve copies and reuse with exact arithmetic.** This is
   the largest remaining arithmetic cost, but inverse-workspace reuse is already
   integrated. LU workspace, layout-only and combined variants were flat or
   inconsistent. Replacing inverse/covariance mathematics can change rounding;
   do not label it an exact optimization without complete proof and testing.
4. **Measure evidence serialization and publication separately.** Their total
   varies materially between runs. Attribute encoding, hashing and I/O before
   adding caches. Previous encoding-cache tests regressed; immutable persisted
   contracts and PNG bytes must remain unchanged.

Do not prioritize bigger position caches: the measured four additionally
reusable calculations total only **0.0783 s** across both hard training arms.
Do not assume a fourth worker fixes the tail: two indivisible long tasks still
dominate this target. Parallelizing work *inside* those tasks is a separate
experiment; earlier gradient parallelism had CPU/latency regressions. Any extra
CPU allowance must be reported separately from same-resource algorithm gains.

## Validation and reproduction

Nine component-owned tests pass, including actual six-task forked execution,
canonical ordering, unchanged returned values, failure propagation and bounds
validation. [Test receipt](tests.xml). The earlier 1,332 runtime tests remain
the numerical qualification; no runtime code changes in this iteration.

From the active worktree, with a fresh output root:

```sh
PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \\
  taskset -c 0,1,2 timeout -k 5 600 python -B \\
  tools/profile_algo07v3_training_queue.py --request PREPARED_REQUEST \\
  --output FRESH_OUTPUT --target 1
```

Use the pinned project Python. [The profiler](../../tools/profile_algo07v3_training_queue.py)
executes a fresh unobserved annotation and a fresh observed annotation without
changing admission, task order or scientific results. This renderer takes
`--root` (queue output) and `--native` (fresh cumulative run root), validates
bindings and exactness, and exports receipts/figures. Prepared target timings
exclude other scan stages; broader DS26 and production qualification remain open.
'''
    (out / 'README.md').write_text(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True)
    args = parser.parse_args()
    main(args.root, args.native)
