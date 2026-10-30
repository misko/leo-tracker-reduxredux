from refine_graph_inclusion_constraints import residual_only_jobs


def test_refinement_requires_residual_failure_and_excludes_any_owner_failure():
    jobs=[dict(track_id=i) for i in range(5)]
    def row(i,failures):return dict(track_id=i,rows=[dict(compatible=not failures,failures=failures)],linear_rows=[])
    audit=dict(results=[row(0,[]),row(1,['conditional_residual']),row(2,['multiple_orbital_owners_required']),
        row(3,['conditional_residual']),row(3,['multiple_orbital_owners_required']),
        dict(track_id=4,rows=[],linear_rows=[dict(compatible=False,failures=['predictive_noise_structure'])])])
    assert residual_only_jobs(jobs,audit)==[jobs[1],jobs[4]]
