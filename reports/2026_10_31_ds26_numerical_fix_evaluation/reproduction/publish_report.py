"""Package the sealed comparison and compact evidence; leave RF arrays local."""
from pathlib import Path
import gzip
import hashlib
import json

ROOT=Path(__file__).resolve().parent
DEST=Path('/srv/bulk/leo-dev/fast-algo02-production-v1/reports/2026_10_31_ds26_numerical_fix_evaluation')

def run():
    DEST.mkdir(parents=True,exist_ok=False)
    mapping=[]
    def copy(src,relative):
        data=src.read_bytes();dst=DEST/relative
        before=hashlib.sha256(data).hexdigest()
        if src.suffix=='.csv':data=data.replace(b'\r\n',b'\n')
        if src.suffix=='.json' and len(data)>300000:
            dst=dst.with_name(dst.name+'.gz');data=gzip.compress(data,mtime=0)
        dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(data)
        mapping.append(dict(source=str(src),source_sha256=before,published=str(dst.relative_to(DEST)),
                            published_sha256=hashlib.sha256(data).hexdigest()))
    for p in sorted((ROOT/'report-draft').iterdir()):
        if p.is_file() and p.name != 'DRAFT.md':copy(p,p.name)
    for p in sorted(ROOT.iterdir()):
        if 'preliminary' in p.name:continue
        if p.is_file() and (p.suffix in {'.py','.md'} or p.name in {
            'dataset-protocol.json','source-freeze.json','full-launch.json','final-dataset-seal.json',
            'cache-review.json','numerical-audit.json','recovery-gain-audit.json','test-summary.json'}):
            copy(p,Path('reproduction')/p.name)
    for case in sorted((ROOT/'cases').iterdir()):
        for name in ('receipt.json','protocol.json','outcome.json','inference-seal.json'):
            p=case/name
            if p.exists():copy(p,Path('case-receipts')/case.name/name)
    (DEST/'artifact-map.json').write_text(json.dumps(mapping,indent=2)+'\n')
    files=[p for p in DEST.rglob('*') if p.is_file()]
    (DEST/'publication-manifest.json').write_text(json.dumps({
        'raw_IQ_included':False,'production_changed':False,
        'files_sha256':{str(p.relative_to(DEST)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}},indent=2)+'\n')
    print(len(files),'files',round(sum(p.stat().st_size for p in files)/2**20,2),'MiB')

if __name__=='__main__':run()
