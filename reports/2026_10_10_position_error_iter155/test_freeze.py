"""Pure projection fixtures; no historical receipt/model/recording access."""
import copy
import pytest
from freeze import project_receipt,write_projections


def test_only_exact_published_narrative_update_is_admitted():
    from freeze import inherited_digest,NARRATIVE_PATH,NARRATIVE_OLD,NARRATIVE_NEW
    accepted,receipt=inherited_digest('input_sha256',NARRATIVE_PATH,NARRATIVE_OLD,NARRATIVE_NEW)
    assert accepted==NARRATIVE_NEW and receipt['commit']=='ac82b3a'
    assert receipt['old_sha256']==NARRATIVE_OLD and receipt['new_sha256']==NARRATIVE_NEW
    for group,path,old,new in [
        ('source_sha256',NARRATIVE_PATH,NARRATIVE_OLD,NARRATIVE_NEW),
        ('input_sha256','other/README.md',NARRATIVE_OLD,NARRATIVE_NEW),
        ('input_sha256',NARRATIVE_PATH,'wrong',NARRATIVE_NEW),
        ('input_sha256',NARRATIVE_PATH,NARRATIVE_OLD,'wrong'),
    ]:
        with pytest.raises(ValueError):inherited_digest(group,path,old,new)
    assert inherited_digest('input_sha256','other','same','same')==('same',None)


def receipt():
    vector=[0.]*8;clock=[0.]*6
    state=dict(stage='B7',vector=vector,clock_coefficients=clock,
        receiver_baseline_hz=[0.,0.],clock_nodes_s=[0.,1.],satellite_centers_s=[0.],total_objective=3.,
        position_error_km=999.)
    fit=dict(vector=vector,clock_coefficients=clock,objective=3.,converged=True,
             joint_state=state,posterior_rms_hz=99.,reference=[1.,2.])
    operations={arm:dict(arm=arm,accepted_stage='B7',satellites=[1],region_source='B7',basin='point:0:0',fit=copy.deepcopy(fit),error_km=77.) for arm in ['zero-c','fitted-c']}
    return dict(label='x',branch='native',status='complete',protocol_sha256='control',
                operational=operations,attempts={stage:{arm:copy.deepcopy(fit) for arm in operations} for stage in ['B3','B4','B4W','B5','B7']},reference=[1,2])


def test_exact_projection_whitelist_no_outcomes_and_none_preserved():
    original=receipt();original['attempts']['B4W']['zero-c']=None
    original['attempts']['B5']['fitted-c']=None
    before=copy.deepcopy(original)
    result=project_receipt(original,'x','control')
    assert original==before and result['attempts']['B4W']['zero-c'] is None
    assert set(result)=={'label','branch','status','protocol_sha256','operational','attempts'}
    assert result['protocol_sha256']=='control'
    assert 'error_km' not in result['operational']['zero-c']
    assert 'reference' not in result['operational']['zero-c']['fit']
    assert 'position_error_km' not in result['operational']['zero-c']['fit']['joint_state']


@pytest.mark.parametrize('change',['digest','label','branch','stage','identity','chain','locks','objective'])
def test_invalid_identity_is_rejected_never_filtered(change):
    r=receipt()
    if change=='digest':r['protocol_sha256']='foreign'
    if change=='label':r['label']='other'
    if change=='branch':r['branch']='zero'
    if change=='stage':r['operational']['fitted-c']['accepted_stage']='B5'
    if change=='identity':r['operational']['fitted-c']['fit']['objective']=4.
    if change=='chain':r['attempts']['B3']['fitted-c']=None
    if change=='locks':
        for fit in [r['operational']['zero-c']['fit'],r['attempts']['B7']['zero-c']]:fit['vector'][6]=1.
    if change=='objective':
        for fit in [r['operational']['fitted-c']['fit'],r['attempts']['B7']['fitted-c']]:fit['joint_state']['total_objective']=4.
    with pytest.raises(ValueError):project_receipt(r,'x','control')


def test_projection_publication_is_exclusive(tmp_path,monkeypatch):
    import freeze
    monkeypatch.setattr(freeze,'ROOT',tmp_path)
    write_projections({'selected/x.json':b'{}'})
    with pytest.raises(FileExistsError):write_projections({'selected/x.json':b'changed'})
    assert (tmp_path/'selected/x.json').read_bytes()==b'{}'
