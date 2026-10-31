"""Publish research receipts and figures, excluding raw IQ and interpreter caches."""
from pathlib import Path
import gzip
import hashlib
import json
import re

ROOT=Path(__file__).parent
DEST=Path('/srv/bulk/leo-dev/fast-algo02-production-v1/reports/2026_10_31_ds26_recovery_resolution')

def run():
    DEST.mkdir(parents=True,exist_ok=True)
    mapping={};sources=[]
    allowed={'.py','.md','.png','.pdf','.csv','.json','.log'}
    for src in sorted(ROOT.rglob('*')):
        if not src.is_file() or '__pycache__' in src.parts or src.suffix not in allowed:continue
        if 'raw-panel' in src.parts:continue
        rel=src.relative_to(ROOT);dst=DEST/rel;data=src.read_bytes()
        sources.append(dict(source=str(src),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
        if src.suffix=='.csv':data=data.replace(b'\r\n',b'\n')
        if src.suffix=='.json' and len(data)>300000:
            dst=dst.with_name(dst.name+'.gz');data=gzip.compress(data,mtime=0)
        dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(data)
        mapping[str(rel)]=str(dst.relative_to(DEST))
    # Generated navigation follows compressed evidence; original study sources
    # and their seals stay immutable at their recorded absolute paths.
    for md in DEST.rglob('*.md'):
        def replace(match):
            link=match.group(1)
            if '://' in link or link.startswith('#'):return match.group(0)
            target=(md.parent/link).resolve()
            try:rel=str(target.relative_to(DEST.resolve()))
            except ValueError:return match.group(0)
            if mapping.get(rel)==rel+'.gz':return ']('+link+'.gz)'
            return match.group(0)
        md.write_text(re.sub(r'\]\(([^)]+)\)',replace,md.read_text()))
    (DEST/'source-artifact-map.json').write_text(json.dumps(dict(sources=sources,mapping=mapping,raw_IQ_published=False),indent=2)+'\n')
    files=[p for p in DEST.rglob('*') if p.is_file() and p.name!='publication-manifest.json']
    manifest=dict(source_commit='d1f0a83214b44d7dd25d9095b09eabc517cd0aec',
                  production_modified=False,raw_IQ_published=False,
                  artifacts=[dict(path=str(p.relative_to(DEST)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(files)])
    (DEST/'publication-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Published',len(files),'files;',round(sum(p.stat().st_size for p in files)/2**20,2),'MiB')

if __name__=='__main__':run()
