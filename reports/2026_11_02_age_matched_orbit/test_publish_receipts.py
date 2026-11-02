"""Synthetic publication/restore checks; live receipts are never edited."""
import importlib.util
import json
from pathlib import Path
import tarfile
import pytest

spec=importlib.util.spec_from_file_location('age_publication',Path(__file__).with_name('publish_receipts.py'))
publication=importlib.util.module_from_spec(spec);spec.loader.exec_module(publication)


def put(root,name,data):
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data if isinstance(data,bytes) else (json.dumps(data,indent=2)+'\n').encode());return path


def fixture(root):
    source=put(root,'science.py',b'# frozen science\n')
    roster=put(root,'evaluation/rf_roster.json',dict(cases=['CASE']))
    protocol=put(root,'protocol.json',dict(source_sha256={str(source):publication.sha(source)}))
    row=dict(case='CASE',status='qualified',raw_endpoints={'c0':dict(status='complete')})
    results=put(root,'evaluation/results.json',dict(workers_joined=True,available=1,rows=[row],
        protocol_sha256=publication.sha(protocol),roster_sha256=publication.sha(roster)))
    put(root,'review/final_audit.json',dict(status='passed',workers_joined=True,recordings=1,
        results_sha256=publication.sha(results),protocol_sha256=publication.sha(protocol),roster_sha256=publication.sha(roster)))
    put(root,'evaluation/completion_seal.json',dict(status='sealed',all_workers_joined=True,
        results_sha256=publication.sha(results),protocol_sha256=publication.sha(protocol),available=1,
        scientific_source_hashes_unchanged=True,scientific_sources=1))
    put(root,'evaluation/cases/CASE/result.json',row)
    put(root,'evaluation/cases/CASE/age-c0.rf.json',b'{ "status": "complete", "number": 1.0000 }\n')
    put(root,'evaluation/cases/CASE/age-c0.checkpoint.json',b'{"status":"running"}\n')
    put(root,'evaluation/cases/CASE/result.json.tmp-10',b'unfinished bytes retained as marker')
    (root/'evaluation/cases/CASE/engine').mkdir()
    put(root,'evaluation/cases/CASE/cache/state.npy',b'cache')
    put(root,'evaluation/cases/CASE/cache/age-c0.rf.json',b'{"protected":"receipt"}\n')
    put(root,'evaluation/cases/CASE/run.log',b'log')
    put(root,'evaluation/cases/CASE/__pycache__/x.pyc',b'bytecode')


def test_exact_members_restore_and_originals(tmp_path):
    fixture(tmp_path)
    before={p.relative_to(tmp_path).as_posix():p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    packet=publication.pack(tmp_path)
    publication.restore_test(tmp_path/'evaluation_receipts.tar.gz',packet)
    names={r['path'] for r in packet['files']}
    assert 'evaluation/results.json' in names and 'review/final_audit.json' in names
    assert 'evaluation/cases/CASE/age-c0.rf.json' in names
    assert 'evaluation/cases/CASE/cache/age-c0.rf.json' in names
    assert 'evaluation/cases/CASE/result.json.tmp-10' in names
    assert not any(name.endswith(('.npy','.log','.pyc')) for name in names)
    assert 'evaluation/cases/CASE/engine' in packet['directories']
    with tarfile.open(tmp_path/'evaluation_receipts.tar.gz') as archive:
        exact=archive.extractfile('evaluation/cases/CASE/age-c0.rf.json').read()
        assert exact==before['evaluation/cases/CASE/age-c0.rf.json']
        assert all(not m.name.startswith('/') and '..' not in Path(m.name).parts for m in archive)
    for name,data in before.items():assert (tmp_path/name).read_bytes()==data
    assert packet['restore_test_passed'] and packet['originals_unchanged']


def test_deterministic_bytes_and_metadata(tmp_path):
    fixture(tmp_path)
    a=publication.pack(tmp_path,'first.tar.gz');b=publication.pack(tmp_path,'second.tar.gz')
    assert a['archive']['sha256']==b['archive']['sha256']
    assert (tmp_path/'first.tar.gz').read_bytes()[4:8]==b'\0'*4
    with tarfile.open(tmp_path/'first.tar.gz') as archive:
        assert all(m.uid==m.gid==m.mtime==0 and m.uname==m.gname=='' for m in archive)


@pytest.mark.parametrize('problem',['unjoined','stale_audit','stale_seal','frozen_source','running'])
def test_refuses_unfinished_or_changed_science(tmp_path,problem):
    fixture(tmp_path)
    if problem in ['unjoined','running']:
        results=publication.read(tmp_path/'evaluation/results.json')
        if problem=='unjoined':results['workers_joined']=False
        else:results['rows'][0]['status']='running'
        put(tmp_path,'evaluation/results.json',results)
    if problem=='stale_audit':
        data=publication.read(tmp_path/'review/final_audit.json');data['results_sha256']='0'*64;put(tmp_path,'review/final_audit.json',data)
    if problem=='stale_seal':
        data=publication.read(tmp_path/'evaluation/completion_seal.json');data['status']='pending';put(tmp_path,'evaluation/completion_seal.json',data)
    if problem=='frozen_source':put(tmp_path,'science.py',b'changed')
    with pytest.raises(ValueError):publication.pack(tmp_path)
    assert not (tmp_path/'evaluation_receipts.tar.gz').exists()


def test_no_overwrite_or_symlinks(tmp_path):
    fixture(tmp_path)
    archive=put(tmp_path,'evaluation_receipts.tar.gz',b'original archive')
    with pytest.raises(FileExistsError):publication.pack(tmp_path)
    assert archive.read_bytes()==b'original archive';archive.unlink()
    (tmp_path/'evaluation/cases/CASE/foreign').symlink_to(tmp_path/'science.py')
    with pytest.raises(ValueError,match='Symlink'):publication.pack(tmp_path)


def test_restore_hash_mismatch_is_rejected(tmp_path):
    fixture(tmp_path);manifest=publication.pack(tmp_path)
    manifest['files'][0]['sha256']='0'*64
    with pytest.raises(ValueError):publication.restore_test(tmp_path/'evaluation_receipts.tar.gz',manifest)
