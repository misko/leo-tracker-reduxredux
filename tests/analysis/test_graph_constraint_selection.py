from refine_graph_inclusion_constraints import residual_only_jobs


def test_refinement_requires_residual_failure_and_excludes_any_owner_failure():
    jobs=[dict(track_id=i) for i in range(5)]
    def row(i,failures):return dict(track_id=i,rows=[dict(compatible=not failures,failures=failures)],linear_rows=[])
    audit=dict(results=[row(0,[]),row(1,['conditional_residual']),row(2,['multiple_orbital_owners_required']),
        row(3,['conditional_residual']),row(3,['multiple_orbital_owners_required']),
        dict(track_id=4,rows=[],linear_rows=[dict(compatible=False,failures=['predictive_noise_structure'])])])
    assert residual_only_jobs(jobs,audit)==[jobs[1],jobs[4]]


def test_batch_records_and_forwards_reference_domain_limit(tmp_path,monkeypatch):
    import json
    from types import SimpleNamespace
    import refine_graph_inclusion_constraints as module
    batch=tmp_path/'source';batch.mkdir()
    job=dict(track_id='track',label='scan',inventory='inventory.json')
    (batch/'protocol.json').write_text(json.dumps(dict(jobs=[job])))
    (batch/'gate_audit.json').write_text(json.dumps(dict(results=[dict(track_id='track',
        rows=[dict(compatible=False,failures=['conditional_residual'])],linear_rows=[])])))
    commands=[]
    def supervise(command,*args):
        commands.append(command);return dict(status='complete')
    monkeypatch.setattr(module,'supervise',supervise)
    output=tmp_path/'result'
    module.run(SimpleNamespace(batch=batch,output=output,workers=1,reference_limit_s=30.))
    assert json.loads((output/'protocol.json').read_text())['reference_limit_s']==30.
    assert commands[0][commands[0].index('--reference-limit-s')+1]=='30.0'
