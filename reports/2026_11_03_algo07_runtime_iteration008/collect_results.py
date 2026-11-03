"""Collect completed replays and retain failures without qualifying them."""

import gzip
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUN = Path('/srv/bulk/leo/research/algo07-runtime-20261103')


def read(path):
    return json.loads(path.read_text())


def write(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def collect(source, name):
    target = OUT/'receipts'/name
    target.parent.mkdir(exist_ok=True)
    shutil.copyfile(source, target)
    return str(target.relative_to(ROOT))


def main():
    runtime_path = RUN/'algo03-cache-fixed-prototype/runtime-manifest.json'
    runtime = read(runtime_path)
    runtime_pin = hashlib.sha256(runtime_path.read_bytes()).hexdigest()
    rows, measurements = [], []
    for stage, case, folder, baseline, candidate in [
        ('algo03', 'single', 'algo03-fresh', 'baseline-repeat', 'cache-fixed'),
        ('algo03', 'joint', 'algo03-joint', 'baseline', 'cache-fixed'),
        ('algo07', 'single', 'fresh-fallback', 'replay-calibration-cache1', 'replay-cache-fixed'),
        ('algo07', 'two_family', 'slow-additive', 'replay-calibration-cache1-r2',
         'replay-cache-fixed'),
    ]:
        root = RUN/folder
        parity_file = root/('cache-fixed-parity-v2.json' if stage == 'algo03' and case == 'joint'
                            else 'cache-fixed-parity.json')
        parity = read(parity_file)
        assert parity['exact_leaves'] > 0
        if stage == 'algo03':
            assert parity['both_calibration_arms_required'] and parity['tolerance'] == 0
            assert parity['candidate_runtime_manifest_sha256'] == runtime_pin
        paths, times = [], []
        for label in (baseline, candidate):
            timing = read(root/label/'timing.json')
            assert timing['successful_execution'] and not timing['timed_out']
            assert timing['reference_after']['verified']
            times.append(timing['wall_seconds'])
            paths.append(collect(root/label/'timing.json', f'{stage}-{case}-{label}-timing.json'))
            collect(root/label/'launch.json', f'{stage}-{case}-{label}-launch.json')
        parity_path = collect(parity_file, f'{stage}-{case}-parity.json')
        rows.append(dict(stage=stage, case=case, parity_path=parity_path, timing_paths=paths))
        measurements.append(dict(stage=stage, case=case, baseline_seconds=times[0],
                                 candidate_seconds=times[1], speedup=times[0]/times[1],
                                 strict_parity_passed=parity['passed'],
                                 exact_leaves=parity['exact_leaves']))
    population = read(RUN/'population/cache-fixed-parity.json')
    policy = read(RUN/'cache-fixed-policy-parity.json')
    assert population['passed'] and len(population['results']) == 16
    assert policy['passed'] and policy['cases'] == 175
    collect(RUN/'population/cache-fixed-parity.json', 'population-parity.json')
    collect(RUN/'cache-fixed-policy-parity.json', 'saved-policy-parity.json')
    # Retain the invalid fast run and its actual failed audit, outside qualification.
    failed = RUN/'algo03-joint/candidate'
    collect(failed/'timing.json', 'rejected-cache-candidate-timing.json')
    collect(failed/'worker/recovery/joint-c0-audit-receipt.json', 'rejected-cache-audit.json')
    (OUT/'receipts/rejected-cache-audit.log.gz').write_bytes(gzip.compress(
        (failed/'worker/recovery/joint-c0-audit.log').read_bytes(), mtime=0))
    collect(RUN/'algo03-joint/kernel-diagnostic/kernel-comparison.json',
            'identical-input-kernel-comparison.json')
    collect(RUN/'algo03-joint/kernel-diagnostic/first-difference.npz',
            'first-kernel-difference.npz')
    name = 'tools/predictive_new_family.py'
    old = subprocess.check_output(['git', '-C', str(ROOT), 'show',
                                   '336715a398c2e6b9295318261bb63da76aaa2726:'+name])
    regression = read(OUT/'regression.json')
    assert regression['passed']
    current_sha = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    assert current_sha == runtime['files_sha256'][name]
    collect(runtime_path, 'candidate-runtime-manifest.json')
    write('cache-fix.json', dict(file=name, previous_sha256=hashlib.sha256(old).hexdigest(),
                               sha256=current_sha, runtime_manifest_sha256=runtime_pin,
                               regression_tests_passed=True))
    write('qualification.json', dict(
          passed=all(r['strict_parity_passed'] for r in measurements), scientific_tolerance=0,
          algo03_cases=[r for r in rows if r['stage'] == 'algo03'],
          algo07_cases=[r for r in rows if r['stage'] == 'algo07'],
          production_deployed=False))
    write('measurements.json', measurements)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    for ax, stage in zip(axes, ('algo03', 'algo07'), strict=True):
        selected = [r for r in measurements if r['stage'] == stage]
        for i, row in enumerate(selected):
            ax.bar(i-.18, row['baseline_seconds'], width=.36, color='#66788a',
                   label='Baseline' if i == 0 else None)
            ax.bar(i+.18, row['candidate_seconds'], width=.36, color='#18877f',
                   label='Corrected candidate' if i == 0 else None)
            label = f"{row['speedup']:.2f}×"
            if not row['strict_parity_passed']:
                label += ' (not qualified)'
            ax.text(i, max(row['baseline_seconds'], row['candidate_seconds'])*1.03,
                    label, ha='center', fontsize=9)
        ax.set_xticks(range(len(selected)), [r['case'].replace('_', ' ') for r in selected])
        ax.set_title(stage.upper()+' stage replay')
        ax.set_ylabel('Elapsed seconds')
        ax.set_ylim(0, max(r['baseline_seconds'] for r in selected)*1.2)
        ax.legend(fontsize=8)
    fig.suptitle('Stage timing; failed exact-parity trial is not qualified')
    fig.tight_layout()
    fig.savefig(OUT/'runtime.png', dpi=150)
    plt.close(fig)
    print(json.dumps(measurements))


if __name__ == '__main__':
    main()
