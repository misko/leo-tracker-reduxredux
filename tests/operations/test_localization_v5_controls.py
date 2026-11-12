from copy import deepcopy

import pytest

from leo.analysis.localization_v3 import recovery_controller
from leo.analysis.localization_v5.control_reuse import ControlReuseFailure
from leo.contracts.localization_v5 import inclusion_control_policy, validate_inclusion_control_work
from leo.operations.localization_v5_controls import ControlCacheFactory
from tests.analysis.test_localization_v3_recovery_controller import execute, setup
from tests.analysis.test_localization_v5_control_reuse import fixture, value


def test_factory_scopes_caches_and_publishes_bound_actual_work():
    context, inventory, bound = fixture()
    factory = ControlCacheFactory(bound, inclusion_control_policy())
    first, second = factory(), factory()
    args = (True, 'fit_shared', context, inventory, 2, False)
    first.pair(value, *args)
    first.pair(value, *args)
    second.pair(value, *args)
    work = factory.provenance()
    assert work['counts'] == dict(requests=3, computed=2, reused=1, failed=0,
                                  unkeyable=0, in_progress=0)
    assert len(work['invocations']) == 2
    assert validate_inclusion_control_work(work, factory.policy,
                                          work['backend_manifest_sha256']) is work
    factory.policy['normalized_lists'].clear()
    assert factory.policy == inclusion_control_policy()
    bound.manifest['changed'] = True
    with pytest.raises(ControlReuseFailure, match='manifest binding changed'):
        factory.provenance()
    with pytest.raises(ControlReuseFailure, match='manifest binding changed'):
        first.pair(value, *args)


@pytest.mark.parametrize('failure', ['binding', 'partial'])
def test_integrity_failures_escape_controller_instead_of_becoming_scientific_rejection(
    monkeypatch, failure
):
    context, inventory, bound = fixture()
    evidence = setup(monkeypatch, shared=True)
    factory = ControlCacheFactory(bound, inclusion_control_policy())

    def fails(*args, control_cache, **kwargs):
        if failure == 'binding':
            bound.manifest['changed'] = True
        compute = value if failure == 'binding' else lambda: {'c0': {}}
        return control_cache.pair(compute, True, 'fit_shared', context, inventory, 2, False)

    monkeypatch.setattr(recovery_controller, 'fit_shared', fails)
    with pytest.raises(ControlReuseFailure):
        recovery_controller.recover_tracks(
            context, evidence, run_stage=execute, discovery_allowed=lambda: True,
            inclusion_control_factory=factory)


@pytest.mark.parametrize('change', ['binding', 'policy', 'missing', 'bool', 'sum', 'extra'])
def test_saved_work_rejects_changed_bindings_or_counts(change):
    _, _, bound = fixture()
    factory = ControlCacheFactory(bound, inclusion_control_policy())
    factory()
    expected = factory.provenance()
    work = deepcopy(expected)
    if change == 'binding':
        work['backend_manifest_sha256'] = 'other'
    elif change == 'policy':
        work['policy']['scan'] = 'omit geometry'
    elif change == 'missing':
        del work['counts']['computed']
    elif change == 'bool':
        work['counts']['reused'] = False
    elif change == 'sum':
        work['invocations'][0].update(requests=1, computed=1)
    else:
        work['extra'] = True
    with pytest.raises(ValueError):
        validate_inclusion_control_work(work, factory.policy, expected['backend_manifest_sha256'])
