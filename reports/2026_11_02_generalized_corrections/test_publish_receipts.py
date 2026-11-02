"""Publication integrity checks use isolated synthetic reports, never live data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile

import pytest

spec=importlib.util.spec_from_file_location('publication_receipts',Path(__file__).with_name('publish_receipts.py'))
publication=importlib.util.module_from_spec(spec);spec.loader.exec_module(publication)


def put(root,name,value):
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(value if isinstance(value,bytes) else (json.dumps(value,indent=2)+'\n').encode())
    return path


def fixture_report(root):
    components=[];checks=[]
    for name in ['evaluation/results.json','evaluation/wave2/results.json','evaluation/wave3/results.json']:
        row=dict(case='CASE',status='complete')
        path=put(root,name,dict(workers_joined=True,available=1,rows=[row]))
        put(root,str(Path(name).parent/'cases/CASE/result.json'),row)
        put(root,str(Path(name).parent/'execution_started.json'),dict(cases=1))
        components.append(dict(path=str(path),sha256=publication.sha(path)))
        checks.append(dict(path=str(path),sha256=publication.sha(path),workers_joined=True))
    combined=put(root,'evaluation/combined_results.json',dict(workers_joined=True,available=1,
        components=components,rows=[dict(case='CASE',status='complete')]))
    put(root,'review/combined_audit.json',dict(status='passed',results_sha256=publication.sha(combined),
        recordings=1,component_checks=checks))
    put(root,'evaluation/cases/CASE/checkpoint_at_total_deadline.json',b'{"status":"running"}\n')
    put(root,'evaluation/cases/CASE/A-c0.rf.json',b'{ "status" : "complete", "exact": 1.000 }\n')
    put(root,'evaluation/cases/CASE/result.json.tmp-123',b'partial-manager-write')
    put(root,'evaluation/cases/CASE/worker.started',b'')
    (root/'evaluation/cases/CASE/engine').mkdir()
    put(root,'evaluation/cases/CASE/contexts/prepared.pkl',b'excluded-runtime-context')
    put(root,'evaluation/cases/CASE/contexts/model.rf.json',b'{"receipt":"kept even in context folder"}\n')
    put(root,'evaluation/cases/CASE/cache/state.npz',b'excluded-runtime-cache')
    put(root,'evaluation/cases/CASE/run.log',b'excluded-log')
    put(root,'evaluation/cases/CASE/__pycache__/worker.pyc',b'excluded-bytecode')
    put(root,'evaluation/rf_roster.json',dict(cases=['CASE']))
    put(root,'evaluation/wave1_seal.json',dict(workers_joined=True))
    put(root,'coverage_protocol.json',dict(small_config=True))
    put(root,'protocol.json',dict(small_config=True))
    put(root,'evaluation/proposed_configuration.json',dict(small_config=True))
    put(root,'publish_receipts.py',b'# directly published source\n')


def test_exact_bytes_paths_tree_markers_and_originals_preserved(tmp_path):
    fixture_report(tmp_path)
    before={p.relative_to(tmp_path).as_posix():p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    manifest=publication.pack(tmp_path)
    archive=tmp_path/manifest['archive']['path']
    assert publication.sha(archive)==manifest['archive']['sha256']
    publication.verify_archive(archive,manifest)
    expected={r['path']:r for r in manifest['files']}
    assert 'evaluation/results.json' in expected and 'evaluation/wave2/results.json' in expected
    assert 'evaluation/wave3/results.json' in expected and 'evaluation/combined_results.json' in expected
    assert 'evaluation/cases/CASE/A-c0.rf.json' in expected
    assert 'evaluation/cases/CASE/result.json.tmp-123' in expected
    assert 'evaluation/cases/CASE/checkpoint_at_total_deadline.json' in expected
    assert 'evaluation/cases/CASE/worker.started' in expected
    assert 'evaluation/cases/CASE/contexts/model.rf.json' in expected
    assert 'protocol.json' not in expected
    assert 'evaluation/proposed_configuration.json' not in expected
    assert all(not name.endswith(('.pkl','.npz','.log','.pyc','.py')) for name in expected)
    with tarfile.open(archive,'r:gz') as packet:
        names=packet.getnames()
        assert all(not n.startswith('/') and '..' not in Path(n).parts for n in names)
        assert 'evaluation/cases/CASE/engine' in names
        assert 'evaluation/cases/CASE/contexts' in names
        exact=packet.extractfile('evaluation/cases/CASE/A-c0.rf.json').read()
        assert exact==before['evaluation/cases/CASE/A-c0.rf.json']
    excluded=[r for r in manifest['original_case_tree'] if r.get('archived') is False]
    assert len(excluded)==4
    for item in excluded:assert item['sha256']==hashlib.sha256(before[item['path']]).hexdigest()
    for name,value in before.items():assert (tmp_path/name).read_bytes()==value


def test_deterministic_gzip_tar_and_zero_metadata(tmp_path):
    fixture_report(tmp_path)
    first=publication.pack(tmp_path,'first.tar.gz')
    second=publication.pack(tmp_path,'second.tar.gz')
    assert first['archive']['sha256']==second['archive']['sha256']
    assert (tmp_path/'first.tar.gz').read_bytes()==(tmp_path/'second.tar.gz').read_bytes()
    assert (tmp_path/'first.tar.gz').read_bytes()[4:8]==b'\0'*4
    with tarfile.open(tmp_path/'first.tar.gz') as packet:
        assert all(m.uid==m.gid==m.mtime==0 and m.uname==m.gname=='' for m in packet)


@pytest.mark.parametrize('mode',['unjoined','running','stale_audit','component_unjoined','unlisted_wave'])
def test_refuses_unfinished_or_mismatched_bindings(tmp_path,mode):
    fixture_report(tmp_path)
    combined=publication.read(tmp_path/'evaluation/combined_results.json')
    audit=publication.read(tmp_path/'review/combined_audit.json')
    if mode=='unjoined':combined['workers_joined']=False
    if mode=='running':combined['rows'][0]['status']='running'
    if mode=='stale_audit':audit['results_sha256']='0'*64
    if mode=='component_unjoined':audit['component_checks'][0]['workers_joined']=False
    if mode=='unlisted_wave':
        combined['components'].pop();audit['component_checks'].pop()
    put(tmp_path,'evaluation/combined_results.json',combined)
    if mode!='stale_audit':audit['results_sha256']=publication.sha(tmp_path/'evaluation/combined_results.json')
    put(tmp_path,'review/combined_audit.json',audit)
    with pytest.raises(ValueError):publication.pack(tmp_path)
    assert not (tmp_path/'evaluation_receipts.tar.gz').exists()


def test_refuses_changed_component_bytes(tmp_path):
    fixture_report(tmp_path)
    with (tmp_path/'evaluation/wave2/results.json').open('ab') as stream:stream.write(b' ')
    with pytest.raises(ValueError,match='Component ledger hash'):
        publication.pack(tmp_path)


def test_refuses_existing_outputs_and_symlink_receipts(tmp_path):
    fixture_report(tmp_path)
    archive=tmp_path/'evaluation_receipts.tar.gz';archive.write_bytes(b'keep-me')
    with pytest.raises(FileExistsError):publication.pack(tmp_path)
    assert archive.read_bytes()==b'keep-me'
    archive.unlink()
    (tmp_path/'evaluation/cases/CASE/foreign').symlink_to(tmp_path/'protocol.json')
    with pytest.raises(ValueError,match='Symlink'):publication.pack(tmp_path)


def test_detects_case_tree_mutation_and_removes_only_own_partial_outputs(tmp_path,monkeypatch):
    fixture_report(tmp_path)
    original=publication.write_archive
    def mutate(root,output,inventory):
        original(root,output,inventory)
        put(root,'evaluation/cases/CASE/new-worker-marker',b'appeared')
    monkeypatch.setattr(publication,'write_archive',mutate)
    with pytest.raises(ValueError,match='changed during publication'):publication.pack(tmp_path)
    assert not (tmp_path/'evaluation_receipts.tar.gz').exists()
    assert not (tmp_path/'evaluation_receipts.manifest.json').exists()
    assert (tmp_path/'evaluation/cases/CASE/new-worker-marker').read_bytes()==b'appeared'
    assert not list(tmp_path.glob('.receipt-*'))
