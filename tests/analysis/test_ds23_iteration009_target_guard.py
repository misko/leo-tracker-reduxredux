from repair_ds23_iteration009_targets import whole_targets


def test_whole_track_nomination_never_receives_an_active_or_partial_component():
    ranking=[dict(component='whole',points=20,original_points=20),
        dict(component='partial',points=12,original_points=40),dict(component='active',points=20,original_points=20)]
    original=dict(ranking=ranking,accepted_observation_ids=['keep'])
    filtered=whole_targets(original,{'active'})
    assert [r['component'] for r in filtered['ranking']]==['whole']
    assert original['ranking']==ranking and len(original['ranking'])==3
    assert filtered['accepted_observation_ids']==['keep']


def test_repair_binds_every_dependent_reentry_path():
    import repair_ds23_iteration009_targets as repair
    repair.configure()
    assert repair.engine.reentry.OUT==repair.OUT
    assert repair.engine.support.NOMINATIONS==repair.OUT
    assert repair.engine.finalize.OLD==repair.OUT
    assert repair.engine.audit.REENTRY==repair.OUT


def test_following_track_diagnostic_uses_current_original_endpoints_and_output():
    import diagnose_ds23_iteration009_tracks as diagnostic
    diagnostic.configure()
    assert diagnostic.diagnostic.OUT==diagnostic.OUT
    assert diagnostic.diagnostic.runner is diagnostic.repair.runner
