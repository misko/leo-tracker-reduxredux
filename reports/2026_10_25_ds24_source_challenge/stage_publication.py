"""Stage exact report bytes after both branch audits; no science or git writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parent
PUBLISHER=Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022')
REPORT='2026_10_25_ds24_source_challenge'
EXCLUDE_DIRS={'publication','__pycache__','.pytest_cache','.git'}
EXCLUDE_FILES={'publication_checks.json','publication_receipt.json','staging_checks.json'}
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
read=lambda path:json.loads(Path(path).read_bytes())


def check_seal(path):
    data=read(path)
    for file,expected in data['files'].items():
        if sha(file)!=expected:raise ValueError('immutable seal mismatch: '+file)


def main(terminal):
    required=['COORDINATOR_PLAN.md','README.md','REPLAY.md','METADATA_FINDINGS.md',
        'metadata_inventory.py','metadata_inventory.json','portions/FINDINGS.md','portions/report/report_seal.json',
        'portions/RF_seal.json','audit/portions_terminal.json','matched_law/RF_seal.json','matched_law/FINDINGS.md','matched_law/report/seal.json']
    for name in required:
        if not (ROOT/name).is_file():raise FileNotFoundError(name)
    for receipt in [ROOT/'audit/portions_terminal.json',terminal]:
        if read(receipt).get('all_passed') is not True:raise ValueError('passing independent terminal receipt required: '+str(receipt))
    if read(terminal).get('protocol_sha256')!=sha(ROOT/'matched_law/protocol.json'):raise ValueError('matched terminal protocol binding')
    for seal in ['portions/RF_seal.json','portions/report/report_seal.json','matched_law/RF_seal.json','matched_law/report/seal.json']:
        check_seal(ROOT/seal)
    stage=ROOT/'publication'
    if stage.exists():raise FileExistsError('preserve previous publication stage')
    stage.mkdir()
    manifest={}
    for source in sorted(ROOT.rglob('*')):
        relative=source.relative_to(ROOT)
        if not source.is_file() or set(relative.parts)&EXCLUDE_DIRS or source.name in EXCLUDE_FILES:continue
        destination=stage/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
        if sha(source)!=sha(destination):raise ValueError('copy changed bytes: '+str(relative))
        manifest[str(relative)]=dict(source=str(source),sha256=sha(source),bytes=source.stat().st_size)
    # Check links against the final report layout, including existing sibling reports.
    checked=[];missing=[]
    for file in sorted(stage.rglob('*.md')):
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',file.read_text()):
            target=target.strip().split(' ',1)[0].strip('<>')
            if not target or target.startswith(('http:','https:','mailto:','#','/')):continue
            target=target.split('#',1)[0]
            relative=(file.relative_to(stage).parent/target)
            local=stage/relative
            final=PUBLISHER/'reports'/REPORT/relative
            exists=local.is_file() or final.is_file()
            resolution='working_tree' if exists else None
            git_path=os.path.normpath(str(Path('reports')/REPORT/relative))
            if not exists and not git_path.startswith('../') and not Path(git_path).is_absolute():
                found=subprocess.run(['git','-C',str(PUBLISHER),'cat-file','-e','HEAD:'+git_path],capture_output=True)
                exists=found.returncode==0
                if exists:resolution='existing_published_HEAD'
            checked.append(dict(file=str(file.relative_to(stage)),target=target,exists=exists,resolution=resolution))
            if not exists:missing.append(checked[-1])
    body=dict(files=manifest,target='reports/'+REPORT,exclusions=sorted(EXCLUDE_DIRS|EXCLUDE_FILES),
        matched_terminal_sha256=sha(terminal),portions_terminal_sha256=sha(ROOT/'audit/portions_terminal.json'),
        source_bytes_preserved=True,new_scientific_computation=False,git_modified=False)
    with (stage/'publication_manifest.json').open('x') as stream:json.dump(body,stream,indent=2);stream.write('\n')
    checks=dict(files=len(manifest),bytes=sum(row['bytes'] for row in manifest.values()),markdown_links=checked,
        missing_links=missing,all_copied_hashes_match=True,ready_for_root_review=not missing,
        git_modified=False,pushed=False,manifest_sha256=sha(stage/'publication_manifest.json'))
    with (ROOT/'staging_checks.json').open('x') as stream:json.dump(checks,stream,indent=2);stream.write('\n')
    print(json.dumps({key:checks[key] for key in ['files','bytes','missing_links','ready_for_root_review','git_modified','pushed']}))
    if missing:raise ValueError('resolve report links before publication; scientific files stay unchanged')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--matched-terminal',required=True,type=Path)
    main(parser.parse_args().matched_terminal)
