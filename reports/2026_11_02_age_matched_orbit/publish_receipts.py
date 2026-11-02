"""Deterministic postfit receipt archive; no original is changed or removed."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parent
RUNTIME_DIRS={'context','contexts','cache','caches','__pycache__','.cache'}
RUNTIME_SUFFIXES={'.pyc','.pyo','.log','.pkl','.pickle','.npz','.npy'}
UNFINISHED={'running','pending','queued','in_progress'}


def sha(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


def read(path):return json.loads(Path(path).read_bytes())


def safe(root,path):
    path=Path(path);path=path if path.is_absolute() else root/path
    name=path.relative_to(root).as_posix()
    if '..' in Path(name).parts:raise ValueError('Unsafe archive path')
    for parent in [path,*path.parents]:
        if parent==root.parent:break
        if parent.is_symlink():raise ValueError('Symlink in receipt tree: '+name)
    if path.resolve()!=root/name:raise ValueError('Receipt path escapes report root')
    return name


def receipt(root,path):return dict(path=safe(root,path),size=path.stat().st_size,sha256=sha(path))


def readiness(root):
    results=read(root/'evaluation/results.json');audit=read(root/'review/final_audit.json')
    seal=read(root/'evaluation/completion_seal.json');protocol=read(root/'protocol.json')
    results_sha=sha(root/'evaluation/results.json');protocol_sha=sha(root/'protocol.json')
    if results.get('workers_joined') is not True or len(results['rows'])!=results['available']:
        raise ValueError('Evaluation workers have not joined or counts differ')
    if any(r.get('status') in UNFINISHED or any(c.get('status') in UNFINISHED
        for c in r.get('raw_endpoints',{}).values()) for r in results['rows']):
        raise ValueError('Unfinished worker/cell remains')
    if audit.get('status')!='passed' or audit.get('workers_joined') is not True or audit.get('results_sha256')!=results_sha:
        raise ValueError('Passing final audit is not bound to exact joined results')
    if seal.get('status')!='sealed' or seal.get('all_workers_joined') is not True or seal.get('results_sha256')!=results_sha:
        raise ValueError('Completion seal is missing or stale')
    if any(packet.get('protocol_sha256')!=protocol_sha for packet in [results,audit,seal]):
        raise ValueError('Scientific protocol binding differs')
    if audit.get('recordings')!=results['available'] or seal.get('available')!=results['available']:
        raise ValueError('Audit/seal recording count differs')
    roster_sha=sha(root/'evaluation/rf_roster.json')
    if any(packet.get('roster_sha256')!=roster_sha for packet in [results,audit]):raise ValueError('Roster binding differs')
    for path,digest in protocol['source_sha256'].items():
        if sha(path)!=digest:raise ValueError('Frozen scientific source changed: '+path)
    if seal.get('scientific_source_hashes_unchanged') is not True or seal.get('scientific_sources')!=len(protocol['source_sha256']):
        raise ValueError('Frozen source completion seal differs')
    return dict(results_sha256=results_sha,protocol_sha256=protocol_sha,roster_sha256=roster_sha,
        final_audit_sha256=sha(root/'review/final_audit.json'),completion_seal_sha256=sha(root/'evaluation/completion_seal.json'),
        scientific_sources=len(protocol['source_sha256']),available=results['available'])


def runtime_reason(name):
    path=Path(name)
    if path.name in {'result.json','checkpoint_at_total_deadline.json'} or path.name.endswith(('.rf.json','.checkpoint.json')) or '.json.tmp' in path.name:
        return None
    if any(p in RUNTIME_DIRS for p in path.parts):return 'runtime context/cache payload'
    if path.suffix.lower() in RUNTIME_SUFFIXES:return 'runtime cache/log/bytecode payload'
    return None


def snapshot(root):
    files={};directories=set();tree=[]
    def add(path):
        if not path.is_file():raise ValueError('Non-regular receipt file')
        item=receipt(root,path);files[item['path']]=item
        directories.update(p.as_posix() for p in Path(item['path']).parents if str(p)!='.')
    for folder in [root/'evaluation',root/'review']:
        for path in sorted(folder.glob('*.json')):add(path)
    case_root=root/'evaluation/cases'
    if not case_root.is_dir():raise ValueError('Missing case receipt tree')
    directories.add(safe(root,case_root))
    for folder,children,names in os.walk(case_root,followlinks=False):
        children.sort();names.sort();folder=Path(folder)
        for name in children:
            path=folder/name;rel=safe(root,path)
            if not path.is_dir():raise ValueError('Non-directory case artifact')
            directories.add(rel);tree.append(dict(path=rel,type='directory',archived=True))
        for name in names:
            path=folder/name;rel=safe(root,path)
            if not path.is_file():raise ValueError('Non-regular case artifact')
            item=receipt(root,path);reason=runtime_reason(rel)
            tree.append(dict(item,type='file',archived=reason is None,exclusion=reason))
            if reason is None:add(path)
    return dict(files=sorted(files.values(),key=lambda r:r['path']),directories=sorted(directories),
        original_case_tree=sorted(tree,key=lambda r:r['path']))


class HashReader:
    def __init__(self,stream):self.stream=stream;self.digest=hashlib.sha256()
    def read(self,size=-1):
        block=self.stream.read(size);self.digest.update(block);return block


def write_archive(root,path,inventory):
    files={r['path']:r for r in inventory['files']}
    with path.open('wb') as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0,compresslevel=9) as compressed:
        with tarfile.open(fileobj=compressed,mode='w',format=tarfile.PAX_FORMAT) as archive:
            for name in sorted(set(files)|set(inventory['directories'])):
                item=tarfile.TarInfo(name);item.uid=item.gid=0;item.uname=item.gname='';item.mtime=0
                if name in files:
                    item.size=files[name]['size'];item.mode=0o644
                    with (root/name).open('rb') as stream:
                        hashing=HashReader(stream);archive.addfile(item,hashing)
                    if hashing.digest.hexdigest()!=files[name]['sha256']:raise ValueError('Receipt changed while archiving')
                else:item.type=tarfile.DIRTYPE;item.mode=0o755;archive.addfile(item)


def verify_archive(path,manifest):
    expected={r['path']:r for r in manifest['files']};found=set();directories=set()
    if 'archive' in manifest and sha(path)!=manifest['archive']['sha256']:raise ValueError('Archive SHA256 differs')
    with tarfile.open(path,'r:gz') as archive:
        for item in archive:
            if Path(item.name).is_absolute() or '..' in Path(item.name).parts:raise ValueError('Unsafe tar member path')
            if item.name in found or item.name in directories:raise ValueError('Duplicate tar member')
            if item.uid or item.gid or item.mtime or item.uname or item.gname:raise ValueError('Nonnormalized tar metadata')
            if item.isdir():directories.add(item.name);continue
            if not item.isfile() or item.name not in expected:raise ValueError('Unexpected tar member')
            stream=archive.extractfile(item);digest=hashlib.sha256()
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
            if item.size!=expected[item.name]['size'] or digest.hexdigest()!=expected[item.name]['sha256']:
                raise ValueError('Archived receipt bytes differ')
            found.add(item.name)
    if found!=set(expected) or directories!=set(manifest['directories']):raise ValueError('Archive membership differs')


def restore_test(path,manifest):
    verify_archive(path,manifest)
    with tempfile.TemporaryDirectory(prefix='receipt-restore-') as temporary:
        destination=Path(temporary)
        with tarfile.open(path,'r:gz') as archive:archive.extractall(destination,filter='data')
        for item in manifest['files']:
            restored=destination/item['path']
            if restored.stat().st_size!=item['size'] or sha(restored)!=item['sha256']:raise ValueError('Restored file hash differs')
        if not all((destination/name).is_dir() for name in manifest['directories']):raise ValueError('Restored directory marker missing')


def pack(report_root=ROOT,name='evaluation_receipts.tar.gz'):
    root=Path(report_root).resolve()
    if Path(name).name!=name or not name.endswith('.tar.gz'):raise ValueError('Use a report-root .tar.gz basename')
    archive=root/name;manifest_path=root/(name[:-7]+'.manifest.json')
    if archive.exists() or manifest_path.exists():raise FileExistsError('Publication outputs already exist')
    binding=readiness(root);inventory=snapshot(root);temporary=[];published=[]
    try:
        with tempfile.NamedTemporaryFile(prefix='.receipt-',dir=root,delete=False) as stream:temp_archive=Path(stream.name)
        temporary.append(temp_archive);write_archive(root,temp_archive,inventory);restore_test(temp_archive,inventory)
        if readiness(root)!=binding or snapshot(root)!=inventory:raise ValueError('Original receipt/source inventory changed during packaging')
        manifest=dict(schema_version=1,binding=binding,archive=dict(path=name,size=temp_archive.stat().st_size,sha256=sha(temp_archive)),
            file_count=len(inventory['files']),total_file_bytes=sum(r['size'] for r in inventory['files']),
            restore_test_passed=True,originals_unchanged=True,**inventory,
            normalization=dict(gzip_mtime=0,gzip_filename='',tar_mtime=0,uid=0,gid=0))
        with tempfile.NamedTemporaryFile(prefix='.receipt-',dir=root,delete=False) as stream:
            temp_manifest=Path(stream.name);stream.write((json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode())
        temporary.append(temp_manifest)
        os.link(temp_archive,archive);published.append(archive)
        os.link(temp_manifest,manifest_path);published.append(manifest_path)
        return manifest
    except BaseException:
        for path in published:path.unlink()
        raise
    finally:
        for path in temporary:path.unlink(missing_ok=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if args.verify:
        manifest=read(args.root/'evaluation_receipts.manifest.json');restore_test(args.root/'evaluation_receipts.tar.gz',manifest)
        print('Archive membership, every byte hash and restored relative paths verified')
    else:
        manifest=pack(args.root);print(json.dumps(dict(archive=manifest['archive'],files=manifest['file_count'],
            restored_files_verified=manifest['file_count'],scientific_sources_unchanged=manifest['binding']['scientific_sources']),indent=2))
