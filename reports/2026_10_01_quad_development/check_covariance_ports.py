"""Recorded covariance-port density, background, trace and objective checks."""
import fcntl
import json
from pathlib import Path
import sys
import numpy as np
from covariance_track_ports import build_covariance_ports
from denser_window_inputs import prepare_denser_window
from conditional_track_evidence import log_student
from regression_batch import verify_sources
from screen_seed_prefix import digest, sealed

HERE = Path(__file__).resolve().parent


def main():
    output = HERE/'covariance-port-check-v1.json'
    if output.exists():
        raise FileExistsError(output)
    screen_path = HERE/'trace-matched-noise-screen-v1.json'
    screen = sealed(screen_path)
    verify_sources(screen['sources'])
    verify_sources(screen['inputs'])
    inputs = {str(screen_path): digest(screen_path), **screen['inputs']}
    rows = []
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for dataset in ('DS9', 'DS10', 'DS11'):
            unit = dataset+'-B01-S1'
            parent = HERE/'independent-v2'/(dataset+'-B01')/(unit+'.json')
            receipt = sealed(parent)
            inputs[str(parent)] = digest(parent)
            prepared, _ = prepare_denser_window(unit, 16)
            scan, height, _ = prepared[1][0]
            state, precision = np.asarray(receipt['best']['mean']), prepared[3]
            references, _ = build_covariance_ports(scan, height, 'tau10')
            for arm in ('tau10', 'matched_white'):
                ports, _ = build_covariance_ports(scan, height, arm)
                gradient = precision*state
                assigned = []
                active = set()
                density_errors = []
                for port, reference in zip(ports, references):
                    likelihood = port.likelihood
                    assert port.observation_ids == reference.observation_ids
                    assert abs(np.trace(likelihood.covariance)-np.trace(reference.likelihood.covariance)) < 1e-7
                    scores = port.score_all(state)
                    index = int(np.argmax(scores))
                    assigned.append(index)
                    visible = np.isfinite(scores[:-1]).sum()
                    bg_prior = scan.config.background_prior+scan.config.signal_prior*(port.candidate_count-visible)/port.candidate_count
                    density_errors.append(abs(scores[-1]-np.log(bg_prior)-log_student(port.observation, likelihood.background_covariance, 4)))
                    if index < port.candidate_count:
                        prediction = port.predict_selected(state, index)
                        assert prediction.eligible
                        assert np.allclose(prediction.covariance, likelihood.covariance, rtol=0, atol=1e-7)
                        residual = port.observation-prediction.mean
                        expected = log_student(residual, prediction.covariance, 4)+np.log(scan.config.signal_prior/port.candidate_count)
                        density_errors.append(abs(expected-scores[index]))
                        solved = np.linalg.solve(prediction.covariance, residual)
                        gradient -= (4+len(residual))/(4+float(residual@solved))*prediction.jacobian.T@solved
                        active.add(5+index)
                assert max(density_errors) < 1e-6

                def objective(x):
                    scores = [p.score_all(x) for p in ports]
                    assert [int(np.argmax(s)) for s in scores] == assigned, 'Association boundary'
                    return float(.5*(precision*x)@x-sum(s[i] for s,i in zip(scores, assigned)))

                directions = [np.eye(1, len(state), k=i)[0] for i in range(5)]
                rng = np.random.default_rng(1016)
                for _ in range(3):
                    d = np.zeros_like(state)
                    d[sorted(active)] = rng.normal(size=len(active))
                    directions.append(d/np.linalg.norm(d))
                errors = [abs((objective(state+step*d)-objective(state-step*d))/(2*step)-gradient@d)
                          for step in (.0005, .0001) for d in directions]
                assert max(errors) < .002
                rows.append(dict(unit=unit, arm=arm, tracks=len(ports),
                    maximum_density_error=max(density_errors), maximum_gradient_error=float(max(errors))))
    sources = {str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py'
        and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
    result = dict(rows=rows, inputs=inputs, sources=sources,
        qualification='Recorded prerequisites only, no fits/geography scoring. All-track trace and density checks; eight full-objective directions at two steps per arm. No global smoothness claim.')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
