#!/usr/bin/env python3
"""Create a lean, verified publication tree after all experiments finish.

This helper is intentionally not executed during active benchmarking.  DEST must
be an existing isolated checkout outside this repository's reports tree.
"""
from __future__ import annotations
import argparse,gzip,hashlib,io,json,shutil,tarfile
from pathlib import Path

HERE=Path(__file__).resolve().parent; REPORTS=HERE.parent
EXPERIMENTS=(
 '2026_09_29_arm_frame_budget','2026_09_29_arm_integrated_scorer',
 '2026_09_29_arm_padded_proposal','2026_09_29_arm_neon_proposal',
 '2026_09_29_arm_proposal_planner','2026_09_29_arm_decimated_proposal',
 '2026_09_29_arm_coarse_budget','2026_09_29_arm_conditioned_moments',
 '2026_09_29_arm_float_scorer','2026_09_29_arm_float_glrt_fft',
 '2026_09_29_arm_final_reuse','2026_09_29_arm_resampled_proposal',
 '2026_09_29_arm_proposal_features',
 '2026_09_29_arm_subsecond')
TOP_SUFFIXES={'.py','.md','.c','.h'}
JSON_NAMES={'manifest.json','summary.json','standard-audit.json','build-receipt.json',
 'build.json','results.json','selection.json','arm-units.json','audit.json',
 'precision-comparison.json','target-preflight.json','publication-manifest.json'}
SOURCE_CATALOG:dict[str,Path]={};SOURCE_LOCATIONS:dict[tuple[str,str],Path]={}

def sha_bytes(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def sha(path:Path)->str:return sha_bytes(path.read_bytes())
def excluded(path:Path)->bool:
    return '__pycache__' in path.parts or path.name=='rows.jsonl' or path.suffix in {'.pyc','.npy','.npz','.ci16'}
def cohort_complete(path:Path)->bool:
    manifest=path.parent/'manifest.json'
    if not manifest.is_file():return True
    try:return json.loads(manifest.read_text()).get('complete') is not False
    except Exception:return False
def keep_json(path:Path,experiment_root:Path)->bool:
    name=path.name
    return (path.parent==experiment_root or name in JSON_NAMES or
            any(token in name for token in ('audit','manifest','summary','receipt','unit','qualification','collector')))
def is_receipt(path:Path)->bool:
    return path.name in {'build.json','build-receipt.json'}
def build_source_catalog()->None:
    for experiment in EXPERIMENTS:
        root=REPORTS/experiment
        if not root.is_dir():continue
        for source in root.rglob('*'):
            if source.is_file() and source.suffix in {'.c','.h'} and not excluded(source):
                SOURCE_CATALOG.setdefault(sha(source),source)
def receipt_sources(receipt:Path,data:dict)->dict[str,str]:
    declared=data.get('sources')
    if isinstance(declared,dict):
        result={}
        for relative,expected in declared.items():
            relative_path=Path(relative)
            if relative_path.is_absolute() or '..' in relative_path.parts:raise RuntimeError(f'{receipt}: unsafe source path {relative}')
            source=receipt.parent/relative
            if not source.is_file():source=SOURCE_CATALOG.get(expected,Path())
            if not source.is_file():raise RuntimeError(f'{receipt}: missing declared source {relative}')
            actual=sha(source)
            if actual!=expected:raise RuntimeError(f'{receipt}: source hash mismatch {relative}: {actual} != {expected}')
            result[str(Path(relative))]=actual
            SOURCE_LOCATIONS[(str(receipt),str(Path(relative)))]=source
        return result
    expected=data.get('source_sha256')
    if isinstance(expected,str):
        candidates=[]
        command=data.get('command',[])
        if isinstance(command,list):candidates=[Path(x) for x in command if isinstance(x,str) and x.endswith(('.c','.h'))]
        candidates += sorted(receipt.parent.glob('*.c'))
        for candidate in candidates:
            source=candidate if candidate.is_absolute() else receipt.parent/candidate
            if source.is_file() and sha(source)==expected:
                SOURCE_LOCATIONS[(str(receipt),source.name)]=source
                return {source.name:expected}
        source=SOURCE_CATALOG.get(expected)
        if source:
            SOURCE_LOCATIONS[(str(receipt),source.name)]=source
            return {source.name:expected}
        raise RuntimeError(f'{receipt}: no source matches source_sha256')
    return {}
def snapshot_id(files:dict[str,str])->str:
    canonical=''.join(f'{name}\0{files[name]}\n' for name in sorted(files)).encode()
    return sha_bytes(canonical)
def write_archive(output:Path,receipt:Path,files:dict[str,str])->None:
    if output.exists():return
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('wb') as raw, gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as zipped, tarfile.open(fileobj=zipped,mode='w') as tar:
        for relative in sorted(files):
            source=SOURCE_LOCATIONS.get((str(receipt),relative),receipt.parent/relative);content=source.read_bytes()
            info=tarfile.TarInfo(relative);info.size=len(content);info.mtime=0;info.mode=0o644;info.uid=info.gid=0;info.uname=info.gname=''
            tar.addfile(info,io.BytesIO(content))
def safe_copy(source:Path,target:Path)->None:
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)

