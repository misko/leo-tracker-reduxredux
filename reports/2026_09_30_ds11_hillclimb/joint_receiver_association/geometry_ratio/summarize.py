"""Score the terminal likelihood-ratio pilot, including all fallback records."""
import importlib.util
import json
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'acquisition_position'))
from common import JOBS, base, read, digest, verify_sources
from gate import evaluate


def main():
    sources = {str(p): digest(p) for p in (Path(__file__), HERE / 'PROTOCOL.md', HERE.parent / 'acquisition_position/gate.py')}
    receipts = {}
    for c, i, _ in JOBS:
        for a in ('doppler', 'candidate'):
            path = HERE / f'fit-{c}-{i:02d}-{a}.receipt.json'
            receipt = read(path)
            assert digest(path.with_name(path.name.replace('.receipt.json', '.log'))) == receipt['log_sha256']
            assert digest(HERE / 'run.py') == receipt['runner_sha256']
            receipts[c, i, a] = receipt
            sources[str(path)] = digest(path)
    reference_path = base('original') / 'summarize.py'
    spec = importlib.util.spec_from_file_location('reference_metrics', reference_path)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    sources[str(reference_path)] = digest(reference_path)
    rows = []
    for c, i, family in JOBS:
        original = base(c) / f'runs/{i:02d}_iid.json'
        sources[str(original)] = digest(original)
        row = dict(cohort=c, index=i, family=family, original=dict(distance_m=reference.distance(read(original)['selected']['estimate_deg'])))
        for arm, key in [('doppler', 'doppler'), ('candidate', 'signed')]:
            receipt = receipts[c, i, arm]
            path = HERE / f'fit-{c}-{i:02d}-{arm}.json'
            if receipt['exit_code'] != 0 or not path.exists():
                row[key] = dict(qualified=False, exit_code=receipt['exit_code'])
                continue
            fit = read(path)
            verify_sources(fit)
            sources[str(path)] = digest(path)
            row[key] = dict(qualified=fit['qualified'], distance_m=reference.distance(fit['coordinates_deg']), held_score=fit['held_score'], gradient_max=fit['gradient_max'], derivative_discrepancy=fit['derivative_audit']['discrepancy'], elapsed_s=fit['elapsed_s'], selected_arm=fit['selected_arm'], fallback=fit['fallback'])
        rows.append(row)
    result = dict(rows=rows, gate=evaluate(rows), sources=sources, scope='signed key denotes calibrated geometry likelihood-ratio composite including Doppler fallback; all original panel records retained')
    with (HERE / 'summary.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps(dict(rows=rows, gate=result['gate']), indent=2))


if __name__ == '__main__':
    main()
