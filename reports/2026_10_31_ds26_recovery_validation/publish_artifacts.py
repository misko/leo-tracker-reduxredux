"""Copy bounded research artifacts to the report; do not mutate inference."""
from pathlib import Path
import gzip
import io
import json
import shutil
import tarfile

ROOT = Path(__file__).parent
DEST = Path('/srv/bulk/leo-dev/fast-algo02-production-v1/reports/2026_10_31_ds26_recovery_validation')

def copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    data = src.read_bytes()
    if src.suffix == '.csv': data = data.replace(b'\r\n', b'\n')
    dst.write_bytes(data)

def archive(folder, target, allowed):
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('wb') as raw, gzip.GzipFile(fileobj=raw,mode='wb',mtime=0) as gz, tarfile.open(fileobj=gz,mode='w') as tar:
        for src in sorted(folder.rglob('*')):
            if not src.is_file() or '__pycache__' in src.parts or not allowed(src):continue
            data=src.read_bytes()
            info=tarfile.TarInfo(str(src.relative_to(folder)));info.size=len(data);info.mode=0o644;info.mtime=0
            tar.addfile(info,io.BytesIO(data))

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    for name in ['audit_phase_cohort.py','run_phase_panel.py','summarize_phase_panel.py','publish_artifacts.py',
                 'phase-cohort-audit.json','phase-cohort-audit.csv','phase-validation-panel.json']:
        copy(ROOT/name,DEST/name)
    for folder in ['incumbent52311','phase0265']:
        base=ROOT/folder
        for src in base.iterdir():
            if src.is_file() and src.suffix in {'.py','.md','.csv','.png','.pdf'}:
                copy(src,DEST/folder/src.name)
        if folder=='incumbent52311':
            for src in base.glob('*.json'):copy(src,DEST/folder/src.name)
        else:
            for src in (base/'figures').glob('*'):copy(src,DEST/folder/'figures'/src.name)
            for relative in ['matched-run01/annotation_summary.json','matched-run01/protocol.json',
                             'shared-run01/reporting_summary.json','shared-run01/inference_seal.json',
                             'shared-run01/terminal.json','shared-run01/protocol.json']:
                copy(base/relative,DEST/folder/relative)
            for name in ['control','target_0','exact_owner_replay']:
                rel=f'shared-run01/reference30/inclusion/{name}.json'
                dst=DEST/folder/(rel+'.gz');dst.parent.mkdir(parents=True,exist_ok=True)
                dst.write_bytes(gzip.compress((base/rel).read_bytes(),mtime=0))
        archive(base,DEST/folder/'raw-evidence.tar.gz',lambda p:p.suffix in {'.json','.log'})
    for src in (ROOT/'receiver').glob('*.py'):copy(src,DEST/'receiver'/src.name)
    for src in (ROOT/'receiver/results-v3').iterdir():
        if src.is_file():copy(src,DEST/'receiver/results-v3'/src.name)
    base=ROOT/'phase-panel'
    for src in base.iterdir():
        if src.is_file():copy(src,DEST/'phase-panel'/src.name)
    archive(base,DEST/'phase-panel/raw-evidence.tar.gz',lambda p:p.suffix in {'.json','.log','.py'})
    print(DEST)

if __name__=='__main__':main()
