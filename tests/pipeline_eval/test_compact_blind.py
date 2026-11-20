import numpy as np
import pytest

from tools.pipeline_eval.qualification import compact_blind_generator as generator
from tools.pipeline_eval.qualification import compact_blind_results as results


@pytest.mark.parametrize("point", [(44.0, 93.0), (-31.0, -54.0)])
@pytest.mark.parametrize("axis", [0, 1])
def test_offers_straddle_one_near_face_using_receiver_frame(point, axis):
    for sign in (-1, 1):
        containing = generator.regional_offer(point, axis, sign, 8.0)
        omitted = generator.regional_offer(point, axis, sign, 14.0)
        assert max(map(abs, generator.local_offset(point, containing))) == pytest.approx(8.0)
        assert max(map(abs, generator.local_offset(point, omitted))) == pytest.approx(14.0)


def test_propagation_has_hidden_additional_clock_phase():
    class Satellite:
        def sgp4_array(self, julian, fraction):
            return julian, fraction

    time = np.array([0.0, 0.75])
    wrapped = generator.Emitter(Satellite(), -0.3)
    _, evaluation_time = wrapped.sgp4_array(None, time)
    np.testing.assert_allclose(evaluation_time, time - 0.3 / 86_400)


def test_omitted_regional_publication_counts_even_inside_five_km():
    truth = [30.0, -7.0]
    tile = generator.regional_offer(truth, 1, 1, 14.0)
    endpoint = [truth[0] + 2.0 / 111, truth[1]]
    row = dict(
        id="query",
        method="phase-release",
        native_sha256="native",
        input_sha256="input",
        catalogue_sha256="tle",
        worker_wall_s=1.0,
        worker_cpu_s=0.6,
        peak_rss_kib=50,
        result=dict(status="ok", arms=dict(c0=dict(latlon=endpoint, rf_rms_hz=34.8))),
    )
    target = dict(site=truth, condition="omitted")
    scored = results.row_score(row, dict(session="capture", tile=tile), target, "c0")
    assert scored["published_inside_offer"] is True
    assert scored["geographic_error_km"] < 5
    assert scored["false_publication"] is True
    assert scored["rf_rms_hz"] == 34.8
    assert scored["cpu_s"] is None and scored["rss_kib"] is None
