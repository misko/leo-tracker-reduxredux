"""Apply frozen empirical uncertainty cutoffs to one sealed held-out position."""
# ruff: noqa: E402, I001
import time

START = time.monotonic()
import argparse
import json
from pathlib import Path
import resource
import sys

import numpy as np
from heldout_adapter import prepare_heldout
from regression_batch import digest, verify_sources
from uncertainty_shape_adapter import build_shapes

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = dict(unit=args.unit, status='error', error_m=None, geographic_coverage=None)
    try:
        threshold_path = HERE/'uncertainty-thresholds-v1-freeze.json'
        assert digest(threshold_path) == threshold_path.with_suffix('.sha256').read_text().strip()
        thresholds = json.loads(threshold_path.read_text())
        verify_sources(thresholds['source_sha256'])
        frozen = HERE/'heldout-baseline-v1-freeze.json'
        assert digest(frozen) == thresholds['heldout_prediction_freeze_sha256']
        assert digest(frozen) == frozen.with_suffix('.sha256').read_text().strip()
        verify_sources(json.loads(frozen.read_text())['source_sha256'])
        validation = json.loads((HERE/'uncertainty-shape-adapter-validation.json').read_text())
        assert validation['all_passed']
        assert validation['adapter_sha256'] == digest(HERE/'uncertainty_shape_adapter.py')
        paths = list((HERE/'heldout-baseline-v1').glob('batch-*/'+args.unit+'.json'))
        assert len(paths) == 1
        path = paths[0]
        assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())[
            'prediction_sha256']
        parent = json.loads(path.read_text())
        assert parent['unit_id'] == args.unit and parent['best']['converged']
        scan, height, ports = prepare_heldout(args.unit)
        assert scan.inputs == parent['inputs'] and height.input_bindings == parent['height']
        assert [list(p.observation_ids) for p in ports] == parent['observations']
        state = np.asarray(parent['best']['mean'])
        matrices, labels, shifts = build_shapes(ports, state)
        arms = {}
        for arm, matrix in matrices.items():
            eigenvalues = np.linalg.eigvalsh(matrix)
            axes = {p: (1000*np.sqrt(rule['squared_distance_cutoff']*eigenvalues)).tolist()
                    for p, rule in thresholds['thresholds'][arm].items()}
            arms[arm] = dict(matrix_km2=matrix.tolist(), ellipse_minor_major_axes_m=axes)
        result.update(status='shapes_prepared', parent_sha256=digest(path),
                      threshold_freeze_sha256=digest(threshold_path),
                      position_km=state[:2].tolist(),
                      group_count=len(labels), largest_predicted_deletion_shift_m=float(
                          1000*np.linalg.norm(shifts, axis=1).max()),
                      inputs=scan.inputs, height=height.input_bindings, arms=arms,
                      qualification='No reference location read; empirical development cutoffs '
                      'applied unchanged to all three candidate shapes. No calibrated coverage '
                      'claim. Point unchanged; diagnostic runtime separate from inference.')
    except Exception as error:
        result['exception'] = type(error).__name__+': '+str(error)
    result['source_sha256'] = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            p = Path(filename).resolve()
            if p.suffix == '.py' and p.is_relative_to(HERE.parents[1]):
                result['source_sha256'][str(p)] = digest(p)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result.update(cpu_seconds=usage.ru_utime+usage.ru_stime,
                  wall_seconds_before_sealing=time.monotonic()-START)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    print(json.dumps({k: result.get(k) for k in
                     ['unit', 'status', 'wall_seconds_before_sealing', 'exception']}))


if __name__ == '__main__':
    main()
