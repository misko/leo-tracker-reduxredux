"""Read reference errors only after every pilot cell has terminated."""
import importlib.util
import json
from pathlib import Path
from common import HERE, JOBS, base, read, digest, bindings, verify_sources
from gate import evaluate


def main():
    receipts = {}
    sources = bindings([Path(__file__), HERE / 'gate.py', HERE / 'PROTOCOL.md'])
    for c, i, _ in JOBS:
        for a in ('doppler', 'signed'):
            path = HERE / f'fit-{c}-{i:02d}-{a}.receipt.json'
            receipt = read(path)
            log = path.with_name(path.name.replace('.receipt.json', '.log'))
            assert digest(log) == receipt['log_sha256']
            assert digest(HERE / 'run.py') == receipt['runner_sha256']
            receipts[c, i, a] = receipt
            sources[str(path)] = digest(path)
    reference_path = base('original') / 'summarize.py'
    spec = importlib.util.spec_from_file_location('original_reference_summary', reference_path)
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    sources[str(reference_path)] = digest(reference_path)
    rows = []
    for c, i, family in JOBS:
        initialpath = base(c) / f'runs/{i:02d}_iid.json'
        row = dict(cohort=c, index=i, family=family, original=dict(distance_m=ref.distance(read(initialpath)['selected']['estimate_deg'])))
        sources[str(initialpath)] = digest(initialpath)
        for a in ('doppler', 'signed'):
            receipt = receipts[c, i, a]
            path = HERE / f'fit-{c}-{i:02d}-{a}.json'
            if receipt['exit_code'] != 0 or not path.exists():
                row[a] = dict(qualified=False, exit_code=receipt['exit_code'], elapsed_s=receipt['elapsed_s'])
                continue
            fit = read(path)
            verify_sources(fit)
            sources[str(path)] = digest(path)
            row[a] = dict(qualified=fit['qualified'], distance_m=ref.distance(fit['coordinates_deg']), score=fit['score'], held_score=fit['held_score'], gradient_max=fit['gradient_max'], derivative_discrepancy=fit['derivative_audit']['discrepancy'], elapsed_s=fit['elapsed_s'], expected_sources=fit['expected_sources'])
        rows.append(row)
    result = dict(rows=rows, gate=evaluate(rows), sources=sources, scope='conditional whole-source model; new causal calibration; same-site previously exposed records')
    with (HERE / 'summary.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps(dict(rows=rows, gate=result['gate']), indent=2))


if __name__ == '__main__':
    main()
