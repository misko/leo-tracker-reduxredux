"""Frozen-fit diagnostic only: screen archived omitted satellites, not admissions."""
from pathlib import Path
import csv
import json
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
SOURCE = REPORTS / '2026_10_02_ds13_timing_em'
sys.path[:0] = [str(SOURCE), str(REPORTS / '2026_10_02_multiscan_localization'),
               str(REPORTS / '2026_10_02_localization_benchmark'),
               str(REPORTS / '2026_10_02_coherent_localization')]
from all_visible_bank import load_expanded_scan
from compact_satellite_selection import competitive_addition_scores
from finite_set_likelihood import circular_residual, prepare_finite_set_likelihood
from prediction_plan import SharedPredictionPlan
from rf_calibration_diagnostic import rf_features


def main():
    results = {}
    for label, session in zip('AB', ['scan-fw-911c4e5db9243281', 'scan-fw-ffa1cc19d8d7c09f']):
        profile = json.loads((SOURCE / 'pruned-position-profile-grid' / f'{session}.json').read_text())
        fit = next(p for p in profile['positions'] if p['label'] == 'truth')['best']
        data = load_expanded_scan(session)
        params = np.array(fit['parameters'])
        selected = np.array(profile['satellite_indices'], int)
        omitted = np.setdiff1d(np.arange(len(data.numbers)), selected)
        common_time = float(np.mean(params[6 + selected]))
        params[6 + omitted] = common_time
        _, features = rf_features(data.rf, data.receiver, False)
        rf_term = features @ np.array(fit['rf_coefficient_hz_per_ghz'])
        prepared = prepare_finite_set_likelihood(data.measured, data.group)
        def predict(indices):
            pred, vis, _ = SharedPredictionPlan(data, indices).predict(params)
            return pred.reshape(len(data.times), -1) + rf_term[:, None], vis.reshape(len(data.times), -1)
        pred, vis = predict(selected)
        selected_residual = np.where(vis, np.abs(circular_residual(data.measured[:, None], pred, prepared.alias_hz)), np.inf)
        best_selected = selected_residual.min(axis=1)
        baseline = prepared.evaluate(pred, vis, sigma_hz=200,
                                     detection_probability=profile['detection_probability'], clutter_rate=2)
        assigned = {int(r['row_index']) for r in csv.DictReader((HERE / 'baseline' / f'{label}-assignments.csv').open())}
        unused = np.array([i not in assigned for i in range(len(data.times))])
        rows = []
        for start in range(0, len(omitted), 32):
            indices = omitted[start:start + 32]
            pred, vis = predict(indices)
            scores = competitive_addition_scores(prepared, baseline, pred, vis, profile['detection_probability'])
            residual = circular_residual(data.measured[:, None], pred, prepared.alias_hz)
            for col, index in enumerate(indices):
                matched = unused & vis[:, col] & (np.abs(residual[:, col]) <= 250)
                times = np.unique(data.times[matched])
                segments = []
                for rx in np.unique(data.receiver):
                    for ch in np.unique(data.channel):
                        lane = matched & (data.receiver == rx) & (data.channel == ch)
                        ticks = np.unique(np.round(data.times[lane], 3))
                        for part in np.split(ticks, np.flatnonzero(np.diff(ticks) > 3) + 1):
                            if len(part) >= 3:
                                segments.append(dict(receiver=int(rx), channel=int(ch),
                                                     start_s=float(part[0]), end_s=float(part[-1]),
                                                     span_s=float(part[-1] - part[0]), samples=len(part)))
                segments.sort(key=lambda s: s['span_s'], reverse=True)
                rows.append(dict(catalog_number=int(data.numbers[index]),
                                 log_likelihood_gain=float(scores['log_likelihood_change'][col]),
                                 expected_group_support=float(scores['candidate_expected_group_support'][col]),
                                 unassigned_groups_within_250hz=int(len(np.unique(data.group[matched]))),
                                 groups_also_within_500hz_of_selected=int(len(np.unique(data.group[matched & (best_selected <= 500)]))),
                                 longest_lane_segments=segments[:3],
                                 span_s=float(np.ptp(times)) if len(times) else 0.0))
        rows.sort(key=lambda r: r['log_likelihood_gain'], reverse=True)
        results[label] = dict(session=session, selected_count=len(selected), omitted_count=len(omitted),
                              common_timing_s=common_time, candidates=rows)
        print(label, json.dumps(rows[:10]), flush=True)
    output = HERE / 'omitted-candidate-audit.json'
    output.write_text(json.dumps(dict(scope=__doc__, timing='Omitted satellites fixed to mean selected timing; no timing search or refit. Gains are separate single-candidate additions, not joint admissions.', scans=results), indent=2))


if __name__ == '__main__':
    main()
