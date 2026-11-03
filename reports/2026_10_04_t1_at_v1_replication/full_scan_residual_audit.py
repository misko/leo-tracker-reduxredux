"""Channel-controlled residual structure after coherent full-scan calibration.

Diagnostic nested fits only: no observations or localization results are changed.
At each saved roof/best fit use confidently supported original-owner rows, then
remove independent RX/channel constants before measuring shared satellite slope
and curvature. Selection is conditional/in-sample, not validation of identity.
"""
import argparse
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from full_scan_cohort import OUT as SOURCE, SCANS, ARMS, digest, serial, make_objective
from position_direct import coordinate_jacobian

OUT = SOURCE/'residual-audit'
REFERENCE_RF_HZ = 11.085e9


def nested_track_fit(times, rf, receiver, channel, residual, weights):
    arrays = [np.asarray(v) for v in (times, rf, receiver, channel, residual, weights)]
    times, rf, receiver, channel, residual, weights = arrays
    if not all(a.ndim == 1 and len(a) == len(times) for a in arrays):
        raise ValueError('Matched diagnostic vectors required')
    if len(times) < 10 or np.ptp(times) < 10:
        return None
    if not all(np.all(np.isfinite(a)) for a in arrays) or np.any(weights <= 0) or np.any(rf <= 0):
        raise ValueError('Finite observations and positive weights/RF required')
    lanes = 4*receiver+channel-1
    unique = np.unique(lanes)
    offsets = (lanes[:, None] == unique).astype(float)
    center = np.average(times, weights=weights)
    scale = max(1., np.max(abs(times-center)))
    t = (times-center)/scale
    signal = rf/REFERENCE_RF_HZ
    root = np.sqrt(weights)
    designs = [offsets, np.column_stack([offsets, signal*t]),
               np.column_stack([offsets, signal*t, signal*t*t])]
    rms, coefficients, ranks = [], [], []
    for x in designs:
        beta, _, rank, _ = np.linalg.lstsq(x*root[:, None], residual*root, rcond=None)
        error = residual-x@beta
        coefficients.append(beta); ranks.append(rank)
        rms.append(float(np.sqrt(np.average(error**2, weights=weights))))
    if ranks[-1] < designs[-1].shape[1] or len(times) <= ranks[-1]:
        return None
    assert rms[2] <= rms[1]+1e-8 and rms[1] <= rms[0]+1e-8
    rxtimes = [times[receiver == rx] for rx in (0, 1)]
    overlap = max(0., min(a.max() for a in rxtimes)-max(a.min() for a in rxtimes)) if all(len(a) for a in rxtimes) else 0.
    return dict(windows=len(times), span_s=float(np.ptp(times)), lane_count=len(unique),
        rx0_windows=len(rxtimes[0]), rx1_windows=len(rxtimes[1]), rx_time_range_overlap_s=float(overlap),
        lane_constant_rms_hz=rms[0], plus_shared_linear_rms_hz=rms[1], plus_shared_quadratic_rms_hz=rms[2],
        linear_improvement_ratio=rms[0]/max(rms[1], 1e-12), curvature_ratio=rms[1]/max(rms[2], 1e-12),
        shared_linear_hz_s=float(coefficients[1][-1]/scale),
        shared_quadratic_hz_s2=float(coefficients[2][-1]/scale**2), time_center_s=float(center))


def run(scans):
    rows, gradients, provenance = [], [], []
    OUT.mkdir(parents=True, exist_ok=True)
    for scan in scans:
        source = SOURCE/scan/'full-rebuilt-members.json'; result = json.loads(source.read_text())
        with np.load(source.with_suffix('.npz')) as z:
            data = SimpleNamespace(**{k: z[k].copy() for k in z.files})
        assert result['input_sha256'] == digest(source.with_suffix('.npz'))
        provenance.append(dict(path=str(source), sha256=digest(source), input_sha256=result['input_sha256']))
        owner = np.array([int(np.flatnonzero(data.numbers == n)[0]) for n in data.owners])
        rr = np.arange(len(owner))
        for arm in ARMS:
            obj = make_objective(data, result['input_metadata'], arm)
            for point in ('roof', 'best'):
                record = result['arms'][arm][point]; v = np.asarray(record['vector'])
                value, gradient = obj.evaluate(v)
                np.testing.assert_allclose(value, record['objective'], atol=1e-7, rtol=0)
                p = obj.likelihood.last_result['row_association_probability'].copy()
                pg = obj.likelihood.last_result['prediction_gradient'].copy()
                pred, visible, jac = obj.base.predict(v[:obj.size], with_jacobian=True)
                pred += (obj.features@v[obj.size:])[:, None]
                alias = obj.likelihood.alias_hz
                residual = (data.measured-pred[rr, owner]+alias/2)%alias-alias/2
                probability = p[rr, owner]
                conditional = probability/np.maximum(p.sum(axis=1), 1e-300)
                good = (probability >= .5)&(conditional >= .9)&visible[rr, owner]&(abs(residual) <= 600.)
                geojac = coordinate_jacobian(record['point_km'])
                contributions = []
                for j, number in enumerate(data.numbers):
                    part = np.zeros_like(pg); part[:, j] = pg[:, j]
                    g = geojac.T@(-jac.transpose_multiply(part.ravel()))[:2]
                    contributions.append(g)
                    gradients.append(dict(scan=scan, arm=arm, point=point, satellite=int(number),
                        east_score_per_km=float(g[0]), north_score_per_km=float(g[1]),
                        strength_score_per_km=float(np.linalg.norm(g))))
                    mask = good&(owner == j)
                    fit = nested_track_fit(data.times[mask], data.rf[mask], data.receiver[mask],
                                           data.channel[mask], residual[mask], probability[mask])
                    if fit:
                        rows.append(dict(scan=scan, arm=arm, point=point, satellite=int(number),
                            position_error_m=float(1000*np.linalg.norm(record['point_km'])),
                            source_fit_converged=bool(record['success']), **fit))
                np.testing.assert_allclose(np.sum(contributions, axis=0), geojac.T@gradient[:2], atol=1e-7, rtol=0)
    summaries = []
    for arm in ARMS:
        for point in ('roof', 'best'):
            subset = [r for r in rows if (r['arm'], r['point']) == (arm, point)]
            summaries.append(dict(arm=arm, point=point, tracks=len(subset),
                above_1p1_linear_ratio=sum(r['linear_improvement_ratio'] > 1.1 for r in subset),
                above_1p1_curvature_ratio=sum(r['curvature_ratio'] > 1.1 for r in subset),
                both_rx_time_overlap_ge10s=sum(r['rx_time_range_overlap_s'] >= 10 for r in subset),
                median_abs_slope_hz_s=float(np.median([abs(r['shared_linear_hz_s']) for r in subset]))))
    report = dict(scope=__doc__, sources=provenance, summaries=summaries,
                  selection='Original-owner probability >=0.5, conditional identity >=0.9, visible, |residual| <=600 Hz; at least10 windows and10 s span.',
                  weighting='Saved original-owner posterior; identical rows and weights across nested diagnostic fits.',
                  gradients='Exact likelihood position-gradient contributions at frozen fitted nuisance; includes all input rows, not just diagnostic support.',
                  rows=rows)
    (OUT/'audit.json').write_text(json.dumps(report, default=serial, indent=2, allow_nan=False))
    for name, values in [('tracks.csv', rows), ('gradient-contributions.csv', gradients)]:
        with (OUT/name).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(values[0])); writer.writeheader(); writer.writerows(values)
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--scans', nargs='+', default=SCANS, choices=SCANS)
    args = parser.parse_args(); run(args.scans)
