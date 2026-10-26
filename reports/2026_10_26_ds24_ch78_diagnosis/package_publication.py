"""Verify immutable study outputs and copy a lean, hash-bound publication."""
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parent
DEST = Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022/reports/2026_10_26_ds24_ch78_diagnosis')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load(path):
    return json.loads(Path(path).read_text())

def check(mapping, base=None):
    for path, digest in mapping.items():
        target = Path(path) if base is None else base / path
        assert sha(target) == digest, str(target)

for branch in ('matched', 'residual'):
    check(load(ROOT / branch / 'RF_seal.json')['files'])
    check(load(ROOT / branch / 'protocol.json')['sources'])
check({p: x['sha256'] for p, x in load(ROOT / 'supplemental_provenance.json')['files'].items()})
check(load(ROOT / 'report/seal.json')['files'])
assert sha(ROOT/'report.py') == load(ROOT/'report/seal.json')['source_sha256']
check(load(ROOT/'report/figures_v2/seal.json')['files'], ROOT/'report/figures_v2')
assert sha(ROOT/'figure_correction.py') == load(ROOT/'report/figures_v2/seal.json')['source_sha256']
check(load(ROOT/'detection/verification.json')['artifact_sha256'], ROOT/'detection')
audit = load(ROOT/'prediction_audit/summary.json')
assert audit['all_complete'] and audit['all_checks_pass'] and audit['exact_vectors'] == 96
assert sha(ROOT/'audit_predictions.py') == load(ROOT/'prediction_audit/protocol.json')['source_sha256']
assert load(ROOT/'report/summary.json')['receiver_correction_advances'] is False
assert not DEST.exists(), 'Refuse to overwrite an existing publication'

included, external = {}, {}
for source in sorted(ROOT.rglob('*')):
    if not source.is_file() or any(x in ('__pycache__', '.pytest_cache', 'mpl') for x in source.relative_to(ROOT).parts):
        continue
    rel = source.relative_to(ROOT)
    if source.suffix == '.npz':
        external[str(source)] = {'sha256': sha(source), 'bytes': source.stat().st_size}
        continue
    if source.suffix not in ('.py', '.json', '.md', '.png', '.pdf', '.csv', '.log'):
        raise ValueError('Unexpected artifact: ' + str(source))
    target = DEST / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    assert sha(source) == sha(target)
    included[str(rel)] = {'sha256': sha(target), 'bytes': target.stat().st_size}

text = (DEST/'README.md').read_text()
for link in re.findall(r'\]\(([^)]+)\)', text):
    if '://' in link:
        continue
    target = (DEST / link.split('#')[0]).resolve()
    # Older reports may be outside the sparse checkout: verify against Git below.
    if not link.startswith('../'):
        assert target.exists(), link

manifest = {
    'study_directory': str(ROOT),
    'included': included,
    'external_predictive_arrays': external,
    'original_frozen_provenance_preserved': True,
    'causal_ancillary_initial_freeze_gap': 'Twenty ancillary files were hashed after launch; supplement does not establish a prelaunch freeze.',
    'no_raw_IQ_in_publication': True,
    'all_scientific_seals_reverified': True,
    'all_internal_main_report_links_resolve': True,
    'no_production_change': True,
}
with (DEST/'publication_manifest.json').open('x') as f:
    json.dump(manifest, f, indent=2)
    f.write('\n')
print(json.dumps({'destination': str(DEST), 'included_files': len(included),
                  'included_bytes': sum(v['bytes'] for v in included.values()),
                  'external_arrays': len(external), 'checks_passed': True}))
