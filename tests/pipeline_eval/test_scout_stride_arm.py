from tools.pipeline_eval.qualification.scout_stride_arm_eval import compare_host


def test_native_arm_comparator_keeps_mode_and_receiver_identity():
    host = {
        "payloads": {
            "control": {"rows": [{"score": 1}, {"score": 2}]},
            "stride": {"rows": [{"score": 3}, {"score": 4}]},
        }
    }
    arm = {
        "payloads": {
            "control": {"rows": [{"score": 1.0}, {"score": 2.0}]},
            "stride": {"rows": [{"score": 4}, {"score": 3}]},
        }
    }
    assert compare_host(arm, host) == {
        "control": {"exact_public_rows": 2},
        "stride": {"exact_public_rows": 0},
    }
