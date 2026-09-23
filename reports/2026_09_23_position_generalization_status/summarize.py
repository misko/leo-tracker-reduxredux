"""Compare sealed timing/drift experiments on identical validation windows."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
SOURCES = [
    '2026_09_23_fractional_timing_position',
    '2026_09_23_shared_bracket_position',
    '2026_09_23_receiver_drift_position',
]


def main():
    rows, bindings, support = [], {}, {}
    authorities, seeds = [], {}
    for source in SOURCES:
        path = HERE.parent / source / 'results.json'
        raw = path.read_bytes()
        result = json.loads(raw)
        bindings[source] = hashlib.sha256(raw).hexdigest()
        recorded = result.get('bindings', {})
        authorities.append(tuple(str(value).removeprefix('sha256:') for value in (
            result.get('inventory_sha256', recorded.get('inventory')),
            result.get('split_manifest_sha256', recorded.get('split')),
        )))
        for window in result['windows']:
            key = window['window_id']
            sessions = window['session_ids']
            if key in support and support[key] != sessions:
                raise ValueError('validation session support differs')
            if key in seeds and seeds[key] != window['seeds']:
                raise ValueError('published starting seeds differ')
            seeds[key] = window['seeds']
            support[key] = sessions
            for arm in window['arms']:
                selected = arm['selected']
                rows.append({
                    'source': source, 'window_id': key, 'method': arm['method'],
                    'session_ids': sessions, 'error_km': selected['reference_error_km'],
                    'reserved_capped800_rmse_hz': selected['reserved_capped800_rmse_hz'],
                    'latitude_deg': selected['latitude_deg'],
                    'longitude_deg': selected['longitude_deg'],
                })
    if len(support) != 4:
        raise ValueError('expected two full groups and their nested singletons')
    if len(set(authorities)) != 1 or 'None' in authorities[0]:
        raise ValueError('frozen inventory or partition authorities differ')
    result = {'scope': 'Retrospective validation; conditional candidate pools and published seeds',
              'new_inference_run': False, 'sources_sha256': bindings, 'rows': rows,
              'worker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (HERE / 'comparison.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    methods = list(dict.fromkeys(row['method'] for row in rows))
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharey=True)
    for ax, (window, sessions) in zip(axes.flat, support.items(), strict=True):
        selected = {row['method']: row for row in rows if row['window_id'] == window}
        values = [selected[method]['error_km'] for method in methods]
        ax.scatter(range(len(methods)), values, color='tab:blue')
        ax.axhline(.3, color='tab:red', linestyle='--', label='300 m target')
        ax.set_yscale('log')
        ax.set_title(f'{window}\n{len(sessions)} scans')
        ax.set_xticks(range(len(methods)), methods, rotation=65, ha='right', fontsize=8)
        ax.set_ylabel('Reference position error (km; log scale)')
        ax.grid(axis='y', alpha=.2)
        ax.legend(fontsize=8)
    fig.suptitle('Same validation windows: timing and receiver-drift models\n'
                 'Singletons are nested views, not independent replicates')
    fig.tight_layout()
    fig.savefig(HERE / 'comparison.png', dpi=140)
    plt.close(fig)


if __name__ == '__main__':
    main()
