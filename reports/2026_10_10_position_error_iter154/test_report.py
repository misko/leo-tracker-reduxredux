import json
import pytest
from report import build, sealed_cells


def plan():
    return dict(members=[dict(label=str(i), dataset='DS16') for i in range(12)],
                source_sha256={}, input_sha256={}, evaluation_source_sha256={},historical_control_sha256={})


def digest(value):
    return value.get('execution_condition', 'base')


def receipts(folder, p):
    for member in p['members']:
        for condition in ['control', 'repair']:
            for branch in ['native', 'zero']:
                path = folder/member['label']/condition/branch/'result.json'
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(dict(protocol_sha256=condition,
                    label=member['label'], branch=branch, status='failed', fallback_available=False)))


def test_all48_gate_rejects_missing_pending_foreign_before_eval(tmp_path):
    p = plan(); receipts(tmp_path, p)
    assert len(sealed_cells(p, tmp_path, digest)) == 48
    path = tmp_path/'0/control/native/result.json'
    for change in ['pending', 'foreign', 'missing']:
        original = path.read_text(); row = json.loads(original)
        if change == 'pending': row['status'] = 'pending'
        if change == 'foreign': row['protocol_sha256'] = 'repair'
        if change == 'missing': path.unlink()
        else: path.write_text(json.dumps(row))
        with pytest.raises(ValueError):
            build(p, tmp_path, digest, evaluation_factory=lambda *a:pytest.fail('reference opened'))
        path.write_text(original)


def test_source_tamper_precedes_terminal_or_eval(tmp_path):
    p = plan();p['source_sha256']={'reports/2026_10_10_position_error_iter154/report.py':'wrong'}
    with pytest.raises(ValueError, match='closure changed'):
        build(p,tmp_path,digest,evaluation_factory=lambda *a:pytest.fail('reference opened'))


@pytest.mark.parametrize('selected',[False,True])
def test_full_report_keeps_policies_cells_and_failed_denominators(tmp_path,selected):
    p=plan();receipts(tmp_path,p)
    for member in p['members']:
        search=tmp_path/member['label']/'sealed/search';search.mkdir(parents=True)
        member['sealed_search_path']=str(search)
        (search/'result.json').write_text(json.dumps(dict(status='complete',searches={})))
        for branch in ['native','zero']:
            old=search.parent/branch/'result.json';old.parent.mkdir()
            old.write_text(json.dumps(dict(status='complete',operational={})))
        if selected:
            for condition in ['control','repair']:
                for branch in ['native','zero']:
                    path=tmp_path/member['label']/condition/branch/'result.json'
                    row=json.loads(path.read_text());row['status']='complete'
                    row['operational']={arm:dict(fit=dict(converged=True,objective=1.,vector=[0.]*9)) for arm in ['zero-c','fitted-c']}
                    path.write_text(json.dumps(row))
    call=[]
    def factory(plan,rows):
        policy=len(call);call.append(1)
        def evaluate(label,alias,arm,operation):
            assert selected
            return (10 if policy==0 else 30)+(0 if alias=='native' else -1)+(0 if arm=='fitted-c' else 2)
        return evaluate
    summary=build(p,tmp_path,digest,evaluation_factory=factory)
    assert len(call)==2 and summary['all48_terminal']
    for policy in ['native','zero']:
        s=summary['policies'][policy];assert len(s['rows'])==12
        assert s['comparison_labels']['fixed']=='own-arm-repair'
        if selected:
            expected=10 if policy=='native' else 30
            assert s['rows'][0]['arms']['fitted-c']['native']['error_km']==expected
            assert s['rows'][0]['arms']['fitted-c']['fixed']['error_km']==expected-1
            assert s['progression']['passed']
        else:
            assert not s['progression']['passed']
            assert len(s['rows'][0]['regions']['fixed'])==3
            assert s['rows'][0]['regions']['fixed'][0]['finals'] is None
