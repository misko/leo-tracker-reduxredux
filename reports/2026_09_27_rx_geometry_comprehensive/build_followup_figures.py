"""Render follow-up figures from bundled receipts; no original corpus required."""
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE / 'followup_sources/2026_09_27_rx_disjoint_confirmation'
OUT = HERE / 'followup_figures'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    plt.rcParams.update({'font.size': 11, 'svg.hashsalt': 'rx-followup-20260927'})
    OUT.mkdir(exist_ok=True)
    files = []

    def save(fig, name):
        for ext in ('png', 'svg'):
            path = OUT / f'{name}.{ext}'
            fig.savefig(path, dpi=170, bbox_inches='tight', metadata={'Date': None} if ext == 'svg' else None)
            if ext == 'svg':
                path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines()) + '\n')
            files.append(path)
        plt.close(fig)

    scores = json.loads((BASE / 'summary-v2.json').read_text())
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    for ax, direction in zip(axes, ('X_to_Y', 'Y_to_X')):
        result = scores['results'][direction]
        sessions = list(result['normal']['per_recording'])
        x = np.arange(len(sessions))
        for shift, model, color in ((-.18, 'normal', '#2677ad'), (.18, 'reversed', '#c66c27')):
            ax.bar(x + shift, [result[model]['per_recording'][sid] * 1000 for sid in sessions],
                   width=.34, color=color, label=model.capitalize())
        ax.axhline(0, color='#333333', linewidth=.8)
        ax.set_xticks(x, [sid.removeprefix('scan-fw-')[:4] for sid in sessions])
        ax.set_xlabel('Recording prefix (not independent passes)')
        ax.set_title(f'{direction.replace("_to_", " → ")}: {result["normal"]["recordings_improving"]}/4 normal gains positive')
        ax.grid(axis='y', alpha=.2)
    axes[0].set_ylabel('Baseline NLL − RX NLL (×10⁻³); positive better')
    axes[1].legend(frameon=False)
    fig.suptitle('Frozen disjoint test: forward consistency gate fails (requires ≥3/4)', fontsize=14)
    fig.tight_layout()
    save(fig, '09_disjoint_gains')

    audit = json.loads((BASE / 'source-audit-summary.json').read_text())
    cross = audit['results']['scan-fw-8f4f960d9db67798']['cross_channel']
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    t0 = min(p['utc_ns'] for key in ('left_to_right', 'right_to_left') for p in cross[key]['pairs'])
    for ax, key, title in zip(axes, ('left_to_right', 'right_to_left'),
                              ('2603 − interpolated 6b6a', '6b6a − interpolated 2603')):
        row = cross[key]
        ax.scatter([(p['utc_ns'] - t0) / 1e9 for p in row['pairs']],
                   [p['difference_hz'] - row['constant_difference_hz'] for p in row['pairs']],
                   color='#2677ad', s=35)
        ax.axhline(0, color='#333333', linewidth=.8)
        ax.set_title(f'{title}\n{row["points"]} points; RMS {row["difference_rms_after_constant_hz"]:.2f} Hz')
        ax.set_xlabel('Seconds since first supported comparison')
        ax.grid(alpha=.2)
    axes[0].set_ylabel('Frequency difference after one constant (Hz)')
    fig.suptitle('Same RX, different RF channels: similar observed trajectory shape', fontsize=14)
    fig.text(.5, -.02, 'Posthoc interpolation; brackets ≤1.5 s; no extrapolation. Not identity proof or a precision bound.', ha='center')
    fig.tight_layout()
    save(fig, '10_cross_channel_agreement')
    manifest = {'generator_sha256': digest(Path(__file__)),
                'input_sha256': {str(path.relative_to(HERE)): digest(path) for path in
                                 (BASE / 'summary-v2.json', BASE / 'source-audit-summary.json')},
                'figure_sha256': {str(path.relative_to(HERE)): digest(path) for path in files}}
    (HERE / 'followup_figure_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
