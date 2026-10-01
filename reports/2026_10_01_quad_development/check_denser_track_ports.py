"""Recorded parity, covariance, normalization and gradient prerequisites; no fits."""
import fcntl
import json
from math import lgamma, log, pi
from pathlib import Path
import sys
import time
import numpy as np
from window_inputs import prepare_scan
from denser_track_ports import build_ports
from regression_batch import verify_sources
from screen_seed_prefix import digest, sealed

HERE = Path(__file__).resolve().parent


def log_density(residual, covariance):
    d = len(residual)
    chol = np.linalg.cholesky(covariance)
    q = float(np.linalg.solve(chol, residual) @ np.linalg.solve(chol, residual))
    return (lgamma((4+d)/2)-lgamma(2)-.5*d*log(4*pi)
            -np.log(np.diag(chol)).sum()-(4+d)/2*np.log1p(q/4))


def main():
    output = HERE/'denser-track-port-check-v1.json'
    if output.exists():
        raise FileExistsError(output)
    rows, inputs = [], {}
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        started = time.monotonic()
        for dataset in ('DS9', 'DS10', 'DS11'):
            unit = dataset+'-B01-S1'
            path = HERE/'independent-v2'/(dataset+'-B01')/(unit+'.json')
            receipt = sealed(path)
            verify_sources(receipt['source_sha256'])
            verify_sources(receipt['inputs'])
            inputs.update(receipt['inputs'])
            inputs[str(path)] = digest(path)
            scan, height, original = prepare_scan(receipt['binding']['scans'][0])
            inputs[height.input_bindings['grid_path']] = height.input_bindings['grid_sha256']
            eight, eight_selection = build_ports(scan, height, 8)
            sixteen, selection = build_ports(scan, height, 16)
            state = np.asarray(receipt['best']['mean'])
            max_score_error = 0.
            max_prediction_error = 0.
            for i, (old, control, dense) in enumerate(zip(original, eight, sixteen)):
                assert old.observation_ids == control.observation_ids
                assert set(control.observation_ids) <= set(dense.observation_ids)
                a, b = old.score_all(state), control.score_all(state)
                assert np.array_equal(np.isfinite(a), np.isfinite(b))
                max_score_error = max(max_score_error, float(np.max(abs(a[np.isfinite(a)]-b[np.isfinite(b)]))))
                index = receipt['best']['associations'][i]
                if index < old.candidate_count:
                    x, y = old.predict_selected(state, index), control.predict_selected(state, index)
                    max_prediction_error = max(max_prediction_error, float(np.max(abs(x.mean-y.mean))), float(np.max(abs(x.jacobian-y.jacobian))))
                    assert np.array_equal(x.covariance, y.covariance)
                likelihood = dense.likelihood
                n = len(dense.observation_ids)
                assert dense.observation.shape == (n-1,)
                assert likelihood.covariance.shape == likelihood.background_covariance.shape == (n-1, n-1)
                lag = np.abs(likelihood.times[:, None]-likelihood.times[None, :])
                raw = scan.config.white_noise_hz**2*np.eye(n)+scan.config.correlated_noise_hz**2*np.exp(-lag/scan.config.correlation_time_s)
                assert np.allclose(likelihood.covariance, likelihood.contrasts@raw@likelihood.contrasts.T, rtol=0, atol=1e-8)
                scores = dense.score_all(state)
                visible = int(np.isfinite(scores[:-1]).sum())
                background_prior = scan.config.background_prior+scan.config.signal_prior*(dense.candidate_count-visible)/dense.candidate_count
                assert abs(background_prior+visible*scan.config.signal_prior/dense.candidate_count-1) < 1e-12
                expected = log_density(dense.observation, likelihood.background_covariance)+log(background_prior)
                assert abs(expected-scores[-1]) < 1e-7
            assert max_score_error < 1e-7 and max_prediction_error < 1e-7
            track_index = next(i for i, p in enumerate(sixteen) if np.argmax(p.score_all(state)) < p.candidate_count)
            port = sixteen[track_index]
            index = int(np.argmax(port.score_all(state)))
            pred = port.predict_selected(state, index)
            residual = port.observation-pred.mean
            expected = log_density(residual, pred.covariance)+log(scan.config.signal_prior/port.candidate_count)
            assert abs(expected-port.score_selected(state, index)) < 1e-6
            assert abs(port.score_selected(state, index)-port.score_all(state)[index]) < 1e-6
            solved = np.linalg.solve(pred.covariance, residual)
            gradient = (4+len(residual))/(4+float(residual@solved))*pred.jacobian.T@solved
            errors = []
            for step in (.0005, .0001):
                differences = []
                for column in (0, 1, 2, 3, 4, 5+index):
                    shift = np.zeros_like(state)
                    shift[column] = step
                    numerical = (port.score_selected(state+shift, index)-port.score_selected(state-shift, index))/(2*step)
                    differences.append(abs(numerical-gradient[column]))
                errors.append(max(differences))
            assert max(errors) < .002
            rows.append(dict(unit=unit, tracks=len(original), points_8=sum(len(p.observation_ids) for p in eight),
                points_16=sum(len(p.observation_ids) for p in sixteen),
                maximum_control_score_error=max_score_error, maximum_control_prediction_error=max_prediction_error,
                checked_track_index=track_index, candidate_index=index, finite_difference_errors=errors,
                selection=selection))
        sources = {str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
            if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py'
            and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
        result = dict(rows=rows, inputs=inputs, sources=sources, seconds=time.monotonic()-started,
                      qualification='No localization fit or reference scoring. All-track control parity and dense covariance/background checks; one dense signal gradient per dataset at a saved state. Hard visibility remains piecewise constant.')
        with output.open('x') as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        output.with_suffix('.sha256').write_text(digest(output)+'\n')
        print(json.dumps([{k: v for k, v in r.items() if k != 'selection'} for r in rows], indent=2))


if __name__ == '__main__':
    main()
