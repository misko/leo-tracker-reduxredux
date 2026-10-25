"""Plot only sealed saved evaluation values; performs no scientific fitting."""
from pathlib import Path
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    data = HERE / 'report'
    seal = json.loads((data / 'data_seal.json').read_text())
    for path, digest in seal['files'].items():
        assert sha(path) == digest
    rows = json.loads((data / 'positions.json').read_text())['rows']
    cases = [f'DS24-{i:04d}' for i in range(10, 14)]
    fig, axes = plt.subplots(2, 2, figsize=(11.6, 7.4), layout='constrained')
    for col, (arm, label) in enumerate((('c0', 'c = 0'), ('fitted_c', 'fitted c'))):
        def values(variant, field):
            return [next(r[field] for r in rows if r['case'] == case
                         and r['arm'] == arm and r['variant'] == variant) for case in cases]
        reference = values('original_reference', 'error_km')
        raw = values('raw_candidate', 'error_km')
        assert values('matched_cold_baseline', 'error_km') == reference
        assert values('research_policy', 'error_km') == reference
        assert values('operational_reference', 'error_km') == reference
        assert not any(values('raw_candidate', 'research_pair_eligible'))
        x = np.arange(4)
        ax = axes[0, col]
        ax.bar(x - .18, reference, .36, color='#3973a5', label='Reference; both policies identical')
        ax.bar(x + .18, raw, .36, color='#cf8c55', hatch='///', edgecolor='#734a27',
               label='Raw candidate: all unqualified')
        ax.set(title=label, xticks=x, xticklabels=[c[-4:] for c in cases],
               ylabel='Position error (km)', ylim=(0, 2.25))
        if col == 0:
            ax.legend(frameon=False, fontsize=8, loc='upper left')
        ax = axes[1, col]
        changes = 1000 * np.array(values('raw_candidate', 'error_change_km'))
        bars = ax.bar(x, changes, .55, color='#cf8c55', hatch='///', edgecolor='#734a27')
        ax.axhline(0, color='#3973a5', lw=1.5, label='Policy change: zero for every case')
        for bar, change in zip(bars, changes):
            ax.annotate(f'{change:+.1f}', (bar.get_x() + bar.get_width()/2, change),
                        xytext=(0, 5 if change >= 0 else -13), textcoords='offset points',
                        ha='center', fontsize=9)
        ax.set(xticks=x, xticklabels=[c[-4:] for c in cases], ylim=(-78, 78),
               ylabel='Raw error change (m); lower is better', xlabel='Exposed development scan')
        if col == 0:
            ax.legend(frameon=False, fontsize=8, loc='lower left')
    fig.suptitle('Retained parent orbit uncertainty: diagnostic geography\n'
                 'Four cases, no qualified candidates; reference remains operational', fontsize=14)
    target = HERE / 'figures'
    target.mkdir(exist_ok=False)
    for suffix in ('png', 'pdf'):
        fig.savefig(target / f'raw_vs_policy.{suffix}', dpi=160)
    plt.close(fig)
    files = [target / 'raw_vs_policy.png', target / 'raw_vs_policy.pdf']
    (target / 'seal.json').write_text(json.dumps({
        'files': {str(p): sha(p) for p in files},
        'source_sha256': sha(__file__), 'evaluation_data_seal_sha256': sha(data / 'data_seal.json'),
        'new_fits': 0, 'raw_endpoints_unqualified': True,
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
