import probe_ds23_iteration014_step_transfer as study


def test_transfer_uses_the_original013_rules_and_correct014_parent():
    choice=study.default.choose;predicate=study.diagnostic.only_step_fails
    assert study.configure('diagnostic') is study.diagnostic
    assert study.diagnostic.runner is study.runner
    assert study.configure('default') is study.default
    assert study.configure('support') is study.support
    assert study.support.previous is study.default and study.support.runner is study.runner
    assert study.default.choose is choice and study.diagnostic.only_step_fails is predicate
