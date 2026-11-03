"""All archived identities, bounded timing grid, greedy joint subset selection.

Reference position fixed. Observed-positive-group likelihood, not held-out evidence.
No claim of globally optimal subset or exhaustive continuous timing search.
"""
from pathlib import Path
import argparse
import csv
import json
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / '2026_10_02_ds13_timing_em'
sys.path[:0] = [str(SOURCE), str(HERE.parent / '2026_10_02_multiscan_localization'),
               str(HERE.parent / '2026_10_02_localization_benchmark'),
               str(HERE.parent / '2026_10_02_coherent_localization')]
from all_visible_bank import load_expanded_scan
from compact_satellite_selection import competitive_addition_scores, timing_prior
from finite_set_likelihood import circular_residual, prepare_finite_set_likelihood
from finite_set_fit import snapshot_files
from position_profile_grid import run_profile
from prediction_plan import SharedPredictionPlan
from rf_calibration_diagnostic import CalibrationObjective, rf_features
from rough_smoke import serializable

SESSIONS = {'A': 'scan-fw-911c4e5db9243281', 'B': 'scan-fw-ffa1cc19d8d7c09f'}
MIN_SUPPORT = 10
OFFSETS = np.arange(-3., 3.001, .25)


def group_support(mask, groups):
    return np.array([len(np.unique(groups[mask[:, j]])) for j in range(mask.shape[1])])


def exclusive_pairs(gains):
    from scipy.optimize import linear_sum_assignment
    nr, ns = gains.shape
    costs = -np.column_stack([np.where(np.isfinite(gains), gains, -1e20), np.zeros((nr, nr))])
    rr, cc = linear_sum_assignment(costs)
    return [(int(r), int(c)) for r, c in zip(rr, cc) if c < ns and gains[r, c] > 0]


class ZeroRF(CalibrationObjective):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bounds[self.size:] = [(0., 0.)] * (len(self.initial) - self.size)


