"""Replay complete scientific objectives before accepting an optimized exact DP."""
import json
from pathlib import Path
import time
import numpy as np
from whole_source_run import load_model
from whole_source_fast import WholeSourcePosition
from doppler_pilot import read, digest

HERE = Path(__file__).resolve().parent


def accelerate(model, cohort, index):
    bound = read(HERE / (f'input-{index:02d}.json' if cohort == 'original' else 'additional-input-01.json'))
    config = dict(geographic_prior_center_deg=model.geometry.center, timing_grid_s=model.geometry.taus)
    return WholeSourcePosition(model.geometry.document, config, bound, model.calibration, model.arm)


def main():
    rows, sources = [], {}
    for cohort, index in [('original', 0), ('original', 16), ('additional', 1)]:
        old, _, initial, bindings = load_model(cohort, index, 'signed')
        sources.update(bindings)
        endpoint = HERE / f'whole-{cohort}-{index:02d}-signed.json'
        x = np.array(read(endpoint)['x']) if endpoint.exists() else initial
        if endpoint.exists():
            sources[str(endpoint)] = digest(endpoint)
        start = time.monotonic()
        a = old.evaluate(x)
        old_s = time.monotonic() - start
        model = accelerate(old, cohort, index)
        start = time.monotonic()
        b = model.evaluate(x)
        new_s = time.monotonic() - start
        difference = a['score'] - b['score']
        derivative = float(np.max(np.abs(a['gradient'] - b['gradient'])))
        assert abs(difference) < 1e-8 and derivative < 1e-7
        assert abs(a['expected_sources'] - b['expected_sources']) < 1e-7
        row = dict(cohort=cohort, index=index, old_s=old_s, new_s=new_s, score_difference=difference, gradient_difference=derivative)
        rows.append(row)
        print(json.dumps(row), flush=True)
    for p in (Path(__file__), HERE / 'source_partition_fast.py', HERE / 'whole_source_fast.py', HERE / 'WHOLE_SOURCE_RUNTIME.md', HERE / 'test_source_partition_fast.py'):
        sources[str(p)] = digest(p)
    with (HERE / 'whole-source-speed-check.json').open('x') as f:
        json.dump(dict(rows=rows, sources=sources, parity_passed=True), f, indent=2, allow_nan=False)


if __name__ == '__main__':
    main()
