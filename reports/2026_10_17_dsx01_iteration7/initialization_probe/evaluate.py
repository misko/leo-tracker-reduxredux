"""Post-seal, fixed-denominator evaluation; never feeds results into inference."""
# ruff: noqa: E402
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
ROOT = REPORTS.parent
sys.path.insert(0, str(REPORTS/'2026_10_17_dsx01_iteration7/cold_saved_s01'))
sys.path.insert(0, str(REPORTS/'2026_10_17_dsx01_iteration5/joint_band_contrast'))
sys.path.insert(0, str(REPORTS/'2026_10_16_dsx01_models'))
from common import distance_km, point_state
from contexts import load_contexts
from leo.analysis.regional_position_score import coordinates
from leo.application.shared_fast_position import plain
from leo.storage.shared_fast_scan import SharedFastScanStore
from model import free_context


def sha(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rms(values):
    return float(np.sqrt(np.mean(np.asarray(values)**2))) if len(values) else None


def paired(before, after, before_residual, after_residual, before_number, after_number):
    arrays = [np.asarray(a) for a in (before, after, before_residual, after_residual,
                                     before_number, after_number)]
    if any(a.ndim != 1 or a.shape != arrays[0].shape for a in arrays):
        raise ValueError('Aligned one-dimensional observation states required')
    before, after, br, ar, bn, an = arrays
    if before.dtype != bool or after.dtype != bool:
        raise ValueError('Explicit association masks required')
    retained = before & after
    return dict(observations=len(before), original=int(before.sum()), assigned=int(after.sum()),
        new=int((after & ~before).sum()), lost=int((before & ~after).sum()),
        retained=int(retained.sum()), intersection_before_rms_hz=rms(br[retained]),
        intersection_after_rms_hz=rms(ar[retained]),
        retained_identity_changes=int((retained & (bn != an)).sum()))


def compare(before, after, mask=None):
    use = np.ones(len(before['associated']), bool) if mask is None else mask
    return paired(before['associated'][use], after['associated'][use],
        before['residual_hz'][use], after['residual_hz'][use],
        before['number'][use], after['number'][use])


def main():
    seal = json.loads((HERE/'outcomes_seal.json').read_text())
    assert seal['all_four_sealed'] and len(seal['outcomes']) == 4
    assert sha(HERE/'source_freeze.json') == seal['source_freeze_sha256']
    assert sha(HERE/'qualified_freeze.json') == seal['qualified_freeze_sha256']
    for freeze in ('source_freeze.json', 'qualified_freeze.json'):
        for path, expected in json.loads((HERE/freeze).read_text())['files'].items():
            assert sha(path) == expected
    for item in seal['outcomes']:
        assert sha(item['path']) == item['sha256']
    contexts = load_contexts(maximum_seconds=110.)
    target = free_context(contexts['saved_space_track'])
    observations = target.observations
    data = REPORTS/'2026_10_16_dsx01_fast_association_losses'
    authority_path = REPORTS/'2026_10_17_dsx01_iteration5/comparison/receipt.json'
    authority = json.loads(authority_path.read_text())['inputs']
    for name in ('membership.csv', 'context-observations.jsonl'):
        assert sha(data/name) == authority[str((data/name).relative_to(REPORTS))]
    with (data/'membership.csv').open() as stream:
        members = [row for row in csv.DictReader(stream) if row['source_id'] == 'S01']
    ids = np.asarray(observations.window_ids)
    masks = {rid: np.isin(ids, [r['observation_id'] for r in members if r['region_id'] == rid])
             for rid in ('DSX01-001', 'DSX01-002', 'DSX01-003')}
    assert [int(mask.sum()) for mask in masks.values()] == [86, 35, 27]
    requested = np.logical_or.reduce(list(masks.values()))
    assert requested.sum() == 148
    # Only now read the configured station reference. All inference outcomes are sealed.
    source = next(row for row in json.loads((data/'sources.json').read_text())
                  if row['source_id'] == 'S01')
    _, document, _, _ = SharedFastScanStore('/srv/bulk/leo', 'shared-scan-q-v2').plot_evidence(
        source['job_id'])
    station_path = ROOT/'deploy/station/gauss-r20-lt3d-004b-20261001-v1.json'
    station = json.loads(station_path.read_text())
    assert document['source']['radio_id'] == station['radio_serial']
    assert station['valid_from_utc_ns'] <= source['first_sample_estimate_utc_ns']
    assert source['first_sample_estimate_utc_ns'] < station['valid_until_utc_ns']
    states, rows, windows = {}, [], []

    def score(label, context, vector, nuisance, audit, kind, arm):
        ev, details, best, associated, residual = point_state(context.model, vector, nuisance)
        number = context.bank.numbers[best]
        state = dict(associated=associated, residual_hz=residual, number=number,
                     row_nll=details['row_nll'])
        np.testing.assert_allclose(state['row_nll'].sum(), ev[3].nll, rtol=0, atol=1e-7)
        states[label] = state
        lat, lon = coordinates(context.prior, vector[:2])
        tau = vector[7] + context.model.basis @ vector[8:]
        result = dict(label=label, kind=kind, arm=arm, objective=float(ev[0]),
            data_nll=float(ev[3].nll), full_assigned=int(associated.sum()),
            requested_assigned=int(associated[requested].sum()),
            associated_population_rms_hz=rms(residual[associated]), audit=audit,
            configured_reference_distance_km=distance_km([lat, lon],
                [station['latitude_deg'], station['longitude_deg']]),
            position=dict(latitude_deg=float(lat), longitude_deg=float(lon)),
            common_timing_s=float(vector[7]), relative_timing_rms_s=rms(tau-vector[7]),
            total_timing_s={str(int(n)): float(t)
                            for n, t in zip(context.bank.numbers, tau, strict=True)},
            c_hz_per_ghz=float(vector[6]))
        if hasattr(context.model, 'band_design'):
            result['absolute_band_offsets_hz'] = nuisance[
                context.model.original_nuisance_count:].tolist()
        for rid, mask in masks.items():
            selected_numbers, counts = np.unique(number[mask & associated], return_counts=True)
            windows.append(dict(label=label, arm=arm, region_id=rid, observations=int(mask.sum()),
                assigned=int(associated[mask].sum()), row_nll=float(state['row_nll'][mask].sum()),
                identity_histogram={str(int(n)): int(c) for n, c in zip(
                    selected_numbers, counts, strict=True)}))
        np.savez(HERE/f'eval_{label}.npz', observation_id=ids, times_s=observations.times_s,
                 **state)
        rows.append(result)

    for label, ctx in contexts.items():
        score(label, ctx, ctx.vector, ctx.nuisance, ctx.source['audit'], 'historical', 'fitted-c')
    assert int(states['original']['associated'].sum()) == 1643
    assert int(states['saved_space_track']['associated'].sum()) == 2150
    original_counts = [int(states['original']['associated'][mask].sum())
                       for mask in masks.values()]
    assert original_counts == [13, 1, 0]
    for item in seal['outcomes']:
        saved = json.loads(Path(item['path']).read_text())
        label = saved['donor'] + '_' + saved['arm']
        score(label, target, np.asarray(saved['result']['vector']),
              np.asarray(saved['result']['nuisance']), saved['independent_audit'],
              'controlled_initialization', saved['arm'])
    for row in rows:
        row['full_vs_original'] = compare(states['original'], states[row['label']])
        row['requested_vs_original'] = compare(states['original'], states[row['label']], requested)
        if row['kind'] == 'controlled_initialization':
            baseline = 'original_' + row['arm']
            row['full_vs_matched_original_start'] = compare(states[baseline], states[row['label']])
            row['requested_vs_matched_original_start'] = compare(
                states[baseline], states[row['label']], requested)
        for window in [w for w in windows if w['label'] == row['label']]:
            window['vs_original'] = compare(states['original'], states[row['label']],
                                             masks[window['region_id']])
    payload = dict(rows=rows, windows=windows, seal_sha256=sha(HERE/'outcomes_seal.json'),
        all_four_frozen_before_evaluation=True, observations=4797, requested=148,
        untested_sources=4, untested_requested_observations=545, untested_windows=12,
        configured_reference=dict(sha256=sha(station_path), revision=station['revision'],
            binding='Same recording radio serial and validity interval',
            uncertainty=station['position_evidence']), classification_objective_calls=6,
        additional_public_context_replay_calls=2, no_model_selection=True,
        input_authority_sha256=sha(authority_path),
        evaluation_code_sha256=sha(__file__),
        scope='One-source full-data development. Historical providers not budget matched.')
    with (HERE/'evaluation.json').open('x') as stream:
        json.dump(plain(payload), stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps([dict(label=r['label'], assigned=r['full_assigned'],
        requested=r['requested_assigned'], nll=r['data_nll'],
        configured_km=r['configured_reference_distance_km'], strict=r['audit']['accepted'])
        for r in rows], indent=2))


if __name__ == '__main__':
    main()
