"""Postfit deterministic packaging of exact RF receipts; originals stay intact."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parent
DIRECT_CONFIGS={'protocol.json','execution_protocol.json','coverage_protocol.json',
                'prelaunch_amendment.json','evaluation/proposed_configuration.json'}
RUNTIME_DIRS={'context','contexts','cache','caches','__pycache__','.cache'}
RUNTIME_SUFFIXES={'.pyc','.pyo','.log','.pkl','.pickle','.npz','.npy'}
UNFINISHED={'running','pending','queued','in_progress'}


def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def relative(root,path):
    path=Path(path)
    if not path.is_absolute():path=root/path
    rel=path.relative_to(root)
    if '..' in rel.parts:raise ValueError('Receipt path escapes report root')
    # Reject symlinks rather than silently following or rewriting source bytes.
    for parent in [path,*path.parents]:
        if parent==root.parent:break
        if parent.is_symlink():raise ValueError('Symlink in receipt tree: '+str(path))
    if path.resolve()!=root/rel:raise ValueError('Receipt path is not local to report root')
    return rel.as_posix()


def ensure_terminal(packet,label):
    if packet.get('workers_joined') is not True:raise ValueError(label+' workers have not joined')
    rows=packet.get('rows',[])
    if len(rows)!=packet.get('available'):raise ValueError(label+' row count differs')
    if any(row.get('status') in UNFINISHED for row in rows):raise ValueError(label+' contains unfinished worker rows')


def readiness(root):
    """Bind publication to a completed combined ledger and its passing audit."""
    combined_path=root/'evaluation/combined_results.json'
    audit_path=root/'review/combined_audit.json'
    relative(root,combined_path);relative(root,audit_path)
    combined=read(combined_path);audit=read(audit_path)
    ensure_terminal(combined,'Combined')
    digest=sha(combined_path)
    if audit.get('status')!='passed' or audit.get('results_sha256')!=digest:
        raise ValueError('Passing combined audit is not bound to these exact results')
    if audit.get('recordings')!=combined['available']:raise ValueError('Combined audit recording count differs')
    for key,name in [('scientific_protocol_sha256','execution_protocol.json'),
                     ('coverage_protocol_sha256','coverage_protocol.json'),
                     ('roster_sha256','evaluation/rf_roster.json')]:
        if key in combined and (audit.get(key)!=combined[key] or sha(root/name)!=combined[key]):
            raise ValueError('Current direct input/config differs from combined audit: '+name)
    listed=combined.get('components',[])
    expected=['evaluation/results.json','evaluation/wave2/results.json','evaluation/wave3/results.json']
    names=[relative(root,item['path']) for item in listed]
    if not names or names!=expected[:len(names)]:raise ValueError('Component ledgers are not a chronological original/wave2/wave3 prefix')
    checks={relative(root,item['path']):item for item in audit.get('component_checks',[])}
    if set(checks)!=set(names):raise ValueError('Combined audit component set differs')
    for name,item in zip(names,listed):
        path=root/name
        if sha(path)!=item['sha256'] or checks[name].get('sha256')!=item['sha256']:
            raise ValueError('Component ledger hash differs from combined results/audit: '+name)
        ensure_terminal(read(path),name)
        if checks[name].get('workers_joined') is not True:raise ValueError('Audited component workers have not joined')
    # Any started later wave must have reached a terminal ledger included here.
    for name in expected[1:]:
        folder=(root/name).parent
        if ((folder/'execution_started.json').exists() or (folder/'results.json').exists()) and name not in names:
            raise ValueError('Started/completed wave is absent from the combined ledger: '+str(folder))
    return dict(combined_results_path='evaluation/combined_results.json',results_sha256=digest,
                combined_audit_path='review/combined_audit.json',combined_audit_sha256=sha(audit_path),
                available=combined['available'],components=[dict(path=name,sha256=item['sha256']) for name,item in zip(names,listed)])


def file_receipt(root,path):
    return dict(path=relative(root,path),size=path.stat().st_size,sha256=sha(path))


def runtime_reason(rel):
    path=Path(rel)
    if (path.name in {'result.json','checkpoint_at_total_deadline.json'}
            or path.name.endswith(('.rf.json','.checkpoint.json')) or '.json.tmp' in path.name):
        return None
    if any(part in RUNTIME_DIRS for part in path.parts):return 'runtime context/cache directory payload'
    if path.suffix.lower() in RUNTIME_SUFFIXES:return 'runtime context/cache/log/bytecode payload'
    if path.name.lower().startswith(('context.','context_')):return 'runtime context payload'
    return None


def collect(root,binding):
    """Keep all case marker directories, even when their payload is excluded."""
    files={};directories=set();case_tree=[];direct=[]
    def add(path):
        if not path.is_file():raise ValueError('Non-regular receipt file: '+str(path))
        rec=file_receipt(root,path);files[rec['path']]=rec
        for parent in Path(rec['path']).parents:
            if str(parent)!='.':directories.add(parent.as_posix())
    for folder in [root,root/'evaluation',root/'review',root/'evaluation/wave2',root/'evaluation/wave3']:
        if not folder.exists():continue
        for path in sorted(folder.glob('*.json')):
            rel=relative(root,path)
            if path.name.endswith('.manifest.json'):continue
            if rel in DIRECT_CONFIGS:direct.append(file_receipt(root,path))
            else:add(path)
    for component in binding['components']:
        case_root=(root/component['path']).parent/'cases'
        if not case_root.is_dir():raise ValueError('Missing component case tree: '+str(case_root))
        directories.add(relative(root,case_root))
        for folder,children,names in os.walk(case_root,followlinks=False):
            children.sort();names.sort();folder=Path(folder)
            for child in children:
                path=folder/child;rel=relative(root,path)
                if not path.is_dir():raise ValueError('Non-directory case tree entry: '+rel)
                directories.add(rel);case_tree.append(dict(path=rel,type='directory',archived=True))
            for name in names:
                path=folder/name;rel=relative(root,path)
                if not path.is_file():raise ValueError('Non-regular case tree entry: '+rel)
                rec=file_receipt(root,path);reason=runtime_reason(rel)
                case_tree.append(dict(rec,type='file',archived=reason is None,exclusion=reason))
                if reason is None:add(path)
    return dict(files=sorted(files.values(),key=lambda r:r['path']),directories=sorted(directories),
                original_case_tree=sorted(case_tree,key=lambda r:r['path']),
                directly_published_configs=sorted(direct,key=lambda r:r['path']))


class HashReader:
    def __init__(self,stream):self.stream=stream;self.digest=hashlib.sha256()
    def read(self,size=-1):
        block=self.stream.read(size);self.digest.update(block);return block


def write_archive(root,output,inventory):
    # An empty gzip filename and zero timestamp avoid host/time-dependent bytes.
    with output.open('wb') as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0,compresslevel=9) as zipped:
        with tarfile.open(fileobj=zipped,mode='w',format=tarfile.PAX_FORMAT) as archive:
            members={r['path']:r for r in inventory['files']}
            for name in sorted(set(members)|set(inventory['directories'])):
                info=tarfile.TarInfo(name)
                info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
                if name in members:
                    rec=members[name];info.size=rec['size'];info.mode=0o644
                    with (root/name).open('rb') as stream:
                        reader=HashReader(stream);archive.addfile(info,reader)
                    if reader.digest.hexdigest()!=rec['sha256']:
                        raise ValueError('Source receipt changed while archiving: '+name)
                else:
                    info.type=tarfile.DIRTYPE;info.mode=0o755;archive.addfile(info)


def verify_archive(archive_path,inventory):
    expected={r['path']:r for r in inventory['files']};seen=set();dirs=set()
    with tarfile.open(archive_path,'r:gz') as archive:
        for member in archive:
            if member.name in seen or member.name in dirs:raise ValueError('Duplicate archive member')
            if member.uid or member.gid or member.mtime or member.uname or member.gname:
                raise ValueError('Archive metadata is not normalized')
            if member.isdir():dirs.add(member.name);continue
            if not member.isfile() or member.name not in expected:raise ValueError('Unexpected archive member')
            digest=hashlib.sha256();stream=archive.extractfile(member)
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
            rec=expected[member.name]
            if member.size!=rec['size'] or digest.hexdigest()!=rec['sha256']:
                raise ValueError('Archive member bytes differ: '+member.name)
            seen.add(member.name)
    if seen!=set(expected) or dirs!=set(inventory['directories']):raise ValueError('Archive membership differs')


def pack(report_root=ROOT,archive_name='evaluation_receipts.tar.gz'):
    root=Path(report_root).resolve()
    if Path(archive_name).name!=archive_name or not archive_name.endswith('.tar.gz'):
        raise ValueError('Archive name must be a report-root .tar.gz basename')
    archive=root/archive_name;manifest=root/(archive_name[:-7]+'.manifest.json')
    if archive.exists() or manifest.exists():raise FileExistsError('Refusing to replace existing publication artifacts')
    binding=readiness(root);inventory=collect(root,binding)
    archive_tmp=None;manifest_tmp=None;published=[]
    try:
        with tempfile.NamedTemporaryFile(prefix='.receipt-archive-',dir=root,delete=False) as stream:
            archive_tmp=Path(stream.name)
        write_archive(root,archive_tmp,inventory)
        verify_archive(archive_tmp,inventory)
        if readiness(root)!=binding or collect(root,binding)!=inventory:
            raise ValueError('Original receipts/tree changed during publication packaging')
        packet=dict(schema_version=1,binding=binding,
            archive=dict(path=archive_name,size=archive_tmp.stat().st_size,sha256=sha(archive_tmp)),
            normalization=dict(gzip_mtime=0,gzip_filename='',tar_mtime=0,uid=0,gid=0),
            file_count=len(inventory['files']),total_file_bytes=sum(r['size'] for r in inventory['files']),
            **inventory,
            policy='Exact receipts and all case directory markers; runtime payloads excluded but full original case tree hashed; small configs/source publish directly; no originals removed or rewritten')
        payload=(json.dumps(packet,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
        with tempfile.NamedTemporaryFile(prefix='.receipt-manifest-',dir=root,delete=False) as stream:
            manifest_tmp=Path(stream.name);stream.write(payload)
        # link is atomic and refuses replacement; unlink only our temporary paths.
        os.link(archive_tmp,archive);published.append(archive)
        os.link(manifest_tmp,manifest);published.append(manifest)
        return packet
    except BaseException:
        for path in published:path.unlink()
        raise
    finally:
        for path in [archive_tmp,manifest_tmp]:
            if path is not None:path.unlink(missing_ok=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args();result=pack(args.root)
    print(json.dumps(dict(archive=result['archive'],files=result['file_count'],originals_unchanged=True),indent=2))
