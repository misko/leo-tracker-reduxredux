"""Read-only posthoc decomposition of a frozen cold prediction failure.

Original full-recording winner identities are descriptive oracle labels, never
truth or inference inputs. Nothing here fits, selects or changes a prediction.
"""
import csv
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
COLD = REPORTS/'2026_10_17_dsx01_iteration4/cold_pipeline/S03-early_to_late'


def quantiles(values):
    values = np.asarray(values, float)
    return dict(zip(['minimum', 'q25', 'median', 'q75', 'maximum'],
        map(float, np.quantile(values, [0., .25, .5, .75, 1.])))) if len(values) else None


def partition(original_assigned, original_number, predicted_assigned, selected_numbers, mask):
    use = np.asarray(mask, bool) & original_assigned
    available = np.isin(original_number, selected_numbers)
    lost = use & ~predicted_assigned
    return dict(original_assigned=int(use.sum()), original_winner_present=int((use & available).sum()),
        original_winner_absent=int((use & ~available).sum()), lost_original=int(lost.sum()),
        lost_original_winner_present=int((lost & available).sum()),
        lost_original_winner_absent=int((lost & ~available).sum()))


def projection_fraction(target, nuisance):
    """Unregularized local linear dependence, not posterior uncertainty."""
    target, nuisance = np.asarray(target, float), np.asarray(nuisance, float)
    predicted = nuisance@np.linalg.lstsq(nuisance, target, rcond=1e-10)[0]
    norm = float(target@target)
    return float(np.clip(1.-np.sum((target-predicted)**2)/norm, 0., 1.)) if norm else None


