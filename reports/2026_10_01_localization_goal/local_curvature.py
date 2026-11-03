"""Compute inverse IRLS curvature at one sealed prediction, without GPS."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from regression_batch import digest

from leo.analysis.localization_uncertainty import profiled_position_covariance

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    start = time.monotonic()
    paths = list((HERE/'regression-v1').glob('batch-*/'+args.unit+'.json'))
    assert len(paths) == 1
    path = paths[0]
    assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())[
        'prediction_sha256']
    receipt = json.loads(path.read_text())
    assert receipt['status'] == 'converged_local_mode'
    for filename, expected in receipt['source_sha256'].items():
        assert digest(filename) == expected
    scan, height, ports = prepare(args.unit)
    assert scan.inputs == receipt['inputs'] and height.input_bindings == receipt['height']
    assert [list(p.observation_ids) for p in ports] == receipt['observations']
    state = np.asarray(receipt['best']['mean'])
    assignments = [int(np.argmax(p.score_all(state))) for p in ports]
    epochs = sorted({5+i for p, i in zip(ports, assignments, strict=True)
                     if i < p.candidate_count})
    columns = np.array([0, 1, 2, 3, 4, *epochs])
    information = np.diag(np.r_[0., 0., 1., np.full(len(columns)-3, 4.)])
    signal_tracks = 0
    for port, index in zip(ports, assignments, strict=True):
        if index == port.candidate_count:
            continue
        prediction = port.predict_selected(state, index)
        assert prediction.eligible
        residual = port.observation-prediction.mean
        jacobian = prediction.jacobian[:, columns]
        solved = np.linalg.solve(prediction.covariance, residual)
        weight = (4+len(residual))/(4+float(residual@solved))
        information += weight*jacobian.T@np.linalg.solve(prediction.covariance, jacobian)
        signal_tracks += 1
    covariance = profiled_position_covariance(information)
    result = dict(
        unit=args.unit, receipt_sha256=digest(path), source_sha256=digest(__file__),
        kernel_sha256=digest(HERE.parents[1]/'src/leo/analysis/localization_uncertainty.py'),
        position_km=state[:2].tolist(), covariance_km2=covariance.tolist(),
        axis_scales_m=(1000*np.sqrt(np.linalg.eigvalsh(covariance))).tolist(),
        signal_tracks=signal_tracks, nuisance_dimension=len(columns)-2,
        seconds=time.monotonic()-start,
        qualification=('Conditional hard-assignment inverse IRLS curvature at sealed state. '
                       'Includes local shared nuisance coupling and prior curvature. '
                       'Excludes other location modes, identity uncertainty, model discrepancy, '
                       'and residual second derivatives. Not calibrated uncertainty.'),
    )
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    print(json.dumps(dict(unit=args.unit, seconds=result['seconds'])))


if __name__ == '__main__':
    main()
