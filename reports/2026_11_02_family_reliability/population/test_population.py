"""Critical saved-comparator fallback invariants; entirely synthetic inputs."""
import hashlib
import signal
import pytest
import run as population
from algo06_science.common import read,write


@pytest.fixture
def fake_policy(tmp_path,monkeypatch):
    source=tmp_path/'input.json';source.write_text('{}')
    baseline={a:dict(error_m=123.4 if a=='c0' else 234.5,objective=456.7,associated=89,selected='old_to_new',source='frozen.csv') for a in population.ARMS}
    record=dict(case='FAKE-0001',dataset='FAKE',identities=['native-one'],baseline=baseline,
        selected='old_to_new',input_path=str(source),input_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    policy=dict(cases=[record],development_cases=[],source_sha256={})
    write(tmp_path/'protocol.json',policy)
    monkeypatch.setattr(population,'ROOT',tmp_path)
    yield tmp_path,policy,record
    signal.alarm(0)


def test_existing_ALGO07_repair_preserved_without_ALGO06_reconstruction(fake_policy,monkeypatch):
    root,policy,record=fake_policy
    monkeypatch.setattr(population.e,'load_case',lambda *a:(_ for _ in ()).throw(AssertionError('must never reconstruct accepted comparator')))
    result=population.worker(record['case'])
    assert result['status']=='preserved_existing_ALGO07'
    assert result['accepted'] is False
    for arm in population.ARMS:
        assert result['selected_output'][arm]==dict(record['baseline'][arm],source='exact_saved_ALGO07')


def test_reconstruction_failure_keeps_exact_both_arm_saved_comparator(fake_policy,monkeypatch):
    root,policy,record=fake_policy
    record['selected']=None
    write(root/'protocol.json',policy)
    monkeypatch.setattr(population.e,'configure',lambda *a:None)
    monkeypatch.setattr(population.e,'load_case',lambda *a:(_ for _ in ()).throw(ValueError('intentional missing fixture')))
    result=population.worker(record['case'])
    assert result['status']=='failed'
    assert result['accepted'] is False
    assert not result['fit_attempted']
    for arm in population.ARMS:
        assert result['selected_output'][arm]['error_m']==record['baseline'][arm]['error_m']
        assert result['selected_output'][arm]['objective']==record['baseline'][arm]['objective']
        assert result['selected_output'][arm]['associated']==record['baseline'][arm]['associated']


def test_final_qualifier_requires_full_native_union_and_phase_closure():
    from audit import arm_qualified
    row=dict(optimizer_success=True,phase_closed=True,all_gates_pass=True,
        mixture_phase_boundary_masses=[.001],native_ids_preserved=True,all_native_IDs_preserved=True,
        all_fitted_owners_preserved=True,incumbent_lost=0,unrelated_reassigned=0)
    assert arm_qualified(row)
    assert not arm_qualified(dict(row,all_native_IDs_preserved=False))
    assert not arm_qualified(dict(row,all_fitted_owners_preserved=False))
    assert not arm_qualified(dict(row,phase_closed=False))


def test_complete_native_inventory_includes_predictive_pieces_and_rejects_reuse():
    from types import SimpleNamespace
    p=SimpleNamespace(rows=[{'candidate_norad':11}],members=[0],slices=[slice(0,2)],
        scan=SimpleNamespace(tracks=[{'observation_ids':['curved-one','excluded']}]),keep=[True,False])
    d=dict(entries=[dict(observation_ids=['conditional-one'],norad=22)],
        families=[SimpleNamespace(entries=[dict(observation_ids=['mixture-one'],norad=33)])])
    inventory=population.native_inventory(p,d)
    assert inventory['owners']=={'curved-one':11,'conditional-one':22,'mixture-one':33}
    assert inventory['counts']=={'curved':1,'conditional_entries':1,'phase_mixture_families':1}
    d['families'][0].entries[0]['observation_ids']=['conditional-one']
    with pytest.raises(ValueError,match='duplicated'):
        population.native_inventory(p,d)


def test_numeric_timeout_audit_binds_exact_fallback_without_claiming_model_evidence(fake_policy,monkeypatch):
    import audit
    root,policy,record=fake_policy
    record['selected']=None
    write(root/'protocol.json',policy)
    monkeypatch.setattr(audit,'ROOT',root)
    monkeypatch.setattr(population.e,'load_case',lambda *a:(_ for _ in ()).throw(AssertionError('timeout fallback must not be presented as completed model replay')))
    output={a:dict(record['baseline'][a],source='exact_saved_ALGO07') for a in population.ARMS}
    row=dict(case=record['case'],dataset='FAKE',status='case_cap',accepted=False,
        baseline=record['baseline'],selected_output=output,protocol_sha256=population.sha(root/'protocol.json'),
        source_input_sha256=record['input_sha256'])
    write(root/'cases'/record['case']/'result.json',row)
    receipt=audit.audit(record['case'])
    assert receipt['status']=='passed_timeout_fallback_binding'
    assert 'Not evaluated' in receipt['full_native_scope']
    final=read(root/'cases'/record['case']/'audited_result.json')
    assert final['status']=='case_cap'
    assert final['selected_output']==output
