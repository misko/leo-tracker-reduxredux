"""Independent recovery arms preserve frozen serial control/addition decisions."""

import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import algo07v3_prerecovery_arms_oracle as oracle
import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import recovery_inclusion as owned
from leo.operations.localization_v3_parallel import ParallelFitFailure, map_initial_arms


def test_serial_oracle_is_frozen():
    assert hashlib.sha256(Path(oracle.__file__).read_bytes()).hexdigest() == (
        '93b7f6871b5884f5f09c994fe883799ed9d3192de9ef6e4677d640d02851e5bc'
    )


def fixture(monkeypatch, *, fail=False, numerical=False):
    targets = [dict(component='new', candidate_index=1, norad=20,
                    observation_ids=['new'], track_index=0)]
    context = dict(entries=[], means=np.zeros(1), keep=np.ones(1, bool), powers=np.ones(1),
                   model={}, scan=SimpleNamespace(tracks=[], white=[]))
    if numerical:
        context['numerical_policy'] = SimpleNamespace(calls=[])
    inventory = dict(policy={a: dict(proposed_associated_ids=['old']) for a in owned.ARMS})

    def problem(d, arm, reference, entries, **kwargs):
        if fail and arm == 'fitted_c':
            raise RuntimeError('recovery arm failed')
        if numerical:
            d['numerical_policy'].calls.append(arm)
        return SimpleNamespace(
            arm=arm, reference=reference, labels=np.array([0]), keep=np.ones(1, bool),
            calculate=lambda x: dict(elevation=np.ones(1), negative_twice_elbo=float(x @ x)),
            state=lambda x: dict(phases=reference + 0.001), linear_entries=[], linear_slices=[],
        )

    def summary(p, x, entries):
        return dict(endpoint_east_north_km=x.copy(), reference=p.reference.copy(),
                    arm=p.arm, linear_calibration_max_difference=0., linear_gates=[],
                    negative_twice_elbo=float(x @ x))

    class Family:
        def __init__(self, *args, **kwargs):
            self.receipt = dict(phase_step_s=kwargs['phase_step'])

        def evaluate(self, p, x, *args, details=False):
            return (dict(negative_twice_log_density=2., gates=[], phase_boundary_mass=0.)
                    if details else 2.)

    def minimize(d, original, objective, x, **kwargs):
        y = x + np.array([0.01, -0.02])
        return SimpleNamespace(x=y, fun=objective(y), success=True, message='done', nfev=1)

    for module in (oracle, owned):
        monkeypatch.setattr(module, '_targets', lambda d, *a, **k: (d, targets, [], [], 0))
        monkeypatch.setattr(module, '_problem', problem)
        monkeypatch.setattr(module, 'fit', lambda p, x, **k: dict(parameters=x + 0.01))
        monkeypatch.setattr(module, 'summary', summary)
        monkeypatch.setattr(module, 'original_graph_view', lambda p, count: p)
        monkeypatch.setattr(module, 'memberships', lambda *a: (None, None, {'old', 'new'},
                                                             {'old': 10, 'new': 20}))
        monkeypatch.setattr(module, 'pair_passes', lambda *a, **k: True)
        monkeypatch.setattr(module, 'exact_shared_replay', lambda *a: dict(
            phases_in_bounds=True, maximum_phase_linearization_error_hz=0.01))
        monkeypatch.setattr(module, 'NewFamily', Family)
        monkeypatch.setattr(module, 'resolution_audit', lambda *a: dict(local_agreement=True))
    monkeypatch.setattr(owned.numerics, 'refresh', lambda d, p, phase, reference:
                        (phase.copy(), dict(phase_change_s=0.001)))
    monkeypatch.setattr(owned.numerics, 'minimize', minimize)
    return context, inventory, []


@pytest.mark.parametrize('kind,kwargs', [
    ('fit_shared', {}), ('fit_shared', dict(conditional_satellite_refresh=True)),
    ('fit_new', {}), ('fit_new', dict(optimizer='powell')),
])
@pytest.mark.parametrize('mapper', [None, map_initial_arms])
def test_complete_trials_match_frozen_serial(monkeypatch, kind, kwargs, mapper):
    args = fixture(monkeypatch)
    expected = getattr(oracle, kind)(*copy.deepcopy(args), **kwargs)
    actual = getattr(owned, kind)(*copy.deepcopy(args), map_arms=mapper, **kwargs)
    assert fingerprint(actual) == fingerprint(expected)
    for value in list(actual.values())[1:]:
        assert list(value['arms']) == ['c0', 'fitted_c']
        assert all(len(row['history']) == 5 for row in value['arms'].values())


@pytest.mark.parametrize('kind', ['fit_shared', 'fit_new'])
def test_mutable_numerical_receipts_stay_in_parent(monkeypatch, kind):
    args = fixture(monkeypatch, numerical=True)

    def forbidden(*args):
        raise AssertionError('mutable policy must remain serial')

    reference_args = copy.deepcopy(args)
    expected = getattr(oracle, kind)(*reference_args)
    actual = getattr(owned, kind)(*args, map_arms=forbidden)
    assert args[0]['numerical_policy'].calls == reference_args[0]['numerical_policy'].calls
    assert len(args[0]['numerical_policy'].calls) == 20
    assert fingerprint(actual) == fingerprint(expected)


@pytest.mark.parametrize('kind', ['fit_shared', 'fit_new'])
def test_failed_child_aborts_instead_of_becoming_a_rejection(monkeypatch, kind):
    args = fixture(monkeypatch, fail=True)
    with pytest.raises(ParallelFitFailure, match='recovery arm failed'):
        getattr(owned, kind)(*args, map_arms=map_initial_arms)
