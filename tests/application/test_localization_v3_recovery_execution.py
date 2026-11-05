from leo.application import localization_v3 as application


def test_checkpoint_forwards_arm_mapper_and_keeps_stage_capture(monkeypatch):
    mapper, captured = object(), []

    def recover(context, inventory, **kwargs):
        assert kwargs['map_inclusion_arms'] is mapper
        assert kwargs['run_stage']('inclusion', lambda: 123) == (True, 123)
        kwargs['on_selection']({'selected': 1})
        captured.append((context, inventory))
        return {'decision': 'retained'}

    monkeypatch.setattr(application, 'recover_tracks', recover)
    ticks = iter([10., 12.])
    prepared = dict(status='track_recovery_prepared', recovery_context={}, inventory={})
    result = application.recover_predictive_checkpoint(
        prepared, run_stage=lambda name, op: (True, op()), discovery_allowed=lambda: True,
        clock=lambda: next(ticks), inventory_seconds=3., map_inclusion_arms=mapper)
    assert captured == [({}, {})]
    assert result['completed_stages']['inclusion'] == dict(value=123, seconds=2.)
    assert result['selected_state'] == {'selected': 1}
