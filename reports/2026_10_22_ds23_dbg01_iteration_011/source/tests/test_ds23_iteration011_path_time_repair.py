import repair_ds23_iteration011_path_times as repair


def test_repair_uses_current_parents_and_fresh_v2_output_without_replacing_the_old_source():
    repair.configure()
    assert repair.paths.runner is repair.runner
    assert repair.paths.OUT==repair.OUT and repair.OUT!=repair.OLD
    assert repair.paths.native.append_native_paths is repair.append_exact
    assert repair.ORIGINAL_APPEND is not repair.append_exact
