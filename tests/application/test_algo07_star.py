from leo.application.algo07_star import ALGORITHMS, Stage, run


def make_stages(calls, *, failed=None, complete=()):
    def execute(name, previous):
        calls.append((name, previous))
        return dict(state='failed' if name == failed else 'complete', name=name)
    return [Stage(name, 1200, lambda _, n=name: n in complete,
                  lambda previous, n=name: execute(n, previous)) for name in ALGORITHMS]


def test_one_coordinator_preserves_order_and_incumbent_chain():
    calls = []
    result = run(make_stages(calls), {'native': True}, clock=lambda: 0)
    assert result['state'] == 'scientific_complete'
    assert [c[0] for c in calls] == list(ALGORITHMS)
    assert calls[0][1] == {'native': True}
    assert [c[1]['name'] for c in calls[1:]] == list(ALGORITHMS[:-1])


def test_stage_failure_cannot_publish_a_later_success():
    calls = []
    result = run(make_stages(calls, failed='ALGO04'), {}, clock=lambda: 0)
    assert result['state'] == 'stage_failed'
    assert [c[0] for c in calls] == ['ALGO02', 'ALGO03', 'ALGO04']


def test_stop_at_boundary_instead_of_shortening_production_budget():
    calls = []
    result = run(make_stages(calls), {}, maximum_seconds=1200, clock=lambda: 0)
    assert result['state'] == 'checkpointed' and result['next_stage'] == 'ALGO02'
    assert calls == []


def test_completed_checkpoints_are_verified_even_when_slice_has_little_time():
    calls = []
    result = run(make_stages(calls, complete=ALGORITHMS), {}, maximum_seconds=1,
                 clock=lambda: 0)
    assert result['state'] == 'scientific_complete' and len(calls) == 6


def test_explicit_stage_boundary_retains_next_step():
    calls = []
    result = run(make_stages(calls), {}, through='ALGO02', clock=lambda: 0)
    assert result['next_stage'] == 'ALGO03' and len(calls) == 1


def test_contended_stage_is_not_success():
    stages = make_stages([])
    stages[0] = Stage('ALGO02', 1200, lambda _: False, lambda _: None)
    result = run(stages, {}, clock=lambda: 0)
    assert result['state'] == 'owned_elsewhere'
