import pytest
from simultaneous_tracks import selected_job


def test_fixed_opportunities_keep_original_output_separate():
    unit, tracks, old = selected_job(None)
    assert (unit, tracks) == ("DS7-F069", (7, 17))
    outputs = [selected_job(k)[2] for k in range(4)]
    assert len(set(outputs)) == 4 and old not in outputs
    assert selected_job(3)[:2] == ("DS7-F042", (46, 51))
    with pytest.raises(ValueError):
        selected_job(4)
