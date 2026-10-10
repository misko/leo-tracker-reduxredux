"""Synthetic metadata authority tests; no model or recording imports."""
import hashlib
import io
import json
import tarfile
import pytest
import freeze


def fixture(tmp_path, monkeypatch, *, count=12, foreign=None):
    root=tmp_path; prior=root/'prior160';here=root/'iter161'
    prior.mkdir();here.mkdir();(prior/'results').mkdir()
    monkeypatch.setattr(freeze,'ROOT',root);monkeypatch.setattr(freeze,'PRIOR',prior)
    monkeypatch.setattr(freeze,'HERE',here)
    members=[dict(label=str(i),dataset='DS16',binding={},selected_path='original/'+str(i)) for i in range(count)]
    protocol=dict(members=members,source_sha256={},input_sha256={},
                  runtime=dict(interpreter=freeze.INTERPRETER,sha256={}))
    def write(path,value):path.write_text(json.dumps(value))
    write(prior/'protocol.json',protocol)
    hashes={}
    with tarfile.open(prior/'raw-receipts.tar.gz','w:gz') as archive:
        for member in members:
            for suffix in ('.json','.claim.json'):
                name=member['label']+suffix
                value=dict(label=member['label'],protocol_sha256=freeze.FOLD_DIGEST,status='complete')
                if foreign=='digest' and name=='0.json':value['protocol_sha256']='foreign'
                if foreign=='label' and name=='0.json':value['label']='other'
                data=json.dumps(value).encode();(prior/'results'/name).write_bytes(data)
                hashes[name]=hashlib.sha256(data).hexdigest()
                entry=tarfile.TarInfo(name);entry.size=len(data);archive.addfile(entry,io.BytesIO(data))
    write(prior/'SUMMARY.json',dict(protocol_sha256=freeze.FOLD_DIGEST,raw_sha256=hashes))
    integrity={name:freeze.sha(prior/name) for name in ('protocol.json','SUMMARY.json','raw-receipts.tar.gz')}
    write(prior/'REPORT_INTEGRITY.json',integrity)
    monkeypatch.setattr(freeze,'AUTHORITY_SHA',freeze.sha(prior/'protocol.json'))
    monkeypatch.setattr(freeze,'INTEGRITY_SHA',freeze.sha(prior/'REPORT_INTEGRITY.json'))
    for name in ('freeze.py','run.py','fit_core.py','test_fit_core.py','test_run.py','test_freeze.py','PLAN.md'):
        (here/name).write_text('synthetic')
    rows=here.parent/'2026_10_10_position_error_iter159/rows.py';rows.parent.mkdir();rows.write_text('synthetic')
    return members


def test_exact_inventory_preserves_selected_members_and_binds_folds(tmp_path,monkeypatch):
    members=fixture(tmp_path,monkeypatch)
    plan=freeze.prepare()
    assert len(plan['members'])==12 and plan['policy']['maximum_fits']==72
    assert plan['members'][0]['selected_path']==members[0]['selected_path']
    assert plan['members'][0]['fold_protocol_digest']==freeze.FOLD_DIGEST
    assert all(member['fold_path'] in plan['input_sha256'] for member in plan['members'])
    assert 'iter161/run.py' in plan['source_sha256']


@pytest.mark.parametrize('foreign',['digest','label'])
def test_foreign_fold_is_rejected_even_when_archive_bytes_match(tmp_path,monkeypatch,foreign):
    fixture(tmp_path,monkeypatch,foreign=foreign)
    with pytest.raises(ValueError,match='foreign160'):freeze.prepare()


def test_missing_member_is_not_filtered(tmp_path,monkeypatch):
    fixture(tmp_path,monkeypatch,count=11)
    with pytest.raises(ValueError,match='exact twelve'):freeze.prepare()


def test_local_receipt_tamper_rejected_against_published_archive(tmp_path,monkeypatch):
    fixture(tmp_path,monkeypatch)
    (freeze.PRIOR/'results/0.claim.json').write_text('{}')
    with pytest.raises(ValueError,match='local receipt differs'):freeze.prepare()
