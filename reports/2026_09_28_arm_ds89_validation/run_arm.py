"""Run a frozen method on four metadata-selected fresh dwells, without RF."""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
HARNESS = REPORTS / '2026_09_28_arm_full_optimization'
sys.path.insert(0, str(HARNESS))
import arm_cohort

SELECT_FOUR = arm_cohort.select_four


def selection(rows, dataset):
    return SELECT_FOUR([r for r in rows if r['dataset_id'] == dataset])


def run(inputs, baseline, output, dataset, method):
    inputs, baseline = inputs.resolve(), baseline.resolve()
    receipt = json.loads((inputs / 'inputs.json').read_text())
    if not receipt['complete']:
        raise ValueError('Incomplete input receipt')
    selected = selection(receipt['rows'], dataset)
    expected = {(r['session_id'], r['visit_index']): r['sha256'] for r in selected}
    observed = {}
    for line in baseline.read_text().splitlines():
        r = json.loads(line)
        ctx = r['context']
        key = (ctx['session_id'], ctx['visit_index'])
        if key in expected:
            if key in observed or r['status'] != 'ok' or r['method'] != 'original' or r['repeat'] != 0:
                raise ValueError('Invalid selected baseline record')
            observed[key] = ctx['sha256']
    if observed != expected:
        raise ValueError('ARM subset baseline missing or input hashes differ')
    if method == 'boundary':
        build = REPORTS / '2026_09_28_arm_boundary_fallback/builds/arm-v1'
        binary, unit = build / 'cohort_boundary', build / 'test_boundary'
    else:
        build = Path('/var/tmp/leo-arm-refinement-cache-v2')
        binary, unit = build / 'cohort', build / 'test_refinement_cache'
    receipt_path = (build / 'build.json' if method == 'boundary' else
        REPORTS / '2026_09_28_arm_refinement_cache/builds/arm-v2/build.json')
    build_receipt = json.loads(receipt_path.read_text())
    for path in (binary, unit):
        if arm_cohort.sha(path) != build_receipt['binary_sha256'][path.name]:
            raise ValueError('Frozen binary hash differs')
    # Reuse unchanged transport, template verification, CPU0 binary and timing.
    arm_cohort.INPUTS = inputs
    arm_cohort.BASELINE = baseline
    arm_cohort.select_four = lambda rows: selected
    arm_cohort.run(binary, unit, output)
    provenance = dict(dataset_id=dataset, method=method,
        wrapper_sha256=arm_cohort.sha(Path(__file__)),
        build_receipt_sha256=arm_cohort.sha(receipt_path),
        selection='First and last lower then first and last upper at 2.5 MS/s within dataset',
        selected=[(r['session_id'], r['visit_index'], r['sha256']) for r in selected])
    (output / 'validation-provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--dataset', choices=('DS8','DS9'), required=True)
    p.add_argument('--method', choices=('boundary','exact-cache'), required=True)
    a = p.parse_args()
    run(a.inputs, a.baseline, a.output, a.dataset, a.method)