class Case:
    def __init__(self, label):
        self.label = label
        self.session = SESSIONS[label]
        self.path = SOURCE / 'pruned-position-profile-grid' / f'{self.session}.json'
        profile = json.loads(self.path.read_text())
        fit = next(p for p in profile['positions'] if p['label'] == 'truth')['best']
        self.data = load_expanded_scan(self.session)
        self.params = np.array(fit['parameters'])
        self.coeff = np.array(fit['rf_coefficient_hz_per_ghz'])
        self.selected = list(profile['satellite_indices'])
        self.original = self.selected.copy()
        self.pdet = profile['detection_probability']
        self.prepared = prepare_finite_set_likelihood(self.data.measured, self.data.group)
        _, self.features = rf_features(self.data.rf, self.data.receiver, False)
        self.penalty = .5 * np.log(len(self.prepared.group_values))
        self.log = []
        self.screens = []

    def predict(self, indices, params=None, coeff=None):
        p, v, _ = SharedPredictionPlan(self.data, indices).predict(self.params if params is None else params)
        shape = (len(self.data.times), len(indices))
        return p.reshape(shape) + (self.features @ (self.coeff if coeff is None else coeff))[:, None], v.reshape(shape)

    def evaluate(self, indices=None, params=None, coeff=None):
        indices = self.selected if indices is None else indices
        params = self.params if params is None else params
        pred, vis = self.predict(indices, params, coeff)
        result = self.prepared.evaluate(pred, vis, sigma_hz=200., detection_probability=self.pdet, clutter_rate=2.,
                                        return_gradient=False, return_precision=False)
        objective = -result['total_log_likelihood'] + timing_prior(params[6 + np.array(indices)]) + self.penalty * len(indices)
        return float(objective), result, pred, vis

    def assignments(self, indices=None, params=None, coeff=None):
        indices = self.selected if indices is None else indices
        pred, vis = self.predict(indices, params, coeff)
        residual = circular_residual(self.data.measured[:, None], pred, self.prepared.alias_hz)
        gain = np.log(self.pdet / (1-self.pdet)) - np.log(200*np.sqrt(2*np.pi)) - .5*(residual/200)**2 - np.log(2/self.prepared.alias_hz)
        gain[~vis | (np.abs(residual)>1000)] = -np.inf
        # The likelihood's exact-alias clusters define stable representatives.
        representatives = np.array([int(rows[0]) for rows in self.prepared.clusters])
        records = []
        for group in np.unique(self.data.group[representatives]):
            rows = representatives[self.data.group[representatives] == group]
            for r, c in exclusive_pairs(gain[rows]):
                row = int(rows[r])
                records.append(dict(scan=self.label, row_index=row, group=int(group),
                                    catalog_number=int(self.data.numbers[indices[c]]), receiver=int(self.data.receiver[row]),
                                    channel=int(self.data.channel[row]), time_s=float(self.data.times[row]),
                                    residual_native_hz=float(residual[row,c]),
                                    residual_hz=float(residual[row,c]*11.085e9/self.data.rf[row])))
        counts = {i: sum(r['catalog_number'] == int(self.data.numbers[i]) for r in records) for i in indices}
        return records, counts

    def fit(self, indices, params, coeff, zero=False):
        current = None
        attempts = []
        for _ in range(4):
            fit = run_profile(self.data, params, np.array(indices), [0.] if zero else coeff,
                              params[:2], probability_override=self.pdet, start_vector=current,
                              budget_s=8., objective_factory=ZeroRF if zero else CalibrationObjective)
            attempts.append({k: fit[k] for k in ['success', 'status', 'objective', 'projected_nuisance_gradient_inf_norm']})
            current = fit['vector']
            if fit['success']:
                break
        return fit, attempts

    def refit(self):
        fit, attempts = self.fit(self.selected, self.params, self.coeff)
        self.params = np.array(fit['parameters'])
        self.coeff = np.array(fit['rf_coefficient_hz_per_ghz'])
        self.log.append(dict(action='refit', attempts=attempts))

    def screen(self):
        base = self.evaluate()[1]
        common = float(np.mean(self.params[6 + np.array(self.selected)]))
        n = len(self.data.numbers)
        best = np.full(n, -np.inf)
        shifts = np.full(n, common)
        supports = np.zeros(n, int)
        cache_p = np.empty((len(self.data.times), n))
        cache_v = np.empty(cache_p.shape, bool)
        # Every identity, including incumbents, is sampled on every grid point.
        for start in range(0, n, 32):
            ids = np.arange(start, min(start+32, n))
            for offset in OFFSETS:
                params = self.params.copy()
                params[6 + ids] = common + offset
                pred, vis = self.predict(ids, params)
                residual = circular_residual(self.data.measured[:,None], pred, self.prepared.alias_hz)
                peak_gain = np.log(self.pdet/(1-self.pdet)) - np.log(200*np.sqrt(2*np.pi)) - .5*(residual/200)**2 - np.log(2/self.prepared.alias_hz)
                support = group_support(vis & (peak_gain > 0), self.data.group)
                scores = competitive_addition_scores(self.prepared, base, pred, vis, self.pdet)['log_likelihood_change']
                for col, i in enumerate(ids):
                    score = float(scores[col]) - .5*offset**2
                    if support[col] >= MIN_SUPPORT and score > best[i]:
                        best[i], shifts[i], supports[i] = score, common+offset, support[col]
                        cache_p[:,i], cache_v[:,i] = pred[:,col], vis[:,col]
            print(self.label, 'screen', start+len(ids), '/', n, flush=True)
        receipt = dict(common_timing_s=common, offsets_s=OFFSETS, evaluated_identities=n,
                       candidates=[dict(catalog_number=int(self.data.numbers[i]), satellite_index=i,
                                        support=int(supports[i]), score=float(best[i]) if np.isfinite(best[i]) else None,
                                        shift_s=float(shifts[i])) for i in range(n)])
        self.screens.append(receipt)
        remaining = [i for i in range(n) if np.isfinite(best[i]) and i not in self.selected]
        # Recompute competition after each addition; never admit independent scores wholesale.
        while remaining:
            old, base, _, _ = self.evaluate()
            scores = competitive_addition_scores(self.prepared, base, cache_p[:,remaining], cache_v[:,remaining], self.pdet)['log_likelihood_change']
            oldprior = timing_prior(self.params[6+np.array(self.selected)])
            gain = [float(s)-self.penalty-timing_prior(np.r_[self.params[6+np.array(self.selected)], shifts[i]])+oldprior for i,s in zip(remaining,scores)]
            j = int(np.argmax(gain))
            if gain[j] <= 0:
                break
            i = remaining.pop(j)
            trial = self.params.copy()
            trial[6+i] = shifts[i]
            _, counts = self.assignments(self.selected+[i], trial)
            if counts[i] < MIN_SUPPORT:
                continue
            self.params = trial
            self.selected.append(i)
            self.log.append(dict(action='add', catalog_number=int(self.data.numbers[i]), penalized_gain=gain[j], assigned_groups=counts[i]))
            print(self.label, self.log[-1], flush=True)

    def prune(self):
        while len(self.selected) > 1:
            old = self.evaluate()[0]
            _, counts = self.assignments()
            weak = [i for i in self.selected if counts[i] < MIN_SUPPORT]
            if weak:
                remove = min(weak, key=counts.get)
                reason = 'under_10_assigned_groups'
            else:
                scores = [(self.evaluate([j for j in self.selected if j != i])[0], i) for i in self.selected]
                value, remove = min(scores)
                if value >= old:
                    break
                reason = 'penalized_score_improves'
            self.selected.remove(remove)
            self.log.append(dict(action='drop', catalog_number=int(self.data.numbers[remove]), reason=reason))
            self.refit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scan', choices=list(SESSIONS), required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    started = time.monotonic()
    case = Case(args.scan)
    output = HERE / 'exhaustive-subset'
    output.mkdir(exist_ok=True)
    baseline_objective = case.evaluate()[0]
    baseline_records, _ = case.assignments()
    previous_elapsed = 0.
    if args.resume:
        previous = json.loads((output/f'{args.scan}-receipt.json').read_text())
        fit = previous['arms']['fitted-c']['fit']
        case.params = np.array(fit['parameters'])
        case.coeff = np.array(fit['rf_coefficient_hz_per_ghz'])
        case.selected = [int(np.flatnonzero(case.data.numbers == number)[0]) for number in previous['catalog_numbers']]
        case.log, case.screens = previous['log'], previous['screens']
        previous_elapsed = previous['elapsed_s']
    else:
        case.refit()
    stable = False
    for _ in range(len(case.screens), 5):
        before = set(case.selected)
        case.screen()
        case.refit()
        case.prune()
        if set(case.selected) == before:
            stable = True
            break
    # Matched RF ablation: same subset, observations, initial nuisance values and solve budgets.
    start_params, start_coeff = case.params.copy(), case.coeff.copy()
    arms = {}
    for arm, zero in [('fitted-c', False), ('zero-c', True)]:
        fit, attempts = case.fit(case.selected, start_params, start_coeff, zero)
        params, coeff = np.array(fit['parameters']), np.array(fit['rf_coefficient_hz_per_ghz'])
        records, counts = case.assignments(params=params, coeff=coeff)
        objective = case.evaluate(params=params, coeff=coeff)[0]
        with (output/f'{args.scan}-{arm}-assignments.csv').open('w') as f:
            writer = csv.DictWriter(f, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
        arms[arm] = dict(fit=fit, attempts=attempts, penalized_objective=objective, assigned_peaks=len(records),
                         rms_normalized_hz=float(np.sqrt(np.mean([r['residual_hz']**2 for r in records]))),
                         support={int(case.data.numbers[i]): count for i,count in counts.items()})
    if min(arms['fitted-c']['support'].values()) < MIN_SUPPORT:
        raise RuntimeError('Final fitted-c subset violates support floor')
    receipt = dict(scope=__doc__, scan=args.scan, session=case.session, minimum_assigned_groups=MIN_SUPPORT,
                   gate='Positive MAP gain, sigma=200 native Hz, clutter=2, alias-aware; one peak/satellite/group.',
                   timing_search='Full-bank passes until no subset change (at most five), mean selected timing +/-3s in 0.25s steps; continuous joint refits.',
                   selection_stable=stable,
                   baseline=dict(penalized_objective=baseline_objective, assigned_peaks=len(baseline_records),
                                 catalog_numbers=case.data.numbers[case.original]),
                   catalog_numbers=case.data.numbers[case.selected], log=case.log, screens=case.screens,
                   arms=arms, elapsed_s=previous_elapsed+time.monotonic()-started,
                   source_hashes=snapshot_files([__file__, case.path, SOURCE/'all-visible-bank'/case.session/'expanded.npz']))
    (output/f'{args.scan}-receipt.json').write_text(json.dumps(serializable(receipt), indent=2))
    print(args.scan, 'DONE', serializable({k: {x:v[x] for x in ['assigned_peaks','rms_normalized_hz','support']} for k,v in arms.items()}), flush=True)


if __name__ == '__main__':
    main()
