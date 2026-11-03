import copy
from run_ds23_reentry_family_cavity_full import repair_references


def test_recorded_fit_reference_repair_only_applies_to_matching_archived_history():
    arms=dict(c0=dict(phase_reference=[.2,.3],history=[dict(fit='original')]))
    original=copy.deepcopy(arms)
    previous=dict(baseline_arms=copy.deepcopy(arms),legacy_fit_reference_replay=dict(c0=dict(archived_reference=[.2,.3],replayed_fit_reference=[.19,.31])))
    result,repairs=repair_references(arms,previous)
    assert repairs==['c0'] and result['c0']['phase_reference']==[.19,.31] and arms==original
    other=dict(c0=dict(phase_reference=[.2,.3],history=[dict(fit='new hypothesis')]))
    result,repairs=repair_references(other,previous)
    assert repairs==[] and result==other
