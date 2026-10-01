"""Evaluate sealed coordinate choices; reference oracles are diagnostic only."""
import importlib.util
import json
from pathlib import Path
import numpy as np
from screen_seed_prefix import digest, sealed
from window_candidate_policy import rank_targets
from failure_composition_checks import process_ok

HERE = Path(__file__).resolve().parent
POLICIES = ('baseline', 'target_only', 'contained', 'target_oracle', 'contained_oracle')


def summarize(rows):
    result = {}
    for size in (1, 2, 4):
        local = [r for r in rows if r['size'] == size]
        policies = {}
        for policy in POLICIES:
            values = np.asarray([r['errors_m'][policy] for r in local])
            delta = values-np.asarray([r['errors_m']['baseline'] for r in local])
            policies[policy] = dict(n=len(values), median_m=float(np.median(values)),
                p90_m=float(np.quantile(values, .9)), maximum_m=float(values.max()),
                within_1km=int(np.sum(values <= 1000)), within_3km=int(np.sum(values <= 3000)),
                improves_over_1m=int(np.sum(delta < -1)), worsens_over_1m=int(np.sum(delta > 1)),
                within_1m=int(np.sum(np.abs(delta) <= 1)), median_paired_change_m=float(np.median(delta)))
        result[str(size)] = dict(planned=len(local), policies=policies)
    return result


def main():
    output = HERE/'window-candidate-evaluation-v1.json'
    if output.exists(): raise FileExistsError(output)
    inputs, sources, scored = {}, {}, []

    def read(path):
        value = sealed(path); inputs[str(path)] = digest(path); return value

    def verify(mapping):
        for name, expected in mapping.items(): assert digest(name) == expected, name

    manifest = read(HERE/'window-candidate-manifest-v1.json')
    for key in ('sources', 'inputs', 'frozen_sources_and_inputs'): verify(manifest[key])
    # Verify every precomputed decision before loading reference coordinates.
    for block in manifest['blocks']:
        name = block['block']; folder = HERE/'window-candidate-score-v1'
        record = read(folder/(name+'.json')); launch = read(folder/(name+'.launch.json'))
        assert process_ok(launch)
        verify(record['inputs']); verify(record['sources'])
        assert record['block'] == name and record['scans'] == block['scans']
        assert record['candidate_ids'] == [c['id'] for c in block['candidates']]
        assert record['maximum_score_implementation_difference'] < 1e-6
        assert record['decisions'] == rank_targets(block['candidates'], block['scans'],
                                                   record['score_matrix'], block['targets'])
        scored.append((block, record))
    assert len(scored) == 16 and sum(len(r['decisions']) for _, r in scored) == 112
    reference_path = HERE/'reference-admission-v1.json'
    reference = read(reference_path); verify(reference['source_sha256'])
    references = {r['unit']: r['reference_latlon'] for r in reference['rows']}
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == 'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec = importlib.util.spec_from_file_location('offline_geo', helper)
    geo = importlib.util.module_from_spec(spec); spec.loader.exec_module(geo)
    rows, block_details = [], []
    for block, record in scored:
        positions = [references[u] for u in block['scans']]
        assert all(p == positions[0] for p in positions)
        errors = [geo.distance_m(geo.latlon_from_enu(*c['point_km']), positions[0]) for c in block['candidates']]
        block_details.append(dict(block=block['block'], candidate_ids=record['candidate_ids'], candidate_errors_m=errors))
        for decision in record['decisions']:
            chosen = {p: decision[p] for p in ('baseline', 'target_only', 'contained')}
            chosen['target_oracle'] = min(decision['target_candidates'], key=lambda i: (errors[i], i))
            chosen['contained_oracle'] = min(decision['contained_candidates'], key=lambda i: (errors[i], i))
            assert all(chosen[p] in decision['contained_candidates'] for p in POLICIES)
            rows.append(dict(unit=decision['unit'], block=block['block'], dataset=block['dataset'], size=decision['size'],
                chosen_candidates={p: block['candidates'][i]['id'] for p, i in chosen.items()},
                errors_m={p: errors[i] for p, i in chosen.items()},
                acquisition_scores={p: decision['scores'][chosen[p]] for p in ('baseline', 'target_only', 'contained')},
                target_candidate_count=len(decision['target_candidates']),
                contained_candidate_count=len(decision['contained_candidates'])))
    summary = summarize(rows)
    assert [summary[str(s)]['planned'] for s in (1, 2, 4)] == [64, 32, 16]
    for path in (Path(__file__).resolve(), HERE/'window_candidate_policy.py', HERE/'failure_composition_checks.py', helper):
        sources[str(path)] = digest(path)
    result = dict(rows=rows, summary=summary,
        by_dataset={ds: summarize([r for r in rows if r['dataset'] == ds]) for ds in ('DS9', 'DS10', 'DS11')},
        block_details=block_details, inputs=inputs, sources=sources,
        maximum_score_implementation_difference=max(r['maximum_score_implementation_difference'] for _, r in scored),
        total_track_appearances=sum(sum(r['track_counts']) for _, r in scored),
        qualification='Retrospective coordinate-only diagnostic on112correlated targets. '
        'Candidates use only contained scans; source acceptance does not audit a transferred target fit. '
        'Baseline includes three96-iteration replacements. All score decisions sealed before reference evaluation. '
        'Oracles use reference errors and are diagnostic only; no end-to-end cost or fresh full-panel acceptance claim.')
    with output.open('x') as stream: json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), constrained_layout=True)
    styles = (('baseline', 'First-fit baseline', 'black', '-'),
              ('target_only', 'Target-only score', 'tab:blue', '-'),
              ('contained', 'Contained-window score', 'tab:orange', '-'),
              ('contained_oracle', 'Reference oracle', 'tab:green', '--'))
    for ax, size, title in zip(axes, (1, 2, 4), ('64 singles', '32 pairs', '16 quads')):
        local = [r for r in rows if r['size'] == size]
        for policy, label, color, style in styles:
            values = np.sort([r['errors_m'][policy] for r in local]); assert np.all(values > 0)
            ax.step(values, np.arange(1, len(values)+1)/len(values), where='post', label=label, color=color, ls=style)
        ax.set_xscale('log'); ax.set_xlabel('Coordinate reference error (m)'); ax.set_title(title)
        ax.set_ylim(0, 1.02); ax.grid(alpha=.2)
    axes[0].set_ylabel('Fraction of planned target windows'); axes[0].legend(fontsize=8, loc='upper left')
    fig.suptitle('Existing coordinates only: available candidates versus zero-nuisance score ranking')
    fig.savefig(output.with_suffix('.png'), dpi=160)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__': main()
