"""Full dense single-scan objective directional derivatives before any fitting."""
import fcntl
import json
from pathlib import Path
import sys
import time
import numpy as np
from window_inputs import prepare_scan
from denser_track_ports import build_ports
from regression_batch import verify_sources
from screen_seed_prefix import digest, sealed

HERE = Path(__file__).resolve().parent


def main():
    output = HERE/'denser-scan-objective-check-v1.json'
    if output.exists():
        raise FileExistsError(output)
    check_path = HERE/'denser-track-port-check-v1.json'
    gate = sealed(check_path)
    verify_sources(gate['sources'])
    verify_sources(gate['inputs'])
    rows = []
    inputs = {str(check_path): digest(check_path), **gate['inputs']}
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        started = time.monotonic()
        for dataset in ('DS9', 'DS10', 'DS11'):
            unit = dataset+'-B01-S1'
            receipt = sealed(HERE/'independent-v2'/(dataset+'-B01')/(unit+'.json'))
            scan, height, _ = prepare_scan(receipt['binding']['scans'][0])
            ports, _ = build_ports(scan, height, 16)
            state, precision = np.asarray(receipt['best']['mean']), np.asarray(receipt['precision'])
            assigned = [int(np.argmax(p.score_all(state))) for p in ports]
            gradient = precision*state
            active_epochs = set()
            for port, index in zip(ports, assigned):
                if index < port.candidate_count:
                    pred = port.predict_selected(state, index)
                    residual = port.observation-pred.mean
                    solved = np.linalg.solve(pred.covariance, residual)
                    gradient -= (4+len(residual))/(4+float(residual@solved))*pred.jacobian.T@solved
                    active_epochs.add(5+index)

            def objective(x):
                # Check the actual max-branch objective, including background priors.
                scores = [p.score_all(x) for p in ports]
                labels = [int(np.argmax(s)) for s in scores]
                if labels != assigned:
                    raise ValueError('Association boundary crossed: derivative check inconclusive')
                return float(.5*(precision*x)@x-sum(s[i] for s, i in zip(scores, assigned)))

            directions = [np.eye(1, len(state), k=i)[0] for i in range(5)]
            rng = np.random.default_rng(1608)
            for _ in range(3):
                direction = np.zeros_like(state)
                indices = sorted(active_epochs)
                direction[indices] = rng.normal(size=len(indices))
                direction /= np.linalg.norm(direction)
                directions.append(direction)
            errors = []
            for step in (.0005, .0001):
                errors.append([abs((objective(state+step*d)-objective(state-step*d))/(2*step)-gradient@d)
                               for d in directions])
            maximum = float(np.max(errors))
            assert maximum < .002, maximum
            rows.append(dict(unit=unit, dimension=len(state), tracks=len(ports),
                signal_tracks=sum(i < p.candidate_count for p, i in zip(ports, assigned)),
                active_epochs=len(active_epochs), objective=objective(state),
                gradient_errors=errors, maximum_gradient_error=maximum))
        sources = {str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
            if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py'
            and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
        result = dict(rows=rows, inputs=inputs, sources=sources, seconds=time.monotonic()-started,
            qualification='No fits/reference scoring. Full max-branch objective checked in five position/clock/drift axes and three active-epoch directions, at two steps; assignments must remain unchanged. Not global smoothness or stationarity evidence.')
        with output.open('x') as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        output.with_suffix('.sha256').write_text(digest(output)+'\n')
        print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
