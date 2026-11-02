"""Plot-only redraw and publication inventory; never reconstruct or fit RF data."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

import numpy as np

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publication_manifest():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    manifest['source_sha256']['finalize.py'] = sha(ROOT / 'finalize.py')
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
    allowed, excluded = [], []
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or path.name == 'publication_manifest.json':
            continue
        row = dict(path=str(path.relative_to(ROOT.parent)), sha256=sha(path), bytes=path.stat().st_size)
        (excluded if '__pycache__' in path.parts or path.suffix in ('.pyc', '.log') else allowed).append(row)
    (ROOT / 'publication_manifest.json').write_text(json.dumps(dict(
        allowlist=allowed, excluded=excluded, no_refit=True,
        data_scope='All exported native rows and conditional covariance factors retained',
        no_production_changes=True), indent=2) + '\n')


def main():
    began = time.monotonic()
    spec = importlib.util.spec_from_file_location('native_render_final', ROOT / 'render.py')
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    grouped = {}
    summary = []
    for path in sorted((ROOT / 'arrays').glob('*.json')):
        record = json.loads(path.read_text())
        arrays_path = path.with_suffix('.npz')
        if sha(arrays_path) != record['npz_sha256']:
            raise ValueError('Exported arrays changed')
        with np.load(arrays_path, allow_pickle=False) as source:
            arrays = {key: source[key] for key in source.files}
        grouped.setdefault((record['case'], record['split'], record['target_family']), []).append(
            (record['SD_scale'], arrays, record))
        summary.append({key: record[key] for key in ('case', 'split', 'SD_scale', 'held_points',
            'saved_numerical_fit_qualified', 'saved_unqualified_reasons', 'objective_delta', 'held_unbounded_score_delta')})
    for (case, split, target), endpoints in grouped.items():
        renderer.render(case, split, target, sorted(endpoints, key=lambda item: item[0]), ROOT / 'figures')
    manifest.setdefault('execution_source_sha256', manifest['source_sha256'].copy())
    manifest['source_sha256']['render.py'] = sha(ROOT / 'render.py')
    manifest['source_sha256']['finalize.py'] = sha(ROOT / 'finalize.py')
    manifest['plot_only_finalization'] = dict(seconds=time.monotonic() - began,
        reason='Accurate graph-branch label: graph CFO can already be unwrapped',
        RF_reconstruction=False, optimization=False)
    manifest['endpoint_summary'] = summary
    manifest['exported_endpoints'] = len(summary)
    manifest['qualified_endpoints'] = sum(row['saved_numerical_fit_qualified'] for row in summary)
    manifest['held_rows_across_endpoints'] = sum(row['held_points'] for row in summary)
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
    publication_manifest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-only', action='store_true')
    args = parser.parse_args()
    if args.manifest_only:
        publication_manifest()
    else:
        main()
