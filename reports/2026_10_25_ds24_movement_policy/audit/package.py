"""Prepare verified release assets and a compact report inventory; never push."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
OUT=HERE/'publication'
TAG='research-ds24-movement-policy-r01-20261025'
RELEASE='https://github.com/misko/leo-tracker-reduxredux/releases/download/'+TAG+'/'
LIMIT=45_000_000


def read(path):return json.loads(Path(path).read_text())
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def archive(name,files,compressed=False):
    target=OUT/'assets'/name
    records=[dict(source=str(source),member=str(member),bytes=Path(source).stat().st_size,sha256=sha(source)) for source,member in files]
    if not target.exists():
        with target.open('xb') as raw:
            zipped=gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0,compresslevel=6) if compressed else raw
            with tarfile.open(fileobj=zipped,mode='w|') as output:
                for source,member in files:
                    source=Path(source);entry=tarfile.TarInfo(str(member))
                    entry.size=source.stat().st_size;entry.mode=0o644;entry.mtime=0
                    with source.open('rb') as stream:output.addfile(entry,stream)
            if compressed:zipped.close()
    assert target.stat().st_size<50_000_000,(name,target.stat().st_size)
    with tarfile.open(target,'r:gz' if compressed else 'r:') as check:
        actual=list(check)
        assert [m.name for m in actual]==[r['member'] for r in records]
        for member,record in zip(actual,records,strict=True):
            h=hashlib.sha256()
            with check.extractfile(member) as stream:
                for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
            assert h.hexdigest()==record['sha256']
    result=dict(asset=name,url=RELEASE+name,bytes=target.stat().st_size,sha256=sha(target),members=records,
        compression='gzip' if compressed else 'none; member NPZ files already compressed')
    print('asset',name,result['bytes'],len(records),flush=True)
    return result


def main():
    for name in ('movement_artifacts.json','recovery_artifacts.json','reporting_audit.json'):
        assert read(HERE/name)['status']=='passed'
    assert not (OUT/'package_inventory.json').exists(),'Preserve a finalized artifact inventory'
    (OUT/'assets').mkdir(parents=True,exist_ok=True)
    archives=[];raw=set()
    cases=read(ROOT/'protocol.json')['cases']
    for case in cases:
        files=sorted((ROOT/'movement/arrays').glob(case+'_*.npz'))+sorted((ROOT/'movement/results').glob(case+'_*.json'))
        assert len(files)==54,(case,len(files))
        groups=[];group=[];size=10240
        for path in files:
            added=((path.stat().st_size+511)//512)*512+512
            if size+added>LIMIT and group:
                groups.append(group);group=[];size=10240
            group.append(path);size+=added
        if group:groups.append(group)
        for part,group in enumerate(groups,1):
            archives.append(archive(f'movement_{case}_part{part:02d}.tar',[(p,p.relative_to(ROOT)) for p in group]))
            raw.update(group)
    metadata=[];recovery=[];direct=[]
    ignored={'__pycache__','.pytest_cache','.mpl','mpl','publication'}
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or path in raw:continue
        rel=path.relative_to(ROOT)
        if set(rel.parts)&ignored:continue
        if rel.parts[:2] in (('movement','claims'),('movement','receipts'),('movement','logs'),('audit','movement_cases'),('evaluation','initial_reporting')):
            metadata.append((path,rel));continue
        if rel in (Path('movement/input_manifest.json'),Path('audit/baseline_membership.json')) or path.name.endswith('_svd.log'):
            metadata.append((path,rel));continue
        if rel.parts[0]=='recovery' and (any(part.startswith('DS24-') for part in rel.parts[1:]) and
            ('diagnostics' not in str(rel) and 'report_native03' not in str(rel))):
            recovery.append((path,rel));continue
        if rel.parts[0]=='recovery' and path.name.endswith('_DBG01.png') and 'native' not in path.name:
            recovery.append((path,rel));continue
        if path.suffix not in ('.py','.md','.json','.csv','.png','.txt','.log'):continue
        assert path.stat().st_size<10_000_000,('Unexpected bulky direct file',str(rel),path.stat().st_size)
        direct.append(dict(source=str(path),published=str(rel),sha256=sha(path),bytes=path.stat().st_size))
    archives.append(archive('shared_scientific_metadata.tar.gz',metadata,compressed=True))
    for case in ('DS24-0095','DS24-0087'):
        for kind in ('original','support_versions'):
            group=[(p,rel) for p,rel in recovery if case in rel.parts and
                ((rel.parts[1] in ('repair01','eligibility02')) == (kind=='support_versions'))]
            archives.append(archive(f'recovery_{case}_{kind}.tar.gz',group,compressed=True))
    sources=read(HERE/'runtime_source_inventory.json')['files']
    for item in sources:assert sha(item['path'])==item['sha256']
    archives.append(archive('actual_runtime_source_capsule.tar.gz',[(Path(r['path']),Path(r['member'])) for r in sources],compressed=True))
    plan=read(ROOT/'protocol.json')['plan']
    assert sha(plan['path'])==plan['sha256']
    direct.append(dict(source=plan['path'],published='execution_plan.md',sha256=plan['sha256'],bytes=Path(plan['path']).stat().st_size))
    output=dict(status='prepared_not_published',release_tag=TAG,
        release_title='DS24 movement policy r01 raw research evidence',
        release_target='Final reviewed report commit on remote main',
        report_directory='reports/2026_10_25_ds24_movement_policy',
        source_sha256=sha(Path(__file__)),assets=archives,direct_files=direct,
        asset_count=len(archives),asset_bytes=sum(a['bytes'] for a in archives),
        largest_asset_bytes=max(a['bytes'] for a in archives),
        git_direct_file_count=len(direct),git_direct_bytes=sum(r['bytes'] for r in direct),
        raw_IQ_included=False,all_1152_covariance_vectors_preserved=True,
        external_actual_runtime_sources=len(sources),unused_broad_source_bytes_excluded=True,
        deterministic_tar_metadata=True,all_members_roundtrip_hash_verified=True,
        recovery_reporting='Native03 plots are primary; mixed-coordinate superseded DBG01 images retained only inside raw archive',
        source_capsule='Exact actual imported sources, including explicitly authorized three dirty imported snapshots; production checkout unchanged')
    with (OUT/'package_inventory.json').open('x') as stream:json.dump(output,stream,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in output.items() if k not in ('assets','direct_files')},indent=2))


if __name__=='__main__':main()