def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument('dest',type=Path,help='existing isolated checkout root');args=parser.parse_args()
    dest=args.dest.resolve();repo=REPORTS.parent.resolve()
    if not dest.is_dir() or dest==repo or repo in dest.parents:raise SystemExit('DEST must be an existing isolated checkout outside the source repository')
    publication=dest/'reports/2026_09_29_arm_subsecond';archives=publication/'source-archives'
    # DEST is disposable publication staging. Remove only the enumerated report
    # directories so tracked or stale binaries/rows cannot survive the lean copy.
    for experiment in EXPERIMENTS:
        target=dest/'reports'/experiment
        if target.exists():shutil.rmtree(target)
    build_source_catalog()
    index={'schema':'arm-subsecond-publication/v1','source_repository':str(repo),'experiments':{},'receipts':{},'archives':{}}
    for experiment in EXPERIMENTS:
        source_root=REPORTS/experiment
        if not source_root.is_dir():continue
        copied=[]
        for source in sorted(source_root.iterdir()):
            if source.is_file() and source.suffix in TOP_SUFFIXES and not excluded(source):
                relative=Path('reports')/experiment/source.name;safe_copy(source,dest/relative);copied.append(str(relative))
        json_files=[]
        for source in sorted(source_root.rglob('*.json')):
            if excluded(source) or not keep_json(source,source_root) or not cohort_complete(source):continue
            relative=source.relative_to(repo);safe_copy(source,dest/relative);json_files.append(str(relative))
            if not is_receipt(source):continue
            data=json.loads(source.read_text());files=receipt_sources(source,data)
            archive=None
            if files:
                identity=snapshot_id(files);archive=archives/f'{identity}.tar.gz';write_archive(archive,source,files)
                index['archives'].setdefault(identity,{'path':str(archive.relative_to(dest)),'sha256':sha(archive),'files':files})
            index['receipts'][str(source.relative_to(repo))]={'published_path':str(relative),'receipt_sha256':sha(source),'source_archive':None if archive is None else str(archive.relative_to(dest)),'sources':files}
        index['experiments'][experiment]={'top_level_files':copied,'json_evidence':json_files}
    publication.mkdir(parents=True,exist_ok=True)
    (publication/'publication-index.json').write_text(json.dumps(index,indent=2)+'\n')
    # Copy verification code last so an interrupted run cannot appear complete.
    safe_copy(HERE/'verify_publication.py',publication/'verify_publication.py')
    print(json.dumps({'publication':str(publication),'receipts':len(index['receipts']),'archives':len(index['archives'])},indent=2))
if __name__=='__main__':main()