def main():
    sys.path.insert(0, str(REPORTS/'2026_10_16_dsx01_models'))
    sys.path.insert(0, str(REPORTS/'2026_10_17_dsx01_iteration4/cold_pipeline'))
    import common
    from evaluate import extend_bank
    from leo.cli.shared_fast_position import load_input
    from leo.application.shared_fast_position import prepare_views
    from leo.application.shared_orbit_replay import selected_model
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.analysis.hard60_score import predict_orbits
    from leo.analysis.regional_position_score import circular
    from leo.contracts.regional_position import RegionalPrior
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets

    frozen = dict(np.load(COLD/'held-predictions.npz'))
    cold_points = dict(np.load(COLD/'evaluation.npz'))
    cold_report = json.loads((COLD/'evaluation.json').read_text())
    terminal = json.loads((COLD/'output/terminal.json').read_text())
    derivation = json.loads((COLD/'derivation.json').read_text())
    originals_path = REPORTS/'2026_10_16_dsx01_models/results/S03-full-fitted-c-original.npz'
    originals = dict(np.load(originals_path))
    ctx = common.load_context('S03')
    obs = ctx.observations
    np.testing.assert_array_equal(obs.times_s, frozen['times_s'])
    ev, details, best, assigned, original_residual = common.point_state(ctx.model, ctx.vector, ctx.nuisance)
    np.testing.assert_array_equal(assigned, originals['associated'])
    np.testing.assert_array_equal(original_residual, originals['residual_hz'])
    numbers = frozen['number']
    present = np.isin(ctx.bank.numbers, numbers)
    full_prediction = obs.measured_hz[:, None]-ev[3].residual_hz
    # Classifier-only subset oracle. The common posterior denominator cancels
    # in signal>clutter, so keep original full-model q without renormalizing it.
    # A subset no longer has the full-bank q budget and is not a scored model.
    restricted_assigned = ev[3].responsibilities[:, present].max(axis=1) > ev[3].clutter_probability
    original_correction = ctx.model.original.correction(ctx.vector, ctx.nuisance[:ctx.model.base_nuisance_count])
    correction_delta = frozen['correction_hz']-original_correction
    cold_lookup = {int(number):i for i, number in enumerate(numbers)}
    original_number = ctx.bank.numbers[best]
    covered = np.isin(original_number, numbers)
    rows = np.flatnonzero(covered)
    kk = np.array([cold_lookup[int(number)] for number in original_number[rows]])
    total_delta = np.full(len(obs.times_s), np.nan)
    total_delta[rows] = circular(frozen['prediction_hz'][rows, kk]-full_prediction[rows, best[rows]])
    orbit_delta = circular(total_delta-correction_delta)
    same_candidate_residual = np.full(len(rows), np.nan)
    same_candidate_residual[:] = circular(obs.measured_hz[rows]-frozen['prediction_hz'][rows, kk])
    candidate_residual = np.full(len(obs.times_s), np.nan)
    candidate_residual[rows] = same_candidate_residual
    scopes = {}
    for label, mask in [('train', frozen['train_mask']), ('held', frozen['held_mask'])]:
        use = mask & assigned & covered
        scopes[label] = dict(**partition(assigned, original_number, cold_points['associated'], numbers, mask),
            original_oracle_restricted_bank_assigned=int((mask & restricted_assigned).sum()),
            cold_assigned=int((mask & cold_points['associated']).sum()),
            same_original_winner_residual_abs_hz=quantiles(abs(candidate_residual[use])),
            same_original_winner_prediction_delta_hz=quantiles(total_delta[use]),
            same_original_winner_orbit_delta_hz=quantiles(orbit_delta[use]),
            same_original_winner_calibration_delta_hz=quantiles(correction_delta[use]),
            same_original_winner_within_375_hz=int(np.sum(abs(candidate_residual[use]) <= 375.)))
    calibration = []
    for rx in np.unique(obs.receiver):
        for high in [False, True]:
            lane = (obs.receiver == rx) & ((obs.channel >= 5) == high)
            for label, mask in [('train', frozen['train_mask']), ('held', frozen['held_mask'])]:
                use = lane & mask
                calibration.append(dict(receiver=int(rx), high=high, scope=label,
                    rows=int(use.sum()), time_s=quantiles(obs.times_s[use]),
                    cold_correction_hz=quantiles(frozen['correction_hz'][use]),
                    original_correction_hz=quantiles(original_correction[use]),
                    cold_minus_original_hz=quantiles(correction_delta[use])))

    # Replay the strict TRAIN endpoint using public preparation/selection APIs.
    source = load_input(json.loads((COLD/'training-input.json').read_text()))
    prepared, nodes = prepare_views(source)
    prior = RegionalPrior(**terminal['provenance']['prior'])
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    snapshot = next(s for s in archive.list_snapshots() if s.digest == derivation['causal_tle']['sha256']
        and s.provider == derivation['causal_tle']['provider']
        and s.collected_utc_ns == derivation['causal_tle']['collected_utc_ns'])
    filtered, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(filtered)
    bank, _ = extend_bank(catalogue, list(map(int, numbers)), prepared['all'].start_utc_ns,
        prepared['all'].observations, prior)
    stages = {p.stem:json.loads(p.read_text()) for p in (COLD/'output/stages').glob('*.json')}
    cold_model, fit, audit = selected_model(prepared, bank, prior, nodes, terminal, stages)
    assert audit['accepted']
    v, n = np.asarray(fit['vector']), np.asarray(fit['nuisance'])
    e, _, identity, cold_assigned, _ = common.point_state(cold_model, v, n)
    train_obs = cold_model.observations
    tau = v[7]+cold_model.basis@v[8:]
    _, _, spatial, timing = predict_orbits(bank, train_obs, prior, v[:2], tau)
    use = np.flatnonzero(cold_assigned)
    physical = spatial[use, identity[use]]
    clock = np.column_stack([cold_model.original.design, cold_model.original.clock_design,
        cold_model.original.group_design])[use]
    shifts = np.zeros((len(use), len(numbers)))
    shifts[np.arange(len(use)), identity[use]] = timing[use, identity[use]]
    covariance = dict(assigned_training_rows=len(use), assumption='Local frequency Jacobian conditioned on cold winning identities; no Hessian, prior or posterior covariance claim.',
        position_east_fraction_explained_by_calibration=projection_fraction(physical[:, 0], clock),
        position_north_fraction_explained_by_calibration=projection_fraction(physical[:, 1], clock),
        position_east_fraction_explained_by_calibration_and_independent_timing=projection_fraction(physical[:, 0], np.column_stack([clock, shifts])),
        position_north_fraction_explained_by_calibration_and_independent_timing=projection_fraction(physical[:, 1], np.column_stack([clock, shifts])),
        common_timing_fraction_explained_by_calibration=projection_fraction(shifts.sum(axis=1), clock),
        original_vector=ctx.vector, cold_vector=v,
        common_timing_original_s=float(ctx.vector[7]), common_timing_cold_s=float(v[7]),
        original_relative_timing_rms_s=float(np.sqrt(np.mean((ctx.model.basis@ctx.vector[8:])**2))),
        cold_relative_timing_rms_s=float(np.sqrt(np.mean((cold_model.basis@v[8:])**2))))
    result = dict(source_id='S03', source_scope='One faithful TRAIN-early/held-late cold endpoint; no new fitting or model choice.',
        candidate_inventory=dict(cold_selected=len(numbers), original_full_selected=len(ctx.bank.numbers),
            intersection=int(present.sum()), cold_only=sorted(set(map(int, numbers))-set(map(int, ctx.bank.numbers))),
            original_full_only=sorted(set(map(int, ctx.bank.numbers))-set(map(int, numbers)))),
        scopes=scopes, calibration_lanes=calibration, local_dependence=covariance,
        strict_training_audit=audit,
        qualification='Full-state/original-winner restrictions and decompositions are posthoc descriptive oracles conditioned on full measured CFO. They are not truth, recovered prediction or cold-validation performance. No held fit, station reference or parameter search.',
        input_sha256={str(path.relative_to(REPORTS)):'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [COLD/'held-predictions.npz', COLD/'evaluation.npz', COLD/'evaluation.json',
                COLD/'output/terminal.json', originals_path]})
    common.save_json(HERE/'diagnosis.json', result)
    with (HERE/'point-decomposition.csv').open('w') as stream:
        writer = csv.writer(stream)
        writer.writerow(['time_s', 'receiver', 'channel', 'train', 'held', 'original_assigned',
            'original_winner', 'original_winner_present', 'cold_assigned', 'cold_correction_minus_original_hz',
            'same_winner_prediction_delta_hz', 'same_winner_orbit_delta_hz', 'same_winner_cold_residual_hz'])
        writer.writerows(zip(obs.times_s, obs.receiver, obs.channel, frozen['train_mask'], frozen['held_mask'],
            assigned, original_number, covered, cold_points['associated'], correction_delta,
            total_delta, orbit_delta, candidate_residual))
    print(json.dumps(dict(inventory=result['candidate_inventory'], scopes=scopes,
        dependence={k:v for k, v in covariance.items() if not k.endswith('vector')}), indent=2))


if __name__ == '__main__':
    main()
