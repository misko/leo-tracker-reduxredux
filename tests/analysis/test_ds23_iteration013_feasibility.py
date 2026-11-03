import probe_ds23_iteration013_feasibility as study


def test_existing_near_feasible_rule_is_transferred_without_relaxing_its_trigger():
    module=study.configure()
    assert module.binding.runner is study.binding.runner
    assert module.OUT==study.binding.runner.RAW/'temporal_feasibility'
    assert module.eligible(dict(arms={},accepted=False,paired_valid=False),[-.24,-.20])
    assert not module.eligible(dict(arms={},accepted=False,paired_valid=False),[-.26,-.20])
    assert not module.eligible(dict(arms={},accepted=True,paired_valid=True),[.1,.2])
