"""Verify and publish a lean immutable research snapshot; no RF or fits."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parent
DEST=Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022/reports/2026_10_26_ds24_guided_acquisition_geometry')

def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def check(mapping,base=None):
    for p,digest in mapping.items():
        target=Path(p) if base is None else base/p
        assert sha(target)==digest,str(target)

check(load(ROOT/'detection/RF_seal.json')['files'],ROOT/'detection')
check(load(ROOT/'detection/lean_manifest.json')['files'],ROOT/'detection')
assert load(ROOT/'detection/verification.json')['all_passed']
check(load(ROOT/'localization/RF_seal.json')['files'])
check(load(ROOT/'localization/protocol.json')['sources'])
check(load(ROOT/'localization/report/seal.json')['files'])
assert sha(ROOT/'localization/report.py')==load(ROOT/'localization/report/seal.json')['source_sha256']
execution=load(ROOT/'localization/execution.json')
assert len(execution['fits'])==14 and len(execution['scores'])==10
assert all(r['status']=='complete' for r in execution['fits']+execution['scores'])
assert all(r['original_full_endpoint_exact'] for r in execution['fits'] if r['method']=='full')
assert all(x['checks']['checks_pass'] for r in execution['scores'] for x in r['endpoints'].values())
assert {r['method'] for r in execution['fits'] if not r['training_checks_pass']}=={'plus_A'}

repo='/home/mouse9911/gits/leo-tracker-reduxredux'
working_diff=hashlib.sha256(subprocess.check_output(['git','diff','--binary'],cwd=repo)).hexdigest()
assert working_diff=='add0a0f9598b5045dbf6dd6eb05b744b856715c01a9cb3101f6890b999029a4b'
assert not DEST.exists(),'Refuse to overwrite publication'
included={}
for source in sorted(ROOT.rglob('*')):
    if not source.is_file() or any(x in ('__pycache__','.pytest_cache','mpl') for x in source.relative_to(ROOT).parts):
        continue
    relative=source.relative_to(ROOT)
    if source.suffix not in ('.md','.py','.json','.csv','.png','.pdf','.log'):
        raise ValueError('Unexpected file type: '+str(source))
    target_relative=relative
    if str(relative)=='localization/test_cache_redaction.py':
        target_relative=Path('localization/audit/archived_test_cache_redaction.py.txt')
    target=DEST/target_relative;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target);assert sha(source)==sha(target)
    included[str(target_relative)]=dict(sha256=sha(target),bytes=target.stat().st_size,
                                      original_path=str(source))
for link in re.findall(r'\]\(([^)]+)\)',(DEST/'README.md').read_text()):
    if '://' in link or link.startswith('../'):continue
    assert (DEST/link.split('#')[0]).exists(),link
manifest=dict(included=included,all_scientific_seals_reverified=True,original_tracked_diff_unchanged=working_diff,
    production_changes=False,raw_IQ_included=False,new_RF=False,
    owned_tests_passed=dict(detection=6,localization=3),
    localized_solver_limit_cases=['plus_A c0 first refresh','plus_A fitted_c first refresh'],
    archived_test_note='Initial supplementary dictionary-equality test retained verbatim as .txt to avoid collecting it; fresh-instance v2 is the active passing regression test.',
    study_directory=str(ROOT))
with (DEST/'publication_manifest.json').open('x') as f:json.dump(manifest,f,indent=2);f.write('\n')
print(json.dumps(dict(destination=str(DEST),files=len(included)+1,bytes=sum(x['bytes'] for x in included.values()),checks_passed=True)))
