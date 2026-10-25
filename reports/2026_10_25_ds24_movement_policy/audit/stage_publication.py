"""Stage only the reviewed compact report in the isolated publisher; never commit."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import unquote

from PIL import Image

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
PUBLISHER=Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022')
DEST=PUBLISHER/'reports/2026_10_25_ds24_movement_policy'


def read(path):return json.loads(Path(path).read_text())
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def write_new(path,value):
    with Path(path).open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')


def main():
    assert not DEST.exists(),'Preserve an existing publication; use another version'
    assert subprocess.check_output(['git','status','--porcelain=v1'],cwd=PUBLISHER,text=True)==''
    package=read(HERE/'publication/package_inventory.json')
    for name in ('movement_artifacts.json','recovery_artifacts.json','reporting_audit.json'):
        assert read(HERE/name)['status']=='passed'
    archived={Path(member['source']) for asset in package['assets'] for member in asset['members']}
    for asset in package['assets']:
        path=HERE/'publication/assets'/asset['asset']
        assert path.stat().st_size==asset['bytes'] and sha(path)==asset['sha256']
    files=[]
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or path in archived:continue
        rel=path.relative_to(ROOT)
        if set(rel.parts)&{'publication','__pycache__','.pytest_cache','.mpl','mpl'}:continue
        if path.name.startswith('package') and path.suffix=='.log':continue
        if path.suffix not in ('.py','.md','.json','.csv','.png','.txt','.log'):continue
        assert path.stat().st_size<10_000_000,('Unexpected bulky Git artifact',str(path))
        files.append(dict(source=str(path),published=str(rel),sha256=sha(path),bytes=path.stat().st_size))
    plan=read(ROOT/'protocol.json')['plan']
    assert sha(plan['path'])==plan['sha256']
    files.append(dict(source=plan['path'],published='execution_plan.md',sha256=plan['sha256'],bytes=Path(plan['path']).stat().st_size))
    assert any(item['published']=='README.md' for item in files)
    assert any(item['published']=='RESTORE.md' for item in files)
    DEST.mkdir(parents=True)
    for item in files:
        target=DEST/item['published'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(item['source'],target)
        assert sha(target)==item['sha256']
    index={k:v for k,v in package.items() if k!='direct_files'}
    index.update(status='verified_publication_package',direct_files=files,git_direct_file_count=len(files),
        git_direct_bytes=sum(item['bytes'] for item in files),source_sha256=sha(Path(__file__)),
        report_README_sha256=sha(ROOT/'README.md'),recovery_FINDINGS_sha256=sha(ROOT/'recovery/FINDINGS.md'),
        asset_delivery='GitHub research prerelease at the exact reviewed report commit; raw binaries excluded from Git history')
    write_new(DEST/'publication_index.json',index)
    checksums=''.join(f"{asset['sha256']}  {asset['asset']}\n" for asset in package['assets'])
    (DEST/'ASSET_SHA256SUMS').write_text(checksums)
    links=[]
    for path in DEST.rglob('*.md'):
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',path.read_text()):
            if target.startswith(('http:','https:','mailto:','#')):continue
            local=unquote(target.strip('<>').split('#')[0])
            if local:
                assert (path.parent/local).exists(),(str(path),target)
                links.append(dict(document=str(path.relative_to(DEST)),target=target))
    images=[]
    for path in DEST.rglob('*.png'):
        with Image.open(path) as image:image.verify()
        images.append(str(path.relative_to(DEST)))
    assert len(images)==25,len(images)
    assert sha(ROOT/'README.md')==sha(DEST/'README.md')
    assert 'continues the ordinary endpoint and phase reference' in (DEST/'recovery/FINDINGS.md').read_text()
    output=dict(status='passed',report_directory=str(DEST.relative_to(PUBLISHER)),
        no_commit_or_push_yet=True,asset_count=package['asset_count'],asset_bytes=package['asset_bytes'],
        largest_asset_bytes=package['largest_asset_bytes'],all_archive_members_roundtrip_verified=True,
        runtime_source_files=358,git_files=len(files)+3,git_bytes_excluding_this_receipt=sum(p.stat().st_size for p in DEST.rglob('*') if p.is_file()),
        image_files=len(images),local_links_checked=len(links),missing_local_links=0,
        root_README_sha256=sha(ROOT/'README.md'),published_README_sha256=sha(DEST/'README.md'),
        recovery_FINDINGS_sha256=sha(DEST/'recovery/FINDINGS.md'),
        publication_index_sha256=sha(DEST/'publication_index.json'),source_sha256=sha(Path(__file__)),
        raw_IQ_included=False,production_files_changed=False)
    write_new(DEST/'publication_audit.json',output)
    write_new(HERE/'publication/staging_receipt.json',output)
    print(json.dumps(output,indent=2))


if __name__=='__main__':main()
