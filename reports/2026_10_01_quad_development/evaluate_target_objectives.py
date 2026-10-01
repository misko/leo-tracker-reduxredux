"""Evaluate sealed same-target objective choices against identical candidate pools."""
import json
from pathlib import Path
import numpy as np
from screen_seed_prefix import digest, sealed
from window_candidate_policy import choose

HERE = Path(__file__).resolve().parent
POLICIES = ('baseline', 'acquisition', 'full_objective', 'oracle')


def stats(rows):
    result = {}
    for size in (1, 2, 4):
        local = [r for r in rows if r['size'] == size]; arms = {}
        for policy in POLICIES:
            errors = np.asarray([r['errors_m'][policy] for r in local])
            delta = errors-np.asarray([r['errors_m']['baseline'] for r in local])
            arms[policy] = dict(n=len(local), median_m=float(np.median(errors)), p90_m=float(np.quantile(errors, .9)),
                maximum_m=float(errors.max()), within_1km=int(np.sum(errors <= 1000)), within_3km=int(np.sum(errors <= 3000)),
                improves_over_1m=int(np.sum(delta < -1)), worsens_over_1m=int(np.sum(delta > 1)),
                within_1m=int(np.sum(np.abs(delta) <= 1)), median_paired_change_m=float(np.median(delta)))
        result[str(size)] = arms
    return result


def main():
    output = HERE/'target-objective-evaluation-v1.json'
    if output.exists(): raise FileExistsError(output)
    inputs = {}

    def read(path):
        value = sealed(path); inputs[str(path)] = digest(path); return value

    def verify(value):
        for key in ('sources', 'inputs'):
            for name, expected in value[key].items(): assert digest(name) == expected, name

    decisions = read(HERE/'target-objective-decisions-v1.json'); verify(decisions)
    assert len(decisions['rows']) == 112 and len({r['unit'] for r in decisions['rows']}) == 112
    for row in decisions['rows']:
        ids = row['eligible']; objectives = [row['objectives'][i] for i in ids]
        expected = choose(-np.asarray(objectives), list(range(len(ids))), ids.index(row['baseline']))
        assert row['selected'] == ids[expected]
    # Reference-derived errors enter only after every choice has been sealed and verified.
    prior = read(HERE/'window-candidate-evaluation-v1.json'); verify(prior)
    old_rows = {r['unit']: r for r in prior['rows']}
    error_maps = {r['block']: dict(zip(r['candidate_ids'], r['candidate_errors_m'])) for r in prior['block_details']}
    rows = []
    for d in decisions['rows']:
        old = old_rows[d['unit']]
        assert d['baseline'] == old['chosen_candidates']['baseline']
        chosen = dict(baseline=d['baseline'], acquisition=old['chosen_candidates']['target_only'],
                      full_objective=d['selected'], oracle=old['chosen_candidates']['target_oracle'])
        assert all(c in d['eligible'] for c in chosen.values())
        errors = {p: error_maps[d['block']][c] for p, c in chosen.items()}
        assert errors['baseline'] == old['errors_m']['baseline']
        rows.append(dict(unit=d['unit'], block=d['block'], dataset=d['dataset'], size=d['size'],
                         chosen=chosen, errors_m=errors, objective_improvement=d['objective_improvement']))
    summary = stats(rows)
    assert [summary[str(s)]['baseline']['n'] for s in (1, 2, 4)] == [64, 32, 16]
    sources = {str(p): digest(p) for p in (Path(__file__).resolve(), HERE/'window_candidate_policy.py')}
    result = dict(rows=rows, summary=summary,
        by_dataset={ds: stats([r for r in rows if r['dataset'] == ds]) for ds in ('DS9', 'DS10', 'DS11')},
        inputs=inputs, sources=sources,
        qualification='Separate post-result comparison on the same target-only accepted leaders. '
        'Choices sealed before reference-error evaluation. Existing fit costs excluded; no fresh inference or runtime claim. '
        'Full-objective ranking changes nuisance and association treatment together; oracle is diagnostic only.')
    with output.open('x') as stream: json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    for j, (policy, label, color) in enumerate((
        ('baseline', 'First-fit baseline', 'gray'), ('acquisition', 'Acquisition score', 'tab:blue'),
        ('full_objective', 'Full joint objective', 'tab:orange'), ('oracle', 'Reference oracle', 'tab:green'))):
        for ax, metric in zip(axes, ('median_m', 'p90_m')):
            ax.bar(np.arange(3)+(j-1.5)*.2, [summary[str(s)][policy][metric] for s in (1, 2, 4)],
                   .2, label=label, color=color, hatch='//' if policy == 'oracle' else None)
    axes[0].set_ylabel('Median coordinate error (m)'); axes[1].set_ylabel('90th percentile error (m)')
    axes[0].legend(fontsize=8, loc='upper right')
    for ax in axes:
        ax.set_xticks(np.arange(3), ['64 singles', '32 pairs', '16 quads']); ax.grid(axis='y', alpha=.2)
    fig.suptitle('Same target-only candidates: acquisition score versus full fitted objective')
    fig.savefig(output.with_suffix('.png'), dpi=160)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__': main()
