import pytest

from tools.pipeline_eval.qualification.prepared_capture_waveform_results import joined_cache


def test_each_prepared_cache_receipt_is_bound_to_its_original_physical_visit():
    visits = [
        dict(visit=13, grid_calls=0, status="invalid_capture"),
        dict(visit=17, grid_calls=2, status="processed"),
    ]
    readings = [
        dict(ordinal=0, calls=0, cache_hits=0, cold_builds=0, filter_ffts=0, input_ffts=0),
        dict(ordinal=1, calls=2, cache_hits=1, cold_builds=1, filter_ffts=252, input_ffts=6),
    ]
    assert joined_cache(visits, readings, {17}) == [dict(readings[1], visit=17, status="processed")]
    readings[1]["cache_hits"] = 2
    with pytest.raises(ValueError, match="actual detector work"):
        joined_cache(visits, readings, {17})
    with pytest.raises(ValueError, match="different visit counts"):
        joined_cache(visits, readings[:1], {17})
