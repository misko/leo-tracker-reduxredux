"""Descriptive saved-state support audit; window membership is NEVER a fit input."""

import csv
import hashlib
import importlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OLD = ROOT/'reports/2026_10_16_dsx01_models'
PREVIOUS = ROOT/'reports/2026_10_16_dsx01_iteration2'
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(OLD))
sys.path.insert(0, str(PREVIOUS))
bank_expansion = importlib.import_module('bank_expansion')
common = importlib.import_module('common')


def quantiles(values):
    values = np.asarray(values)
    return np.quantile(values, [0, .1, .5, .9, 1]).tolist() if len(values) else None


def run(source_id):
    begun = time.monotonic()
    context = common.load_context(source_id)
    selected = json.loads((PREVIOUS/f'candidate_screen_{source_id}.json').read_text())
    regional = bank_expansion.regional_bank(context)
    expanded, transport = bank_expansion.expandable_context(context, selected['selected_ids'],
                                                            regional=regional)
    states = {}
    paths = dict(original=OLD/'results'/f'{source_id}-full-fitted-c-original.json',
                 fixed=PREVIOUS/'results'/f'{source_id}-fitted-c-profile.json',
                 expanded=PREVIOUS/'expanded-results'/f'{source_id}-fitted-c-profile.json')
    for name, path in paths.items():
        record = json.loads(path.read_text())
        ctx = expanded if name == 'expanded' else context
        v, n = np.array(record['vector']), np.array(record['nuisance'])
        e, detail = ctx.model.evaluate_details(v, n)
        terms = e[3]
        best = terms.responsibilities.argmax(axis=1)
        rows = np.arange(len(best))
        assigned = terms.responsibilities[rows, best] > terms.clutter_probability
        saved = np.load(path.with_suffix('.npz'))
        np.testing.assert_array_equal(assigned, saved['associated'])
        np.testing.assert_array_equal(ctx.bank.numbers[best], saved['satellite_number'])
        np.testing.assert_allclose(terms.residual_hz[rows, best], saved['residual_hz'], atol=1e-8)
        states[name] = dict(vector=v, nuisance=n, terms=terms, detail=detail, best=best,
            assigned=assigned, numbers=ctx.bank.numbers, correction=ctx.model.original.correction(
                v, n[:ctx.model.clock_count]), tau=v[7]+ctx.model.basis@v[8:],
            objective=float(e[0]), nll=float(terms.nll),
            prior=float(e[0]-terms.nll),
            source=dict(path=str(path),
                        sha256='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()))
    obs = context.observations
    output = dict(source_id=source_id, objective_evaluations=3,
        baseline_loader_replay_objectives=2, localization_fits=0, transitions={},
        states={name: {k: state[k] for k in ('objective', 'nll', 'prior', 'source')}
                for name, state in states.items()})
    for before, after in (('original', 'fixed'), ('original', 'expanded'), ('fixed', 'expanded')):
        a, b = states[before], states[after]
        lost = a['assigned'] & ~b['assigned']
        new = ~a['assigned'] & b['assigned']
        lookup = {int(number): i for i, number in enumerate(b['numbers'])}
        indices = np.array([lookup[int(number)] for number in a['numbers'][a['best']]])
        rows = np.arange(len(indices))
        ratio = b['terms'].responsibilities.max(axis=1)/b['terms'].clutter_probability
        previous_residual = a['terms'].residual_hz[rows, a['best']]
        new_residual_same = b['terms'].residual_hz[rows, indices]
        delta_correction = b['correction']-a['correction']
        from leo.analysis.regional_position_score import circular
        delta_orbit = circular(previous_residual-new_residual_same-delta_correction)
        summary = dict(population=len(lost), before_associated=int(a['assigned'].sum()),
            after_associated=int(b['assigned'].sum()), lost=int(lost.sum()), new=int(new.sum()),
            lost_posterior_ratio_quantiles=quantiles(ratio[lost]),
            lost_near_threshold_08_to_1=int(np.sum(lost & (ratio >= .8))),
            lost_below_half_threshold=int(np.sum(lost & (ratio < .5))),
            lost_old_candidate_residual_abs_quantiles=quantiles(abs(previous_residual[lost])),
            lost_new_same_candidate_residual_abs_quantiles=quantiles(abs(new_residual_same[lost])),
            lost_correction_delta_abs_quantiles=quantiles(abs(delta_correction[lost])),
            lost_orbit_geo_and_timing_delta_abs_quantiles=quantiles(abs(delta_orbit[lost])),
            lost_old_candidate_invisible=int(np.sum(lost &
                (b['detail']['visibility_weight'][rows, indices] == 0))),
            old_candidates_removed=0, candidates=[])
        for number in sorted(set(map(int, a['numbers'][a['best'][lost]]))):
            mask = lost & (a['numbers'][a['best']] == number)
            i, j = list(a['numbers']).index(number), lookup[number]
            summary['candidates'].append(dict(number=number, lost=int(mask.sum()),
                total_before_associated=int(np.sum(a['assigned'] &
                                                  (a['numbers'][a['best']] == number))),
                tau_before=float(a['tau'][i]), tau_after=float(b['tau'][j]),
                q_before=float(a['detail']['detection_probability'][i]),
                q_after=float(b['detail']['detection_probability'][j]),
                ratio_quantiles=quantiles(ratio[mask]),
                residual_before_abs_quantiles=quantiles(abs(previous_residual[mask])),
                residual_after_same_candidate_abs_quantiles=quantiles(abs(new_residual_same[mask]))))
        membership = {}
        membership_path = ROOT/'reports/2026_10_16_dsx01_fast_association_losses/membership.csv'
        with membership_path.open() as stream:
            for row in csv.DictReader(stream):
                if row['source_id'] == source_id:
                    membership.setdefault(row['region_id'], set()).add(row['observation_id'])
        summary['windows'] = {}
        for name, ids in membership.items():
            keep = np.array([wid in ids for wid in obs.window_ids])
            summary['windows'][name] = dict(count=int(keep.sum()),
                before=int(np.sum(keep & a['assigned'])), after=int(np.sum(keep & b['assigned'])),
                lost=int(np.sum(keep & lost)), new=int(np.sum(keep & new)),
                lost_ratio_quantiles=quantiles(ratio[keep & lost]),
                lost_old_candidate_new_residual_abs_quantiles=quantiles(
                    abs(new_residual_same[keep & lost])))
        output['transitions'][before+'-to-'+after] = summary
    output['elapsed_seconds'] = time.monotonic()-begun
    common.save_json(HERE/f'audit_{source_id}.json', output)
    print(source_id, {k: {n: s[n] for n in ('lost', 'new', 'lost_near_threshold_08_to_1',
        'lost_below_half_threshold', 'lost_old_candidate_invisible')}
        for k, s in output['transitions'].items()}, flush=True)
    return output


if __name__ == '__main__':
    for label in sys.argv[1:]:
        run(label)
