"""Report the complete original/current comparison without hiding harness cost."""

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
    for name, digest in plan['bindings'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    assert comparison['all_checked_values_exact'] and not comparison['errors']
    assert not comparison['missing_audit_mappings']
    assert len(comparison['mapped_policies']) == 17
    assert not comparison['full_intermediate_equivalence']
    assert all(read(root / 'v3-run/isolation.json')['checks'].values())
    original = read(root / 'reference-timing/summary.json')
    candidate = read(root / 'v3-run/attempt/supervisor.json')
    assert original['state'] == 'completed_unqualified'
    assert candidate['status'] == 'exited' and candidate['returncode'] == 0
    assert candidate['worker']['status'] == 'complete' and not candidate['worker']['resumed']
    metadata = read(root / 'initial-metadata.json')
    assert metadata['initial_metadata_links_verified'] and len(metadata['policies']) == 5
    suites = list(ET.parse(root / 'metadata-tests.xml').getroot().iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in suites) == 19
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('failures', 'errors', 'skipped'))
    workers = []
    for attempt in original['inference']['attempts']:
        workers.extend(row for row in read(Path(attempt['receipt_path']))['stages']
                       if row['executed'])
    assert [r['algorithm'] for r in workers] == [f'ALGO{i:02d}' for i in range(2, 8)]
    worker_seconds = sum(r['wall_seconds'] for r in workers)
    publication = original['publication']['wall_seconds']
    reference_seconds = original['completed_path_seconds']
    v3_seconds = candidate['process_seconds']
    repeat_root = root / 'after-reference'
    repeat = read(repeat_root / 'cli/attempt/supervisor.json')
    repeat_comparison = read(repeat_root / 'comparison.json')
    assert repeat['status'] == 'exited' and repeat['returncode'] == 0
    assert repeat['worker']['status'] == 'complete' and not repeat['worker']['resumed']
    assert repeat_comparison['all_checked_values_exact'] and not repeat_comparison['errors']
    assert not repeat_comparison['missing_audit_mappings']
    assert len(repeat_comparison['mapped_policies']) == 17
    assert all(read(repeat_root / 'cli/isolation.json')['checks'].values())
    for name, digest in read(repeat_root / 'plan.json')['bindings'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    repeat_seconds = repeat['process_seconds']
    overhead = reference_seconds - worker_seconds - publication
    assert overhead >= 0
    cpu = {}
    for side, path in (
        ('reference', root / 'reference-process-time.txt'),
        ('candidate', root / 'candidate-process-time.txt'),
        ('candidate_after', repeat_root / 'process-time.txt'),
    ):
        text = path.read_text()
        fields = dict(line.strip().rsplit(': ', 1) for line in text.splitlines() if ': ' in line)
        assert fields['Exit status'] == '0'
        cpu[side] = dict(user_seconds=float(fields['User time (seconds)']),
                         system_seconds=float(fields['System time (seconds)']),
                         max_rss_kib=int(fields['Maximum resident set size (kbytes)']),
                         major_faults=int(fields['Major (requiring I/O) page faults']))
    summary = dict(
        scan='DS26-0002', original_seconds=reference_seconds, native_v3_seconds=v3_seconds,
        observed_ratio=reference_seconds / v3_seconds,
        observed_reduction_percent=100 * (1 - v3_seconds / reference_seconds),
        native_v3_after_reference_seconds=repeat_seconds,
        after_reference_observed_ratio=reference_seconds / repeat_seconds,
        observation_order=['v3-before', 'original', 'v3-after'],
        original_worker_seconds=worker_seconds, original_publication_seconds=publication,
        original_other_in_interval_seconds=overhead,
        original_workers_plus_publication_seconds=worker_seconds + publication,
        original_workers_plus_publication_ratio=(worker_seconds + publication) / v3_seconds,
        all_public_values_and_17_scientific_audits_exact=True, initial_metadata_fields=21,
        process_cpu_accounting=cpu, qualified_speedup=None, full_dataset_equivalence=False,
        full_intermediate_equivalence=False, production_modified=False,
        runtime_commit='d9fbe5bb96ab47885e28b5e9f32105b8c88b04ff',
    )
    copies = {name: root / name for name in (
        'plan.json', 'comparison.json', 'initial-metadata.json', 'metadata-tests.xml',
        'candidate-process-time.txt', 'reference-process-time.txt',
        'candidate-resources-start.json', 'candidate-resources-end.json',
        'reference-resources-start.json', 'reference-resources-end.json',
        'candidate-execution.json', 'reference-execution.json')}
    copies.update({'reference-timing.json': root / 'reference-timing/summary.json',
                   'candidate-timing.json': root / 'v3-run/attempt/supervisor.json',
                   'candidate-isolation.json': root / 'v3-run/isolation.json'})
    for name, path in copies.items():
        (out / name).write_bytes(path.read_bytes())
    repeat_out = out / 'after-reference'
    repeat_out.mkdir(exist_ok=True)
    for name in ('plan.json', 'comparison.json', 'candidate-execution.json',
                 'candidate-resources-start.json', 'candidate-resources-end.json',
                 'process-time.txt'):
        (repeat_out / name).write_bytes((repeat_root / name).read_bytes())
    (repeat_out / 'supervisor.json').write_bytes(
        (repeat_root / 'cli/attempt/supervisor.json').read_bytes())
    (repeat_out / 'isolation.json').write_bytes((repeat_root / 'cli/isolation.json').read_bytes())
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))
    bars = axes[0].bar(['V3 before', 'Original ALGO07', 'V3 after'],
                       [v3_seconds, reference_seconds, repeat_seconds],
                       color=['#3465a4', '#777777', '#3465a4'])
    axes[0].bar_label(bars, fmt='%.1f s', padding=3)
    axes[0].set(ylabel='Fresh GLRT-ready → published artifacts (seconds)',
                title='Same scan · execution order',
                ylim=(0, max(reference_seconds, v3_seconds, repeat_seconds) * 1.18))
    values = [worker_seconds, publication, overhead]
    bars = axes[1].bar(['Six workers', 'Publication', 'Other in interval'], values,
                       color=['#777777', '#999999', '#bbbbbb'])
    axes[1].bar_label(bars, fmt='%.1f s', padding=3)
    axes[1].set(ylabel='Seconds', title='Original reference accounting',
                ylim=(0, max(values) * 1.18))
    fig.text(.5, .02, 'Both arms, 17 scientific mappings and all public artifacts exact · '
             'shared host · admission/metadata/population gates remain', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, 1))
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    stages = '\n'.join(f"| {r['algorithm']} | {r['wall_seconds']:.3f} |" for r in workers)
    resources = '\n'.join(f"| {name} | {v['user_seconds']:.2f} | {v['system_seconds']:.2f} | "
                          f"{v['major_faults']} | {v['max_rss_kib']} |" for name, v in cpu.items())
    report = f'''# ALGO07 versus standalone ALGO07v3: fresh cumulative timing observation

2026-11-05. No production changes or RF collection.

Both fresh DS26-0002 runs complete, and **all public results, both calibration
arms, all eight PNG bytes, grid/path values and all 17 mapped scientific audit
sections match exactly**. The comparison retains its open historical metadata
and admission-policy gates. [Complete comparison](comparison.json).

| Path | GLRT ready through publication |
| --- | ---: |
| Standalone v3, before reference | **{v3_seconds:.3f} s** |
| Original six-worker ALGO07 reference | **{reference_seconds:.3f} s** |
| Standalone v3, after reference | **{repeat_seconds:.3f} s** |

The observed ratio is **{reference_seconds / v3_seconds:.3f}×**, or
**{100 * (1 - v3_seconds / reference_seconds):.2f}% less elapsed time**. This is a
fresh cumulative comparison on one scan, not a controlled population estimate
or a demonstrated tenfold speedup. The v3 leg ran first; both legs used CPUs
0–2, one BLAS thread per process, fixed input/archive evidence and fresh output
directories. No reference answers enter v3. The candidate hides old installations,
bulk results and reports in a private namespace. [Execution plan](plan.json).

An additional fresh v3 execution after the reference takes
**{repeat_seconds:.3f} s** and again matches all 17 scientific sections and public
artifacts exactly. Relative to the intervening reference its observed ratio is
**{reference_seconds / repeat_seconds:.3f}×**. This third leg was declared after
the first pair exposed differing CPU pressure and major page faults. Both v3
observations are retained; their variation prevents treating either ratio as a
stable dataset-wide guarantee. The second comparison reuses the middle
reference, so these are three executions, not two independent pairs.
[Repeat plan](after-reference/plan.json), [comparison](after-reference/comparison.json).

![Fresh complete timings and original accounting](runtime.png)

## Separate algorithm work from research-harness cost

The reference's recorded interval contains **{worker_seconds:.3f} s** in its six
executed watcher/worker calls and **{publication:.3f} s** in first publication.
The remaining **{overhead:.3f} s** includes orchestration, terminal checks and
frozen-runtime verification. Do not label all of this remainder scientific
computation or assume production incurs identical verification overhead.

The worker-plus-publication subtotal is **{worker_seconds + publication:.3f} s**.
Dividing that subtotal by the complete v3 time gives
**{(worker_seconds + publication) / v3_seconds:.3f}×**. This deliberately omits
reference orchestration gaps, so it is a separately labeled subtotal ratio,
not another continuous end-to-end measurement. Capture, GLRT extraction and
production queue delay are excluded from both paths.

| Original executed stage | Seconds |
| --- | ---: |
{stages}

## Resource observations and limits

| Invocation | User CPU s | System CPU s | Major page faults | Max RSS KiB |
| --- | ---: | ---: | ---: | ---: |
{resources}

GNU time includes descendants and pre/post verification outside the primary
interval; CPU totals therefore have a wider scope than the primary wall clock.
Maximum RSS is per-process accounting, not concurrent aggregate memory.
The current v3 run incurs {cpu['candidate']['major_faults']:,} major page faults;
the earlier 228.848-second observation is not substituted for this slower run.
Shared-host CPU, I/O, cache and frequency effects remain uncontrolled. Boundary
resource snapshots are retained rather than assuming constant load.

The original workers retain ordinary elapsed-time admission and their six
1,200-second allowances. V3 uses validation-all-work with a 1,200-second outer
bound. Exact completed science establishes agreement here; it does not prove
the admission policies equivalent under other inputs/load. Both grids complete
their requested 179 locations; original presentation has its documented 300 s
research allowance. No inference thresholds, priors or search budgets were
relaxed to make the comparison pass.

## Metadata audit progress

A separate read-only verifier now checks **21 previously excluded metadata
fields across five initial policies**: exact case/algorithm identities,
radio-noise mode, source-code hashes against the frozen manifest, prior-TLE and
ordered input-read links, history/forecast/baseline digests and cavity nomination
links. Timing fields must be finite nonnegative observations; their values need
not be equal. All checks pass against this fresh export. [Audit](initial-metadata.json).

**19 component-owned tests pass**, including altered source bytes, swapped
history links, incomplete/duplicate reads, wrong scan identity, redirected TLE
links and invalid elapsed times. The earlier 843-test runtime suite remains
the runtime qualification; no inference code changes in this benchmark.
[Tests](metadata-tests.xml).

Later-policy metadata, broader accepted branches, full DS26 localization,
production admission/deadlines and the tenfold target remain open. The new
metadata verifier does not silently override the existing comparator's verdict.

Reproduce using [run.py](run.py) with a fresh `--root`; it prepares native-only
exports through the public store port, runs both legs, then reconstructs the
three independent scientific oracles and performs the full comparison. Run
[repeat_v3.py](repeat_v3.py) with `--parent` pointing to that root for the third
execution. The [metadata verifier](../../tools/check_algo07v3_initial_metadata.py)
takes `--evidence`, `--runtime`, `--manifest` and a fresh `--output`; its receipt
binds the exact source and exported artifacts. Raw
evidence: `{root}`. Runtime commit: `d9fbe5bb9`.
'''
    (out / 'README.md').write_text(report)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    main(parser.parse_args().root.resolve())
