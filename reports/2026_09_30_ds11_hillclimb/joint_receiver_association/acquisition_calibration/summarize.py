"""Preserve all family transfer screens, including unsupported settings."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    sources = {}
    rows = []
    inventory = json.loads((HERE.parent / 'acquisition-calibration-inventory.json').read_text())
    for number in range(8):
        path = HERE / f'fit-{number}.json'
        fit = json.loads(path.read_text())
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        for p, h in fit['sources'].items():
            assert hashlib.sha256(Path(p).read_bytes()).hexdigest() == h, p
        f = inventory['families'][number]
        rows.append(dict(family=number, sample_rate_hz=f['sample_rate_hz'], rf_hz=f['rf_hz'], screen=fit['screen'], validation_count=fit['validation']['receiver']['count'], validation_scores={a: v['score'] for a, v in fit['validation'].items()}, controls=fit['controls'], geometry_slope=fit['arms']['signed']['selected']['parameters'][-1], all_fits_qualified=all(v['selected']['qualified'] for v in fit['arms'].values()), original_targets=[r['index'] for r in f['original']], additional_targets=[r['index'] for r in f['additional']]))
    passed = [r for r in rows if r['screen']['passed']]
    result = dict(families=rows, passing_families=[r['family'] for r in passed], passing_original_coverage=sum(len(r['original_targets']) for r in passed), passing_additional_coverage=sum(len(r['additional_targets']) for r in passed), position_improvement_tested=False, sources={**sources, str(Path(__file__)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    with (HERE / 'summary.json').open('x') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
