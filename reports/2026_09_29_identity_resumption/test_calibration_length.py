from calibration_length import common_evaluation


def test_only_shared_held_frames_are_compared():
    assert common_evaluation(dict(evaluation_frames=[1, 3]),
                             dict(evaluation_frames=[2, 3, 5, 8, 10, 11, 13])) == [3]
    assert common_evaluation(dict(evaluation_frames=[1]),
                             dict(evaluation_frames=[2])) == []
