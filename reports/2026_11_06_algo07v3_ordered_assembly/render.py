"""Report every assembly trial, exact native qualification and optional convergence profile."""

import argparse
import hashlib
import json
import shutil
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def validate_bindings(bindings, out, native):
    for name, digest in bindings.items():
        path = Path(name)
        options = [path, out / 'measured' / path.name, out / 'measured' / (path.name + '.bin')]
        if '/src/' in name:
            options.append(native / 'baseline-src' / name.split('/src/', 1)[1])
            options.append(out / 'candidate-src' / name.split('/src/', 1)[1])
        assert any(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == digest
                   for p in options), name


def main(native, kernel, training):
    out = Path(__file__).resolve().parent
    data = {}
    for label, root in [('ctypes', kernel),
                        ('native', kernel.with_name('algo07v3-native-assembly-kernel-20261106'))]:
        result = read(root / 'result.json')
        validate_bindings(result['bindings'], out, native)
        assert result['exact'] and len(result['rows']) == 12
        assert all(r['exact'] and r['unchanged_inputs'] for r in result['rows'])
        data[label] = result
        (out / f'{label}-kernel.json').write_bytes((root / 'result.json').read_bytes())
        (out / f'{label}-build.json').write_bytes((root / 'build.json').read_bytes())
    fits = read(training / 'result.json')
    validate_bindings(fits['plan']['bindings'], out, native)
    assert fits['exact'] and len(fits['rows']) == 8 and all(r['exact'] for r in fits['rows'])
    (out / 'training.json').write_bytes((training / 'result.json').read_bytes())
    (out / 'training-build.json').write_bytes((training / 'build.json').read_bytes())
    for name in ('baseline-src', 'candidate-src'):
        shutil.copytree(native / name, out / name, dirs_exist_ok=True)
    plan, comparison = read(native / 'plan.json'), read(native / 'comparison.json')
    validate_bindings(plan['bindings'], out, native)
    assert comparison['exact_owned_science_and_artifacts']
    clocks = {}
    for side in ('baseline', 'candidate'):
        clock = read(native / side / 'attempt/supervisor.json')
        assert clock['returncode'] == 0 and not clock['worker']['resumed']
        assert all(read(native / side / 'isolation.json')['checks'].values())
        lines = (native / side / 'attempt/worker.log').read_text().splitlines()
        rows = [json.loads(line) for line in lines if line.startswith('{')]
        stages = {r['stage']: r['seconds'] for r in rows if r.get('event') == 'stage'}
        stages['save'] = clock['worker']['evidence_save_seconds']
        stages['publication'] = clock['worker']['publication_seconds']
        stages['other'] = clock['process_seconds'] - sum(stages.values())
        assert stages['other'] >= 0
        resources = dict(line.strip().rsplit(': ', 1) for line in
                         (native / f'{side}-process-time.txt').read_text().splitlines()
                         if ': ' in line)
        assert resources['Exit status'] == '0'
        clocks[side] = dict(seconds=clock['process_seconds'], stages=stages,
                           cpu_seconds=float(resources['User time (seconds)']) +
                           float(resources['System time (seconds)']),
                           max_rss_kib=int(resources['Maximum resident set size (kbytes)']),
                           major_faults=int(resources['Major (requiring I/O) page faults']))
        for label, path in [('supervisor.json', native / side / 'attempt/supervisor.json'),
                            ('isolation.json', native / side / 'isolation.json'),
                            ('worker.log', native / side / 'attempt/worker.log'),
                            ('process-time.txt', native / f'{side}-process-time.txt')]:
            (out / f'{side}-{label}').write_bytes(path.read_bytes())
    for name in ('comparison.json', 'plan.json', 'build.json', 'tests-command.json',
                 'baseline-sources.json', 'candidate-sources.json'):
        (out / name).write_bytes((native / name).read_bytes())
    tests = Path('/srv/bulk/leo-dev/algo07v3-assembly-broad-tests-20261106.xml')
    suites = list(ET.parse(tests).getroot().iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in suites) == 1492
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('failures', 'errors', 'skipped'))
    (out / 'tests.xml').write_bytes(tests.read_bytes())
    final_tests = Path('/srv/bulk/leo-dev/algo07v3-assembly-final-tests-20261106.xml')
    final_suites = list(ET.parse(final_tests).getroot().iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in final_suites) == 1444
    assert all(int(s.attrib[k]) == 0 for s in final_suites
               for k in ('failures', 'errors', 'skipped'))
    (out / 'final-tests.xml').write_bytes(final_tests.read_bytes())
    for name, sha in read(out / 'default-restoration.json')['exact_restored_files'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, name
    summary = dict(clocks=clocks, native_exact=True, kernel={}, training_means=fits['means'],
                   tests=1492, full_ds26_qualified=False, production_modified=False)
    reverse = out / 'reverse'
    assert read(reverse / 'comparison.json')['exact_owned_science_and_artifacts']
    validate_bindings(read(reverse / 'plan.json')['bindings'], out, native)
    reverse_clocks = {}
    for side in ('baseline', 'candidate'):
        clock = read(reverse / f'{side}-supervisor.json')
        assert clock['returncode'] == 0 and not clock['worker']['resumed']
        assert all(read(reverse / f'{side}-isolation.json')['checks'].values())
        reverse_clocks[side] = clock['process_seconds']
    summary.update(reverse_native_seconds=reverse_clocks, numerical_runtime_changed=False,
                   candidate_adopted=False, final_default_tests=1444,
                   decision='Reject default integration: both native pairs regress')
    for label, result in data.items():
        means = {side: statistics.mean(r['seconds'] for r in result['rows'] if r['side'] == side)
                 for side in ('baseline', 'candidate')}
        summary['kernel'][label] = dict(means=means,
            reduction_percent=100 * (1 - means['candidate'] / means['baseline']))
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for i, side in enumerate(('baseline', 'candidate')):
        bars = ax.bar([j + .36*i for j in range(2)],
                       [clocks[side]['seconds'], reverse_clocks[side]], width=.34, label=side)
        ax.bar_label(bars, fmt='%.1f s', padding=3)
    ax.set(xticks=[.18, 1.18], xticklabels=['Baseline first', 'Candidate first'],
           ylabel='GLRT-ready through publication (seconds)', ylim=(0, 300),
           title='Both complete-scan pairs regress: candidate not adopted')
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / 'complete-pairs.png', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    for ax, (label, result) in zip(axes[:2], data.items(), strict=True):
        for pair in range(6):
            values = {r['side']: r['seconds'] for r in result['rows'] if r['pair'] == pair}
            ax.plot([0, 1], [values['baseline'], values['candidate']], 'o-', label=f'Pair {pair+1}')
        ax.set(xticks=[0, 1], xticklabels=['Baseline', 'Candidate'], ylabel='Seconds per full call',
               title=f'{label}: {summary["kernel"][label]["reduction_percent"]:.2f}% reduction')
    for arm, color in [('c0', '#327ca5'), ('fitted_c', '#bf7036')]:
        for pair in range(2):
            values = {r['side']: r['seconds'] for r in fits['rows']
                      if r['arm'] == arm and r['pair'] == pair}
            axes[2].plot([0, 1], [values['baseline'], values['candidate']],
                         'o-' if pair == 0 else 'o--', color=color, label=f'{arm}, pair {pair+1}')
    axes[2].set(xticks=[0, 1], xticklabels=['Baseline', 'Candidate'],
                ylabel='Full training seconds',
                title='DS26-0066: five rounds, both arms')
    axes[2].legend(fontsize=8)
    fig.suptitle('Ordered assembly: retain the slower interface and every comparison')
    fig.tight_layout()
    fig.savefig(out / 'experiments.png', dpi=160)
    plt.close(fig)
    names = sorted(clocks['baseline']['stages'],
                   key=lambda n: max(c['stages'][n] for c in clocks.values()), reverse=True)
    fig, ax = plt.subplots(figsize=(10, 7))
    for i, (label, clock) in enumerate(clocks.items()):
        bars = ax.barh([j + .38*i for j in range(len(names[:14]))],
                        [clock['stages'][n] for n in names[:14]], height=.36,
                        label=f'{label}: {clock["seconds"]:.2f} s')
        ax.bar_label(bars, fmt='%.1f', fontsize=8, padding=2)
    ax.set(yticks=[j+.19 for j in range(len(names[:14]))], yticklabels=names[:14],
           xlabel='Elapsed seconds', title='Native DS26-0002: complete publication comparison')
    ax.invert_yaxis()
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / 'native.png', dpi=160)
    plt.close(fig)
    stages = '\n'.join(f'| {n} | {clocks["baseline"]["stages"][n]:.3f} | '
                        f'{clocks["candidate"]["stages"][n]:.3f} |' for n in names)
    pairs = '\n'.join(f'| {r["arm"]} | {r["pair"]+1} | {r["side"]} | '
                       f'{r["seconds"]:.3f} | {r["cpu_seconds"]:.3f} |' for r in fits['rows'])
    text = f'''# ALGO07v3: compiled assembly rejected after complete-scan regressions

**Compiled assembly is not adopted.** It improves the difficult prepared fits,
but both complete native scan comparisons are slower. All scientific results
remain exact; exactness alone is insufficient evidence for a runtime optimization.
The existing NumPy assembly and build configuration have been restored.

| Full DS26-0002 comparison | Baseline | Compiled candidate |
| --- | ---: | ---: |
| Baseline first | {clocks['baseline']['seconds']:.3f} s | {clocks['candidate']['seconds']:.3f} s |
| Candidate first | {reverse_clocks['baseline']:.3f} s | {reverse_clocks['candidate']:.3f} s |

The candidate regresses by **14.67%** and **10.85%** respectively. Both runs in
each pair use CPUs 0–2, one BLAS thread, identical inputs and full budgets.
Shared-host variation is substantial, including unchanged screening/rendering
stages; production analysis jobs were observed sharing the allowed CPUs.
That observation does not prove the cause of either timed regression. We retain
the negative full-scan evidence rather than assuming it is all host noise.
[Reverse comparison](reverse/comparison.json), [post-pair host observation](host-observation.json).

![Both complete native comparisons](complete-pairs.png)

The direct compiled assembly preserves scientific outputs and improves all four
complete DS26-0066 training pairs. Fitted-c averages **45.898 → 44.701 s** (2.61%).
The c=0 reverse-order pair improves **47.304 → 46.527 s** (1.64%); its first pair
57.358 → 51.031 s is much larger and should not be treated as a stable expected
gain. Both arms retain the original data, priors, random grouped holdouts, five
phase rounds and 48 available optimizer iterations per round.

The candidate passes **1,492 tests** and both complete native
DS26-0002 correctness checks with exact scientific evidence, both c arms, ownership,
grid/path values and all eight PNG bytes. [Comparison](comparison.json).
Production and full DS26 qualification remain unchanged.

## What changes

The existing likelihood creates two weighted temporary vectors and calls
NumPy scatter-add for each posterior update. The rejected compiled extension
performs the same separate multiplications and additions in the same order.
It checks vector layout, types, lengths, aliasing and bounds before mutation.
Build flags explicitly disable fast math and fused multiply-add. The posterior
iteration ceiling, stopping rule, inverse solve, covariance and all downstream
arithmetic are unchanged. No larger cache, changed scheduling, approximation
or early stopping is introduced.

The independent provenance improvement is retained: native module bytes enter
the existing implementation-provenance map, alongside
Python modules. This binds the actual compiled numerical implementation rather
than only its Python caller. The map's structure and public scientific contracts
are unchanged. Tests verify a changed native artifact changes its binding.

## Two interfaces, one arithmetic experiment

The first ctypes interface is exact but **3.46% slower** on the captured full
likelihood. Its Python validation and call overhead appear to outweigh the saved
work; this is an interpretation, not an independently timed attribution. It is
rejected. The direct extension averages **0.212564 → 0.204062 s** (4.00% faster),
with five improving pairs and one regression. Both interfaces run 60 exact
captured likelihood calls. Do not multiply this kernel gain into the pipeline.

![All kernel and complete-training pairs](experiments.png)

| Arm | Pair | Side | Elapsed s | CPU s |
| --- | ---: | --- | ---: | ---: |
{pairs}

Every training comparison matches the previously qualified full fit signature:
optimizer history, phase reference, endpoint, likelihood and state, not merely
a newly generated baseline. Context loading and final signature checks are
outside these training timers. [Raw training](training.json).

## Complete native scan

The fresh sequential comparison observes **{clocks['baseline']['seconds']:.3f} →
{clocks['candidate']['seconds']:.3f} seconds** from native GLRT ready through
publication, on CPUs 0–2 with one BLAS thread and unchanged 1,200-second bounds.
The two private namespaces hide historical installations and results; all input,
source and build bindings are recorded. Capture, detector extraction and queue
waiting are outside the clock. This is one shared-host pair, not a population
speed guarantee or a new cumulative comparison against original ALGO07.

![Native stages, including unchanged work](native.png)

| Stage | Baseline s | Candidate s |
| --- | ---: | ---: |
{stages}

Inspect unchanged stages and [resource receipts](candidate-process-time.txt)
before attributing the entire elapsed difference to assembly. The narrower
complete-training pairs support a modest component gain, which is insufficient
to adopt the candidate given both full-scan regressions. The last original-ALGO07
[cumulative comparison](../2026_11_06_algo07v3_reference_recovery/README.md)
remains 886.905 versus 193.899 / 152.529 s for the preceding implementation;
do not combine those historical clocks with this candidate's time.

GNU-time user-plus-system CPU is **{clocks['baseline']['cpu_seconds']:.3f} →
{clocks['candidate']['cpu_seconds']:.3f} s**; maximum reported per-process RSS is
{clocks['baseline']['max_rss_kib']:,} → {clocks['candidate']['max_rss_kib']:,} KiB.
Major page faults are {clocks['baseline']['major_faults']} →
{clocks['candidate']['major_faults']}. CPU includes descendants and the outer
wrapper; maximum RSS is not aggregate concurrent memory. These wider resource
observations are retained separately from the supervisor's primary clock.

## Tests, build and reproducibility

The 1,492-test suite has no failures or skips. Its three warnings are existing
NumPy shape-mutation deprecations. Tests include sparse/dense and empty designs,
both prior modes, duplicate destinations, signed zeros, catastrophic cancellation,
non-fused arithmetic, non-native byte order, invalid indices, read-only output,
input aliasing, complete likelihood comparisons and all existing pipeline checks.
No numerical oracle or tolerance changes. The older inverse-workspace body proof
is retained against an exact frozen pre-assembly oracle; the new body and native
source are separately proven to match the measured prototype.

The archived candidate `measured/setup.py` declares the extension and its C dependency
using the existing build
system. The pinned runtime environment lacks setuptools, so direct `setup.py
build_ext` initially fails before compilation. It was not modified or repackaged.
[build_extension.py](build_extension.py) reproduces the recorded strict compiler
command locally; normal wheel builds use the declared setuptools build dependency.
[Build receipt](build.json). The experimental candidate library is content-bound
in the native plan and resulting scientific provenance. Do not deploy a binary
from a different toolchain without its own qualification.

The external tools are `probe_algo07v3_ordered_assembly.py` (rejected ctypes),
`probe_algo07v3_native_assembly.py` (direct extension), and
`benchmark_algo07v3_ordered_assembly.py` (complete training). Use the pinned
Python, `PYTHONPATH=src:tools`, one BLAS thread, CPU 0 and fresh output roots.
Kernel runs take `--capture` / `--output`; training takes `--request`,
`--expected-root` / `--output` and was bounded to 900 s. Exact measured helper
bytes are preserved under `measured/`; current helpers use the frozen pre-change
oracle so future runtime edits cannot silently redefine their baseline.

[run_pair.py](run_pair.py) takes a fresh prepared root with baseline/candidate
source snapshots and a native request. It runs both complete owned jobs and
declares exactly the likelihood/provenance changes and new native module to the
comparator. Source snapshots, full commands, test receipt and figures are retained.

The [completed convergence profile](convergence.md) now explains the slow fold:
matrix dimensions stay fixed, but its first phase makes 269 calls per arm and
220 calls reach the 256-iteration ceiling. Later rounds generally need only 10
iterations per call. All six full signatures remain exact. This shifts the next
investigation toward the first-round convergence trajectory and exact reusable
work across arms/targets, not larger caches or arbitrary stopping-rule changes.

The default numerical source and packaging are restored to their pre-experiment
bytes. Candidate source lives under `candidate-src/`, its integration tests under
`candidate-tests/`, and its measured binary is archived as `.so.bin`. To reproduce
the rejected native candidate, restore those files and `measured/setup.py` into
an isolated experimental checkout, build there, and use the archived source
snapshots with `run_pair.py`. They are evidence, never runtime dependencies of
the default implementation. No production deployment occurred.

After restoring the default, its broader suite passes **1,444 tests** with no
failures or skips. [Final tests](final-tests.xml),
[exact restoration hashes](default-restoration.json).
The candidate's 1,492-test receipt remains separate; tests for its removed native
runtime are archived with that candidate rather than silently reported as current.
'''
    (out / 'README.md').write_text(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--training', type=Path, required=True)
    args = parser.parse_args()
    main(args.native, args.kernel, args.training)
