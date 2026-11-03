"""Apply the baseline numerical audit, then reference scoring, to a variant directory."""
import argparse
import importlib.util
import json
from pathlib import Path
from evaluate_pilot import audit
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def evaluate(directory):
    rows, states, freeze_hash = audit(directory)
    ref_path = HERE/'reference-admission-v1.json'
    assert digest(ref_path) == ref_path.with_suffix('.sha256').read_text().strip()
    references = json.loads(ref_path.read_text()); verify_sources(references['source_sha256'])
    reference = {r['unit']:r['reference_latlon'] for r in references['rows']}
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == 'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec = importlib.util.spec_from_file_location('offline_geo', helper)
    geo = importlib.util.module_from_spec(spec); spec.loader.exec_module(geo)
    for row in rows:
        locations = [reference[u] for u in row['scans']]
        assert all(p == locations[0] for p in locations)
        row['error_m'] = geo.distance_m(geo.latlon_from_enu(*states[row['unit']]),locations[0]) if row['accepted'] else None
    result = dict(rows=rows, freeze_sha256=freeze_hash, evaluator_sha256=digest(__file__),
        reference_sha256=digest(ref_path), qualification='Variant audit; infer timing scope and constituent costs from sealed launch receipts. Reference scoring follows numerical decisions. Development evidence only.')
    output = directory/'evaluation.json'
    with output.open('x') as stream: json.dump(result,stream,indent=2,allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(rows,indent=2),flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('directory',type=Path)
    evaluate(parser.parse_args().directory)
