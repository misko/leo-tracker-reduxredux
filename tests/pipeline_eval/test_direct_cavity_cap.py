from copy import deepcopy
from pathlib import Path

import pytest

from tools.pipeline_eval.qualification import direct_cavity_cap as cap
from tools.pipeline_eval.qualification import direct_cavity_cap_bundle as bundle
from tools.pipeline_eval.qualification.direct_cavity_cap_results import verify_attempt
from tools.pipeline_eval.variants import v5_direct_cavity, v5_lean


def test_bundle_changes_only_the_preparation_parser():
    original = Path(v5_direct_cavity.__file__).read_text()
    staged = bundle.bounded_source(original)
    assert staged.count("element_parser=ElementParser(maximum_bytes=0)") == 1
    for before, after in bundle.REPLACEMENTS:
        staged = staged.replace(after, before)
    assert staged == original


@pytest.mark.parametrize("source", ("", "    screen_longitude_deg=screen_center[1],\n"))
def test_bundle_rejects_an_unrecognized_donor(source):
    with pytest.raises(ValueError, match="unrecognized direct cavity"):
        bundle.bounded_source(source)


def measured_oom():
    sampled = {"memory.max": cap.MEMORY, "memory.swap.max": 0, "memory.swap.current": 0}
    return dict(
        id="test",
        cpu=4,
        proof=[dict(sampled, cpu=4, nice=10)],
        live=[dict(sampled)],
        stages=[dict(sampled)],
        wall_s=23.0,
        service_result="oom-kill",
        kernel=dict(Result="oom-kill", MemoryPeak=str(cap.MEMORY), ExecMainStatus="9"),
        result=v5_lean._no_fix("Kernel OOM kill at 512 MiB", status="failed"),
    )


def test_oom_receipt_preserves_null_arms_and_bounded_kernel_authority():
    measured = measured_oom()
    verify_attempt(measured, {"id": "test"}, 4)
    simulated = deepcopy(measured)
    simulated["kernel"]["MemoryPeak"] = str(cap.MEMORY - 1)
    with pytest.raises(ValueError, match="kernel OOM"):
        verify_attempt(simulated, {"id": "test"}, 4)
    simulated = deepcopy(measured)
    simulated["live"][0]["memory.swap.max"] = 16
    with pytest.raises(ValueError, match="measured service limit"):
        verify_attempt(simulated, {"id": "test"}, 4)
    measured["result"]["arms"]["c0"]["latlon"] = [37.0, -122.0]
    with pytest.raises(ValueError, match="absent position arms"):
        verify_attempt(measured, {"id": "test"}, 4)
