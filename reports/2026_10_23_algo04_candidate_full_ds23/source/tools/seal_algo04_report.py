"""Package completed numerical evidence and a research source capsule."""
from pathlib import Path
import ast
import hashlib
import json
import shutil
import tarfile

OUT=Path(__file__).resolve().parents[2]
ROOT=Path('/home/mouse9911/gits/leo-tracker-reduxredux')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,data):path.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')


def main():
    assert json.loads((OUT/'execution.json').read_text())['all_passed']
    assert (OUT/'README.md').exists()
    sources=OUT/'source/tools';upstream=OUT/'source/upstream_tools';upstream.mkdir(exist_ok=True)
    queue=list(sources.glob('*.py'));seen=set()
    while queue:
        source=queue.pop();name=source.stem
        if name in seen:continue
        seen.add(name)
        tree=ast.parse(source.read_text());imports=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imports.extend(x.name.split('.')[0] for x in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:imports.append(node.module.split('.')[0])
        for module in imports:
            origin=ROOT/'tools'/(module+'.py');target=upstream/origin.name
            if origin.exists() and module not in seen:
                if not target.exists():shutil.copyfile(origin,target)
                queue.append(target)
    write(OUT/'evidence/source_hashes.json',{str(p.relative_to(OUT)):digest(p) for p in sorted((OUT/'source').rglob('*.py'))})
    cases=json.loads((OUT/'protocol.json').read_text())['cases'];archives=[]
    for start in range(0,len(cases),10):
        chunk=cases[start:start+10];target=OUT/'evidence'/f'case_results_{start//10:02d}.tar.gz';count=0
        with tarfile.open(target,'w:gz') as archive:
            for case in chunk:
                folder=OUT/'raw'/case
                # Result has paired reference, graph and final fits, masks,
                # accepted IDs, histories, and independent numerical audits.
                # Full proposal covariance dumps remain on bulk storage;
                # publish final paired fits and every failed-attempt receipt.
                for p in sorted(folder.rglob('result.json')):
                    archive.add(p,arcname=str(p.relative_to(OUT)),recursive=False);count+=1
        assert target.stat().st_size<45*1024**2,'split this archive further'
        archives.append(dict(file=str(target.relative_to(OUT)),cases=chunk,files=count,bytes=target.stat().st_size,sha256=digest(target)))
    write(OUT/'evidence/archive_manifest.json',archives)
    for p in OUT.glob('*.json'):shutil.copyfile(p,OUT/'evidence'/p.name)
    for name in ['tests.txt','canary.log','full_run.log','legacy_audit_validation.log']:
        p=OUT/name
        if p.exists():shutil.copyfile(p,OUT/'evidence'/p.name)
    lines=['# ALGO04 candidate figure inventory','']
    for p in sorted((OUT/'figures').glob('*.png')):lines.extend([f'## {p.stem.replace("_"," ")}','',f'![{p.stem}](figures/{p.name})',''])
    (OUT/'FIGURES.md').write_text('\n'.join(lines))
    print('Packaged',len(archives),'evidence archives and',len(seen),'tool sources')


if __name__=='__main__':main()
