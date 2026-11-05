"""Render a completed exact family-concurrency pair and its measured costs."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def main(root):
    out = Path(__file__).resolve().parent
    plan, comparison = read(root / 'plan.json'), read(root / 'comparison.json')
    for bindings in (plan['bindings'], comparison['input_bindings']):
        for name, digest in bindings.items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    assert comparison['exact_owned_science_and_artifacts'] and comparison['both_c_arms']
    assert comparison['source_changes'] == sorted([
        'leo.analysis.localization_v3.history_policy', 'leo.application.localization_v3',
        'leo.application.localization_v3_engine', 'leo.operations.localization_v3_job'])
    assert comparison['added_modules'] == []
    suites = list(ET.parse(root / 'tests.xml').getroot().iter('testsuite'))
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('failures', 'errors', 'skipped'))
    count = sum(int(s.attrib['tests']) for s in suites)
    times, stages, cpu = {}, {}, {}
    copies = {name: root / name for name in (
        'plan.json', 'comparison.json', 'tests.xml', 'test-command.json', 'focused-tests.xml',
        'baseline-sources.json', 'baseline-process-time.txt', 'candidate-process-time.txt')}
    for side in ('baseline', 'candidate'):
        clock = read(root / side / 'attempt/supervisor.json')
        assert clock['status'] == 'exited' and clock['returncode'] == 0
        assert clock['worker']['status'] == 'complete' and not clock['worker']['resumed']
        assert all(read(root / side / 'isolation.json')['checks'].values())
        times[side] = clock['process_seconds']
        rows = [json.loads(line) for line in (root / side / 'attempt/worker.log')
                .read_text().splitlines()]
        stages[side] = {r['stage']: r['seconds'] for r in rows if r.get('event') == 'stage'}
        text = (root / f'{side}-process-time.txt').read_text()
        values = dict(line.strip().rsplit(': ', 1) for line in text.splitlines() if ': ' in line)
        assert values['Exit status'] == '0'
        cpu[side] = dict(user_seconds=float(values['User time (seconds)']),
                         system_seconds=float(values['System time (seconds)']),
                         maximum_rss_kbytes=int(values['Maximum resident set size (kbytes)']))
        for name, path in {
            f'{side}-supervisor.json': root / side / 'attempt/supervisor.json',
            f'{side}-isolation.json': root / side / 'isolation.json',
            f'{side}-resources-start.json': root / f'{side}-resources-start.json',
            f'{side}-resources-end.json': root / f'{side}-resources-end.json',
        }.items():
            copies[name] = path
    assert list(stages['baseline']) == list(stages['candidate'])
    reduction = 100 * (1 - times['candidate'] / times['baseline'])
    summary = dict(exact=True, seconds=times, stages=stages, process_cpu_accounting=cpu,
                   observed_reduction_percent=reduction, qualified_speedup=None,
                   production_modified=False, enabled_in_development=True,
                   full_dataset_equivalence=False, component_tests=count)
    for name, path in copies.items():
        (out / name).write_bytes(path.read_bytes())
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    colors = ['#777777', '#3465a4']
    bars = axes[0].bar(['Serial family fits', 'Concurrent family fits'], list(times.values()),
                       color=colors)
    axes[0].bar_label(bars, fmt='%.1f s', padding=3)
    axes[0].set(ylabel='Native GLRT ready → supervisor exit (seconds)',
                title='DS26-0002 · complete pipeline', ylim=(0, max(times.values()) * 1.16))
    labels = sorted(stages['baseline'], key=stages['baseline'].get, reverse=True)[:7][::-1]
    y = np.arange(len(labels))
    for i, side in enumerate(times):
        axes[1].barh(y + (i - .5) * .36, [stages[side][k] for k in labels],
                     height=.36, color=colors[i], label=side)
    axes[1].set(yticks=y, yticklabels=labels, xlabel='Observed wall seconds',
                title='Largest stages · unchanged scientific work')
    axes[1].legend()
    fig.text(.5, .02, 'Exact science, both calibration arms, eight PNGs and publication · '
             'shared host · one scan', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, 1))
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    table = '\n'.join(f"| {name} | {stages['baseline'][name]:.3f} | "
                      f"{stages['candidate'][name]:.3f} |" for name in stages['baseline'])
    cpu_table = '\n'.join(f"| {side} | {r['user_seconds']:.2f} | "
                          f"{r['system_seconds']:.2f} | {r['maximum_rss_kbytes']} |"
                          for side, r in cpu.items())
    direction = f'{abs(reduction):.2f}% ' + ('lower' if reduction >= 0 else 'higher')
    report = f'''# ALGO07v3: concurrent family fits in the standalone CLI

2026-11-05. Development integration; production unchanged.

The c=0 and fitted-c family fits now execute in two owned child processes. The
parent retains the original arm order, combines failed-track gates and applies
the shared mask before the next fitting round. The linear trial also uses two
independent children; its paired acceptance decision remains sequential.
Catalogue, priors, budgets, arithmetic and scientific selection are unchanged.
The existing bounded executor handles failures and cancellation. An incomplete
child fit aborts the stage instead of becoming a scientific track rejection.

**{count} component tests pass.** Tests compare the integrated numerical path
with a frozen serial oracle for whole/masked synthetic evidence, successive
rejection rounds, and child failures. Application and job tests verify that
only the family policy receives the new execution port. The focused suite is
included in the broad count. [Tests](tests.xml), [command](test-command.json).

Both fresh isolated DS26-0002 runs complete, with older installations, bulk
results and reports hidden, the input bundle read-only, and networking isolated.
**All scientific outputs, both calibration arms, eight PNG bytes, grid/path
values and public fields are exact.** Only the four declared implementation
modules differ; no runtime modules are added. [Comparison](comparison.json).

The serial-family baseline takes **{times['baseline']:.3f} s** and the concurrent
candidate **{times['candidate']:.3f} s** from native GLRT input through supervisor
exit after publication: an observed **{direction}** wall time. This excludes
capture, GLRT extraction and production queue delay. It is one sequential pair
on a shared host, with the baseline first, CPUs 0–2, one BLAS thread per process
and identical 1,200 s outer deadlines. It is not a cumulative legacy-to-v3 or
population-wide speedup. [Plan and source bindings](plan.json).

Unchanged stages also become faster: initial fitting takes
{stages['baseline']['initial']:.3f} → {stages['candidate']['initial']:.3f} s,
before either run reaches the modified family stage. Consequently the full
wall-time difference cannot be attributed solely to family concurrency.
Family fitting itself takes {stages['baseline']['family']:.3f} →
{stages['candidate']['family']:.3f} s. Retain both the stage and complete-path
measurements instead of treating the whole observed difference as a causal gain.

![Complete runtime and stage comparison](runtime.png)

| Stage | Serial family fits (s) | Concurrent family fits (s) |
| --- | ---: | ---: |
{table}

| Whole-process accounting | User CPU s | System CPU s | Maximum RSS KiB |
| --- | ---: | ---: | ---: |
{cpu_table}

CPU accounting includes waited-for children. Maximum RSS is the reported
per-process maximum, not the sum of simultaneously resident child processes.
Concurrency trades additional process work for latency; stage savings must not
be added to older complete-path observations.

Full DS26 localization, broader accepted branches, production admission and
deadlines, historical metadata semantics and the cumulative tenfold target
remain open. The CLI remains qualified for validation-all-work only. This
change is not deployed.

Reproduce from this checkout using the source-bound baseline module copies in
`{root}/baseline-src` and fresh request/output paths; [run_pair.py](run_pair.py)
and [run_baseline.sh](run_baseline.sh) preserve the isolated comparison procedure.
Raw evidence: `{root}`.
'''
    (out / 'README.md').write_text(report)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    main(parser.parse_args().root.resolve())
