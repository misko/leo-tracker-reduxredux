"""Metadata-only whitelist and failure-coverage fixtures."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

SPEC=importlib.util.spec_from_file_location('binding164_test',Path(__file__).with_name('inference_binding.py'))
B=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(B)


def fixture(tmp_path):
    document=dict(session_id='session',input_manifest_sha256='capture',analysis_manifest_sha256='analysis',
                  evidence_sha256='evidence',configuration=dict(prior={},scores={},run={}))
    path=tmp_path/'document.json';path.write_text(json.dumps(document))
    authority=dict(member=dict(dataset='DS16',inventory_label='DS16-001',session_id='session',
        recording_manifest_sha256='capture',uncompressed_sha256='iq',exposure='consumed',
        evaluation_status='not-inference'))
    projection=dict(label='DS16-001',session_id='session',membership=copy.deepcopy(authority['member']),
        document_path='document.json',document_sha256=B.sha(path),selected_path='forbidden',
        selected_sha256='forbidden',reference_latitude='forbidden',
        model_identity=dict(session_id='session',input_manifest_sha256='capture',analysis_manifest_sha256='analysis',
            evidence_sha256='evidence',prior_signature='prior',score_signature='score',bank_signature='bank',snapshot_sha256='tle'),
        expected_input_binding=dict(input_digest='capture',evidence_digest='evidence',score_signature='score',
                                    bank_signature='bank',observation_order_signature='order'))
    return authority,projection,path


def test_exact_whitelist_omits_selected_reference_fields_preserves_registry(tmp_path):
    authority,projection,_=fixture(tmp_path)
    row=B.project_member(authority,[projection],repository=tmp_path,loader_sha256='loader')
    assert row['binding_status']=='complete'
    assert set(row['binding'])=={'session_id','loader_source','loader_sha256','document_path','document_sha256','model_identity','expected_input_binding'}
    assert row['membership']['evaluation_status']=='not-inference'
    assert 'forbidden' not in json.dumps(row)
    assert row['membership']['exposure']=='consumed'
    assert row['exposure']=='previously consumed development'


@pytest.mark.parametrize('fault',['missing','duplicate','session','iq','capture','signature','document','reference','path'])
def test_bad_member_retained_with_explicit_error(tmp_path,fault):
    authority,projection,path=fixture(tmp_path);values=[projection]
    if fault=='missing':values=[]
    if fault=='duplicate':values=[projection,projection]
    if fault=='session':projection['session_id']='other'
    if fault=='iq':projection['membership']['uncompressed_sha256']='other'
    if fault=='capture':projection['model_identity']['input_manifest_sha256']='other'
    if fault=='signature':del projection['expected_input_binding']['observation_order_signature']
    if fault=='document':path.write_text('{}')
    if fault=='reference':
        d=json.loads(path.read_text());d['reference_latitude']=0;path.write_text(json.dumps(d));projection['document_sha256']=B.sha(path)
    if fault=='path':projection['document_path']='../escape.json'
    row=B.project_member(authority,values,repository=tmp_path,loader_sha256='loader')
    assert row['label']=='DS16-001' and row['membership']['session_id']=='session'
    assert row['binding_status']=='failed' and row['binding'] is None and row['binding_error']


def test_newer_membership_schema_is_supported_without_endpoint_fields(tmp_path):
    authority,projection,_=fixture(tmp_path)
    del authority['member']['dataset'];authority['dataset']='POST18-development'
    authority['member']['dataset_label']=authority['member'].pop('inventory_label')
    row=B.project_member(authority,[projection],repository=tmp_path,loader_sha256='loader')
    assert row['binding_status']=='complete' and row['dataset']=='POST18-development'


def test_null_mint_manifest_preserved_with_later_exact_physical_authority(tmp_path):
    authority,projection,_=fixture(tmp_path)
    authority['member']['recording_manifest_sha256']=None
    projection['membership']['recording_manifest_sha256']=None
    row=B.project_member(authority,[projection],repository=tmp_path,loader_sha256='loader')
    assert row['binding_status']=='complete'
    assert row['membership']['recording_manifest_sha256'] is None
    assert row['binding']['model_identity']['input_manifest_sha256']=='capture'
    assert 'absent' in row['manifest_provenance']
    projection['expected_input_binding']['input_digest']='different'
    failed=B.project_member(authority,[projection],repository=tmp_path,loader_sha256='loader')
    assert failed['binding_status']=='failed'


def test_nonnull_mint_manifest_is_never_treated_as_optional(tmp_path):
    authority,projection,_=fixture(tmp_path)
    authority['member']['recording_manifest_sha256']='different'
    projection['membership']['recording_manifest_sha256']='different'
    row=B.project_member(authority,[projection],repository=tmp_path,loader_sha256='loader')
    assert row['binding_status']=='failed' and 'mint manifest differs' in row['binding_error']


def test_loader_refuses_failed_member_before_backend_import():
    class Entry:
        def make_loader(self,*a):pytest.fail('backend touched')
    with pytest.raises(ValueError,match='unavailable'):
        B.make_loader(Entry(),dict(binding_status='failed',binding=None,binding_error='missing'))


def test_all193_preserved_despite_one_missing_projection(tmp_path):
    authority,projection,_=fixture(tmp_path);members=[];projections=[]
    for dataset,count in [('DS16',63),('DS17',51),('DS18',34),('POST18-development',45)]:
        for i in range(count):
            label=f'{dataset}-{i:03}';a=copy.deepcopy(authority)
            a['member'].update(dataset=dataset,inventory_label=label,session_id=label)
            members.append(a)
            # An identity mismatch is deliberately retained, not filtered.
            p=copy.deepcopy(projection);p['label']=label;projections.append(p)
    (tmp_path/'authority.json').write_text(json.dumps({'members':members}))
    (tmp_path/'projections.json').write_text(json.dumps({'members':projections[:-1]}))
    loader=tmp_path/B.LOADER;loader.parent.mkdir(parents=True);loader.write_text('# no import')
    rows=B.prepare_bindings(tmp_path,authority_path='authority.json',projection_path='projections.json')
    assert len(rows)==193 and rows[-1]['binding_error']
    assert [r['label'] for r in rows]==[m['member']['inventory_label'] for m in members]
