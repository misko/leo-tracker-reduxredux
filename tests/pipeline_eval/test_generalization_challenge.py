import numpy as np

from tools.pipeline_eval.qualification import generalization_challenge as study
from tools.pipeline_eval.qualification import generalization_challenge_scenes as scenes
from tools.pipeline_eval.scoring import validate_result


def test_offered_distance_uses_wgs84_face_and_changes_sign_outside():
    for site in ([68.4, -130.2], [-35.7, 169.1]):
        for axis in (0, 1):
            for cleared in scenes.CONDITIONS.values():
                target = np.array([-5.0, 3.0])
                target[axis] = -12.5 + cleared
                center = scenes.offer_center(site, target)
                assert np.allclose(scenes.local(site, center), target, atol=1e-6)
                assert np.isclose(scenes.clearance(site, center), cleared, atol=1e-6)


def test_prepared_path_keeps_paired_fit_or_marks_missing():
    result = study.missing("timed_out", "fixture wall cap")
    row = dict(
        method=study.CLOCK,
        result=result,
        prepared_equal=True,
        prepared_result=result,
        prepared_projection_sha256="same",
    )
    prepared = study.prepared(row)
    assert prepared["method"] == study.PREPARED
    assert prepared["result"] == result
    validate_result(prepared["result"])
    missing = study.prepared(dict(method=study.CLOCK, result=result))
    assert missing["result"]["status"] == "missing"
    assert missing["result"]["arms"] == result["arms"]
    validate_result(missing["result"])
