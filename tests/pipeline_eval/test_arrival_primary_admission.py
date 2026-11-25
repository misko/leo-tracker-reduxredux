from pathlib import Path

import arrival_primary_0049_admission as admission
import pytest


@pytest.mark.parametrize("duration", [0, 121])
def test_watch_refuses_to_open_outside_its_registered_opportunity(duration):
    with pytest.raises(ValueError, match="one bounded passive"):
        admission.watch(1, duration)


def test_worker_cannot_accept_a_different_output_or_packet():
    with pytest.raises(ValueError, match="authenticated prepared packet"):
        admission.checked(Path("/tmp/unrelated-output"), admission.PLAN_PIN)
    with pytest.raises(ValueError, match="authenticated prepared packet"):
        admission.checked(admission.ROOT, "a" * 64)
