"""Describe saved alternative CFO gaps; no detector, tracking or inference call."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
OLD = Path('/srv/bulk/leo/research/ds24-measurement-continuity-r01/recorded')
OUT = ROOT / 'grid'
STEP = 1 / (512 * 4.4e-6)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=False)
    source = OLD / 'alternatives.csv'
    old_seal = json.loads((OLD/'seal.json').read_text())
    assert sha(source) == old_seal['alternatives.csv']
    bindings = {str(p): sha(p) for p in (
        source, OLD/'seal.json', ROOT/'CLOCK_AND_EXPORT_REVIEW.md',
        Path(__file__), Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src/leo/analysis/starlink/fast_scan_scores.py'))}
    rows = list(csv.DictReader(source.open()))
    assert len(rows) == 501
    output = []
    for row in rows:
        delta = float(row['circular_CFO_delta_hz'])
        assert 250 < abs(delta) <= 5000
        k = int(np.rint(delta / STEP))
        assert k != 0
        offset = delta - k * STEP
        output.append({**row, 'nearest_nonzero_bin_multiple': k,
                       'bin_residual_hz': offset,
                       'absolute_bin_residual_hz': abs(offset)})
    residual = np.array([r['absolute_bin_residual_hz'] for r in output])
    assert np.all(residual <= STEP/2 + 1e-9)
    counts = {str(t): int(np.sum(residual <= t)) for t in (1, 5, 25)}
    with (OUT/'all_pairs.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output[0]))
        writer.writeheader(); writer.writerows(output)
    summary = dict(pairs=len(output), unique_winning_windows=len({r['observation_id'] for r in output}),
                   step_hz=STEP, within_hz_counts=counts,
                   absolute_bin_residual_percentiles_hz={str(q): float(np.percentile(residual,q)) for q in (0,25,50,75,95,100)},
                   pair_denominator_not_independent_sources=True,
                   detector_calls=0, tracking_calls=0, position_fits=0,
                   source_bindings=bindings)
    (OUT/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    fig, axes = plt.subplots(1,2,figsize=(12,4.5))
    delta = np.array([float(r['circular_CFO_delta_hz']) for r in output])
    axes[0].hist(delta, bins=np.linspace(-5000,5000,81), color='#236da2')
    for k in range(-11,12):
        if k: axes[0].axvline(k*STEP, color='#c46a32', alpha=.23, lw=.7)
    axes[0].set(xlabel='Alternative − winning CFO (Hz; circular)', ylabel='Saved alternative pairs',
                title='All 501 pre-existing nearby alternatives')
    axes[1].hist(residual, bins=np.linspace(0,STEP/2,46), color='#236da2')
    for t in (1,5,25): axes[1].axvline(t,color='#c46a32',lw=.8,alpha=.8)
    axes[1].set(xlabel='Distance from nearest nonzero refinement-bin multiple (Hz)',
                ylabel='Saved alternative pairs', title='Descriptive bin alignment; not source identity')
    axes[1].text(.98,.96,'\n'.join(f'Within {t} Hz: {counts[str(t)]}/501' for t in (1,5,25)),
                 transform=axes[1].transAxes, ha='right',va='top',bbox=dict(facecolor='white',alpha=.9,edgecolor='none'))
    for ax in axes: ax.grid(alpha=.15)
    fig.suptitle('DS24-0011 exported hypotheses can include alternate refinements of one signal')
    fig.tight_layout()
    fig.savefig(OUT/'bin_alignment.png',dpi=180); fig.savefig(OUT/'bin_alignment.pdf')
    plt.close(fig)
    files = {str(p):sha(p) for p in sorted(OUT.iterdir()) if p.is_file()}
    files.update(bindings)
    (OUT/'seal.json').write_text(json.dumps(dict(files=files,scientific_inference=False),indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='source_bindings'},indent=2))


if __name__ == '__main__':
    main()
