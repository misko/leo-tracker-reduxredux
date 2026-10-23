import pytest
from repair_algo04_phase_metadata import normalize_arms


def test_phase_convergence_is_copied_from_history_without_changing_existing_value():
    arms={'c0':dict(history=[dict(phase_change_s=.02)]),'fitted_c':dict(final_phase_change_s=.001,history=[dict(phase_change_s=.5)])}
    changed=normalize_arms(arms)
    assert changed['c0']['final_phase_change_s']==.02
    assert changed['fitted_c']['final_phase_change_s']==.001
    assert 'final_phase_change_s' not in arms['c0']
    with pytest.raises(KeyError):normalize_arms({'c0':{}})
