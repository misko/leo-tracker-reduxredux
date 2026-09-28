"""Calibration-only, shared-identity Student-t residual scale estimation."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln, logsumexp

HERE = Path(__file__).resolve().parent
BOUNDS = np.log([[1., 5000.], [1.01, 100.]])


def prepare_sessions(payload, allowed_sessions):
    sessions = {}
    for session in payload['sessions']:
        sid = session['session_id']
        if sid not in allowed_sessions or sid in sessions:
            raise ValueError('unexpected or duplicate calibration session')
        grouped = defaultdict(list)
        for row in session['candidate_rows']:
            grouped[row['track_id']].append(row)
        tracks = []
        for tid, rows in grouped.items():
            residual = np.asarray([r['reserve_residual_hz'] for r in rows], float)
            logw = np.asarray([r['log_weight'] for r in rows], float)
            weight = float(rows[0]['weight_seconds'])
            if residual.ndim != 2 or not residual.shape[1] or not np.all(np.isfinite(residual)):
                raise ValueError('invalid reserved residual array')
            if not np.all(np.isfinite(logw)) or not np.isclose(logsumexp(logw), 0., atol=1e-8):
                raise ValueError('invalid training probabilities')
            if not np.isfinite(weight) or weight <= 0 or any(r['weight_seconds'] != weight for r in rows):
                raise ValueError('invalid track duration weight')
            tracks.append((residual, logw, weight))
        if not tracks:
            raise ValueError('empty calibration session')
        sessions[sid] = tracks
    if set(sessions) != set(allowed_sessions):
        raise ValueError('incomplete calibration session set')
    return sessions


def loss(parameters, sessions):
    scale, df = np.exp(parameters)
    constant = gammaln((df + 1) / 2) - gammaln(df / 2) - .5 * np.log(df * np.pi) - np.log(scale)
    scan_losses = []
    for tracks in sessions.values():
        total = weight_sum = 0.
        for residual, logw, weight in tracks:
            ll = constant - (df + 1) / 2 * np.log1p((residual / scale) ** 2 / df)
            total += weight * (-logsumexp(logw + ll.sum(axis=1)) / residual.shape[1])
            weight_sum += weight
        scan_losses.append(total / weight_sum)
    if not scan_losses:
        raise ValueError('no calibration scans')
    return float(np.mean(scan_losses))


def fit(sessions):
    runs = [minimize(loss, np.log(seed), args=(sessions,), method='L-BFGS-B',
                     bounds=BOUNDS, options={'ftol': 1e-11, 'maxiter': 250})
            for seed in ((100., 4.), (300., 2.), (50., 10.))]
    successful = [r for r in runs if r.success and np.isfinite(r.fun)]
    if not successful:
        raise RuntimeError('all calibration optimizations failed')
    result = min(successful, key=lambda r: r.fun)
    scale, df = np.exp(result.x)
    return dict(scale_hz=float(scale), degrees_of_freedom=float(df),
                mean_scan_nll=float(result.fun), optimizer_success=True,
                at_bound=bool(np.any(np.isclose(result.x, BOUNDS[:, 0], atol=1e-4))
                              or np.any(np.isclose(result.x, BOUNDS[:, 1], atol=1e-4))),
                starts=[dict(success=bool(r.success), objective=float(r.fun)) for r in runs])


def main():
    target = HERE / 'frequency_parameters.json'
    if target.exists():
        raise FileExistsError('calibration is frozen; do not overwrite')
    source = HERE / 'calibration_frequency.json'
    raw = source.read_bytes()
    inventory = json.loads((HERE.parent / '2026_09_27_roof_direction_subset/evaluation_inventory.json').read_text())
    allowed = {x['session_id'] for x in inventory if x['split'] == 'calibration'}
    if len(allowed) != 6:
        raise ValueError('expected six frozen calibration scans')
    sessions = prepare_sessions(json.loads(raw), allowed)
    fitted = fit(sessions)
    validation = []
    for sid in sessions:
        fold = fit({s: t for s, t in sessions.items() if s != sid})
        parameters = np.log([fold['scale_hz'], fold['degrees_of_freedom']])
        validation.append(dict(heldout_calibration_session=sid, fit=fold,
            validation_nll=loss(parameters, {sid: sessions[sid]}),
            initialization_nll=loss(np.log([100., 4.]), {sid: sessions[sid]})))
    output = dict(parameters=fitted, calibration_sessions=sorted(allowed), leave_one_scan_out=validation,
        protocol='Fixed initialization training shortlist and CFO; shared-track reserve mixture; occupied-second weights within scan; equal weight per scan. Conditional residual calibration, not orbit uncertainty.',
        scale_bounds_hz=[1., 5000.], df_bounds=[1.01, 100.],
        extraction_sha256='sha256:' + hashlib.sha256(raw).hexdigest(),
        code_sha256='sha256:' + hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    target.write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
