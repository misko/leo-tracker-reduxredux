import pytest
import run_supported_graph_inclusions as runner


def test_only_supported_engine_rows_and_no_error_selection(monkeypatch):
    monkeypatch.setattr(runner, 'identity_consensus', lambda folds, score_name: folds)
    rows = [dict(track_id='a', engine_member=True, error_km=99),
            dict(track_id='b', engine_member=False, error_km=0),
            dict(track_id='c', engine_member=True, error_km=0)]
    results = {key: dict(folds=dict(status=status)) for key, status in
               [('a', 'conditionally_supported_identity'), ('b', 'conditionally_supported_identity'),
                ('c', 'ambiguous_identity')]}
    assert [j['track_id'] for j in runner.supported_jobs(rows, results)] == ['a']
    with pytest.raises(ValueError, match='repeated track'):
        runner.supported_jobs([rows[0], rows[0]], results)


def test_terminal_failures_remain_explicit_and_live_claims_cannot_be_reused(tmp_path):
    from debug_fast_graph_unassociated import write
    attempt=tmp_path/'attempt-1';attempt.mkdir()
    rows=[dict(track_id=t,label=t) for t in ('a','b')]
    write(attempt/'selected.json',rows)
    write(attempt/'a-terminal.json',dict(status='complete'))
    with pytest.raises(ValueError,match='not terminal'):runner.completed_rows(tmp_path,['attempt-1'])
    write(attempt/'b-terminal.json',dict(status='timeout',reason='600s cap'))
    complete,excluded,_=runner.completed_rows(tmp_path,['attempt-1'])
    assert complete==rows[:1]
    assert excluded==[dict(track_id='b',label='b',execution='timeout',reason='600s cap')]


def test_single_target_is_fitted_once_but_multiple_targets_keep_joint_fit():
    from include_curved_family_annotations import fit_variants
    a,b=dict(row=1),dict(row=2)
    assert fit_variants([a])==[('control',[]),('target_0',[a])]
    assert fit_variants([a,b])==[('control',[]),('target_0',[a]),('target_1',[b]),('combined',[a,b])]
    assert fit_variants([a,b],True)==[('control',[]),('combined',[a,b])]
    with pytest.raises(ValueError,match='at least two'):fit_variants([a],True)
    with pytest.raises(ValueError,match='at least one'):fit_variants([])


def test_gate_audit_uses_targets_and_does_not_double_count_singleton_reuse(tmp_path):
    from audit_receiver_ramp_gates import target_paths
    for name in ('control.json','target_0.json','combined.json','receiver_hz_target.json'):(tmp_path/name).touch()
    assert [p.name for p in target_paths(tmp_path,True)]==['target_0.json']
    assert [p.name for p in target_paths(tmp_path)]==['receiver_hz_target.json']
