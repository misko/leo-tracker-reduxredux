"""Compact archive inventory for the completed three-branch wave; no fits."""

import gzip
import hashlib
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parent
OUTPUT=Path('/srv/bulk/leo/research/ds24-fast-identifiability-publication-r01')
REPORT='reports/2026_10_25_ds24_fast_identifiability'
TAG='research-ds24-fast-identifiability-r01-20261025'
GROUPS={
    'receiver_contrasts_raw.tar.gz':('receiver_contrasts/cases/',),
    'synthetic_raw.tar.gz':('synthetic/fits/','synthetic/execution.json'),
    'transfer_raw.tar.gz':('transfer/fits/','transfer/ownership/','transfer/preflight/'),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def eligible(path):
    rel=path.relative_to(ROOT)
    return path.is_file() and not any(v.startswith('.') or v=='__pycache__' for v in rel.parts) and rel.name not in ('publication_index.json','publication_receipt.json') and path.suffix!='.pyc'


def main():
    (OUTPUT/'assets').mkdir(parents=True,exist_ok=True)
    branches={}
    for branch in ('receiver_contrasts','synthetic','transfer'):
        protocol=read(ROOT/branch/'protocol.json')
        names=('file_sha256',) if branch=='receiver_contrasts' else ('input_sha256','source_sha256')
        branches[branch]=dict(protocol_sha256=sha(ROOT/branch/'protocol.json'),
            declared_bindings={name:protocol[name] for name in names},
            scope='Declared protocol bindings; no new runtime/source discovery campaign.')
    (ROOT/'input_bindings.json').write_text(json.dumps(dict(branches=branches,
        prior_reports=[dict(commit='82e608d8d3b254e737326058e601a4775f231135',report='reports/2026_10_25_ds24_movement_policy'),
            dict(commit='7c11ca70240bbb029c2cb070992f3baa2979f288',report='reports/2026_10_25_ds24_new_family_uncertainty')],
        replay_limit='Exact original frozen local DS25 corpus, prior source snapshots and third-party environment remain prerequisites. This publication supplies all new outputs/source, not all24 original sky banks or a new full runtime capsule.',
        no_raw_IQ=True),indent=2)+'\n')
    files=[p for p in sorted(ROOT.rglob('*')) if eligible(p)]
    assets=[];archived=set()
    for name,prefixes in GROUPS.items():
        members=[p for p in files if str(p.relative_to(ROOT)).startswith(prefixes) and p.name!='README.md']
        destination=OUTPUT/'assets'/name
        with destination.open('wb') as raw:
            with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0,compresslevel=6) as stream:
                with tarfile.open(fileobj=stream,mode='w') as tar:
                    for path in members:
                        member=str(path.relative_to(ROOT));info=tarfile.TarInfo(member)
                        info.size=path.stat().st_size;info.mode=0o644;info.mtime=0
                        with path.open('rb') as source:tar.addfile(info,source)
                        archived.add(member)
        inventory=[]
        with tarfile.open(destination,'r:gz') as tar:
            for member in tar.getmembers():
                data=tar.extractfile(member).read()
                digest=hashlib.sha256(data).hexdigest()
                assert digest==sha(ROOT/member.name)
                inventory.append(dict(member=member.name,sha256=digest,bytes=len(data)))
        assert len(inventory)==len(members) and destination.stat().st_size<45_000_000
        assets.append(dict(asset=name,bytes=destination.stat().st_size,sha256=sha(destination),
            url=f'https://github.com/misko/leo-tracker-reduxredux/releases/download/{TAG}/{name}',members=inventory))
    direct=[dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=sha(p)) for p in files if str(p.relative_to(ROOT)) not in archived]
    index=dict(status='verified_archive_inventory',report_directory=REPORT,release_tag=TAG,
        release_title='DS24 fast identifiability r01 research evidence',assets=assets,asset_count=len(assets),
        asset_bytes=sum(v['bytes'] for v in assets),archived_members=sum(len(v['members']) for v in assets),
        direct_files=direct,direct_file_count=len(direct),direct_bytes=sum(v['bytes'] for v in direct),
        no_raw_IQ=True,no_new_fits_during_packaging=True,all_members_roundtrip_hash_verified=True,
        source_sha256=sha(Path(__file__)),README_sha256=sha(ROOT/'README.md') if (ROOT/'README.md').exists() else None)
    (ROOT/'publication_index.json').write_text(json.dumps(index,indent=2)+'\n')
    receipt=dict(all_passed=True,index_sha256=sha(ROOT/'publication_index.json'),
        assets=[{k:v[k] for k in ('asset','bytes','sha256')} for v in assets],archived_members=index['archived_members'],
        direct_file_count=len(direct)+1,direct_bytes=index['direct_bytes']+(ROOT/'publication_index.json').stat().st_size,
        asset_bytes=index['asset_bytes'],no_new_fits=True)
    (OUTPUT/'archive_validation.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':
    main()
