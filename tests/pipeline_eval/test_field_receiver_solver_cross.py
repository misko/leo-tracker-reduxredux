from copy import deepcopy

import pytest

from field_receiver_solver_cross import contrasts, exact_charted_policy


def test_interaction_uses_matched_receiver_and_solver_contrasts():
    values = {"installed/full": 10, "installed/mixed": 18, "charted/full": 13, "charted/mixed": 20}
    assert contrasts(values) == dict(receiver_under_installed=8, receiver_under_charted=7,
                                     solver_on_full=3, solver_on_mixed=2, interaction=-1)
    assert contrasts(values | {"installed/mixed": None}) is None


def test_charted_policy_preserves_configuration_with_different_branch_outcomes():
    witness = dict(source_sha256={'path': 'sha'}, solver_recipe=dict(specification_solver='named',
                   history_risk=dict(requested=True, optional_prefit_exterior_probe=False, choice='lean')))
    alternate = deepcopy(witness)
    alternate['solver_recipe']['history_risk']['choice'] = 'fallback'
    exact_charted_policy(witness, alternate)
    alternate['solver_recipe']['history_risk']['optional_prefit_exterior_probe'] = True
    with pytest.raises(ValueError, match='configured policies'):
        exact_charted_policy(witness, alternate)
    alternate = deepcopy(witness)
    alternate['source_sha256']['path'] = 'other'
    with pytest.raises(ValueError, match='source bytes'):
        exact_charted_policy(witness, alternate)
