"""Paired held-block diagnostics on saved predictions, without new fitting."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
PREVIOUS = REPORTS/'2026_10_17_dsx01_iteration5'


def block_rows(times, held, nll_before, nll_after, before, after, seconds=20.):
    arrays = [np.asarray(a) for a in (times, held, nll_before, nll_after, before, after)]
    if any(a.ndim!=1 or a.shape!=arrays[0].shape for a in arrays):
        raise ValueError('Aligned one-dimensional held scores required')
    t, use, old_nll, new_nll, old, new = arrays
    if use.dtype!=bool or old.dtype!=bool or new.dtype!=bool or seconds<=0:
        raise ValueError('Boolean membership/assignment and positive block size required')
    blocks = np.floor(t/seconds).astype(int)
    rows = []
    for block in sorted(set(blocks[use])):
        m = use & (blocks==block)
        rows.append(dict(start_s=float(block*seconds), end_s=float((block+1)*seconds),
            observations=int(m.sum()), associated_before=int(old[m].sum()), associated_after=int(new[m].sum()),
            new=int(np.sum(m & new & ~old)), lost=int(np.sum(m & old & ~new)),
            nll_before=float(old_nll[m].sum()), nll_after=float(new_nll[m].sum()),
            nll_delta=float((new_nll[m]-old_nll[m]).sum())))
    return rows


def main():
    from leo.analysis.shared_scan_model import density
    from leo.contracts.regional_position import POSITION_SCORES
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    bindings = {}

    def bind(path):
        bindings[str(path.relative_to(REPORTS))] = 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
        return path

    context = REPORTS/'2026_10_16_dsx01_fast_association_losses/context-observations.jsonl'
    obs = [json.loads(line) for line in bind(context).read_text().splitlines()]
    obs = [r for r in obs if r['source_id']=='S03']
    measured = np.array([r['measured_cfo_hz'] for r in obs])
    times = np.array([r['time_s'] for r in obs])
    membership_path = REPORTS/'2026_10_16_dsx01_fast_association_losses/membership.csv'
    with bind(membership_path).open() as stream:
        membership = [r for r in csv.DictReader(stream) if r['source_id']=='S03']
    requested = np.array([r['observation_id'] in {m['observation_id'] for m in membership} for r in obs])

    def load(path):
        with np.load(bind(path)) as data:
            return dict(data)

    def score(state, key='prediction_hz'):
        np.testing.assert_allclose(state['times_s'], times, atol=1e-9, rtol=0)
        terms, details = density(measured, state[key], state['visibility_weight'],
            np.full(len(measured), 125.), state['detection_probability'], POSITION_SCORES['V16'])
        best = terms.responsibilities.argmax(axis=1)
        assigned = terms.responsibilities[np.arange(len(best)), best] > terms.clutter_probability
        if '_saved_associated' in state:
            np.testing.assert_array_equal(assigned, state['_saved_associated'])
        return assigned, details['row_nll']

    def load_age(family, arm):
        state = load(PREVIOUS/'age_timing'/f'blocked_predictions_{family}_{arm}.npz')
        evaluated = load(PREVIOUS/'age_timing'/f'blocked_eval_{family}_{arm}.npz')
        # Prediction exports omit timestamps; the corresponding score export
        # retains the same metadata ordering. Bind both and replay every label.
        np.testing.assert_array_equal(state['held_mask'], evaluated['held_mask'])
        return dict(state, times_s=evaluated['times_s'], _saved_associated=evaluated['associated'])

    rows, summary = [], []
    band_authority = json.loads(bind(PREVIOUS/'band_contrast_audit/results.json').read_text())['results']
    age_authority = json.loads(bind(PREVIOUS/'age_timing/blocked_evaluation.json').read_text())['rows']
    for arm in ['fitted-c', 'zero-c']:
        bands = load(PREVIOUS/'band_contrast_audit'/f'predictions-{arm}.npz')
        age_old = load_age('scalar2', arm)
        age_new = load_age('age', arm)
        comparisons = [('band-offset-profile', bands, 'baseline_prediction_hz', bands, 'profile_prediction_hz'),
                       ('age-relative-prior', age_old, 'prediction_hz', age_new, 'prediction_hz')]
        for method, old, old_key, new, new_key in comparisons:
            np.testing.assert_array_equal(old['held_mask'], new['held_mask'])
            held = old['held_mask']
            before, old_nll = score(old, old_key)
            after, new_nll = score(new, new_key)
            expected = ([r for r in band_authority if r['arm']==arm] if method=='band-offset-profile'
                        else [r for r in age_authority if r['arm']==arm])
            old_label, new_label = ('baseline', 'profile') if method=='band-offset-profile' else ('scalar2', 'age')
            field = 'method' if method=='band-offset-profile' else 'family'
            for label, flags, nll in [(old_label, before, old_nll), (new_label, after, new_nll)]:
                record = next(r for r in expected if r[field]==label)['held']
                assert int(flags[held].sum())==record['associated']
                np.testing.assert_allclose(nll[held].sum(), record['frequency_nll'], atol=1e-8, rtol=0)
            per_block = block_rows(times, held, old_nll, new_nll, before, after)
            assert sum(r['observations'] for r in per_block)==1909
            rows.extend(dict(method=method, arm=arm, **r) for r in per_block)
            summary.append(dict(method=method, arm=arm, held_observations=int(held.sum()),
                requested_held_observations=int((held & requested).sum()),
                requested_held_time_blocks=len(set(np.floor(times[held & requested]/20).astype(int))),
                blocks=len(per_block), blocks_with_better_nll=sum(r['nll_delta']<0 for r in per_block),
                held_nll_delta=float((new_nll[held]-old_nll[held]).sum()),
                assigned_delta=int(after[held].sum()-before[held].sum())))
    with (HERE/'blocks.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), constrained_layout=True, sharex=True)
    for axis, arm in zip(axes, ['fitted-c', 'zero-c']):
        for offset, method, label, color in [(-.18, 'band-offset-profile', 'Band constants profile', '#0072B2'),
                                           (.18, 'age-relative-prior', 'Age-aware timing prior', '#D55E00')]:
            use = [r for r in rows if r['arm']==arm and r['method']==method]
            axis.bar(np.arange(len(use))+offset, [r['nll_delta'] for r in use], width=.36, label=label, color=color)
        axis.axhline(0, color='black', linewidth=.8)
        axis.set(title=arm, ylabel='Paired held NLL change\nnegative is better')
        axis.grid(axis='y', alpha=.2)
    axes[0].legend()
    axes[1].set_xticks(range(7), ['20–40', '60–80', '100–120', '140–160', '180–200', '220–240', '260–280'])
    axes[1].set_xlabel('Excluded whole-probe temporal block (seconds)')
    fig.suptitle('S03 paired changes across seven excluded blocks\nEach method has its own matched baseline; these are different policies, not a common-baseline ranking')
    fig.savefig(HERE/'paired-blocks.png', dpi=160)
    plt.close(fig)
    result = dict(summary=summary, inputs=bindings, code_sha256='sha256:'+hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        qualification='Read-only paired diagnostics on already selected training-only predictions. Seven temporal blocks are dependent; no p-values or discovery false-positive claims. Requested80heldpoints occupyonly2blocks. Band profiles keep original physicalstate; timing continuations use the matched broaderresearchdomain disclosed in age_timing/blocked_domain_erratum.json. Bothc arms are conditional after fittedc publicdiscovery.')
    (HERE/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__=='__main__':
    main()
