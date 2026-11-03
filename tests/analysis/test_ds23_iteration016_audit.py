import audit_ds23_iteration016_recovery as study


def test_all_audit_modules_bound_to_frozen016_evidence():
    study.configure()
    assert study.audit.RAW == study.binding.runner.RAW
    assert study.audit.step.runner is study.binding.runner
    assert study.augmented.study.runner is study.binding.runner
    assert study.audit.step.OUT.parent == study.binding.runner.RAW
    assert study.augmented.study.OUT.parent == study.binding.runner.RAW
