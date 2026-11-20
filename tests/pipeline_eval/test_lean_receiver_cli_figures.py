from copy import deepcopy

import pytest

from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.qualification import lean_receiver_cli_figures as figures


@pytest.fixture
def observation():
    ident = "fixture"
    solver = "smooth-clock"
    files = {key: {"path": f"/input/{key}", "sha256": key + "-digest"} for key in figures.app.FILES}
    tile = {"id": "r0", "center": [37.0, -122.0]}
    request = dict(files, mode="native", cutoff=12, catalog_timestamp=10, offer=tile)
    digest = figures.app.hex_sha(encoded(request))
    arms = {key: {"latlon": None, "forced_latlon": [37.0, -122.0]} for key in figures.app.ARMS}
    result = dict(status="withheld", reason="weak_position_geometry", arms=arms)
    parent = dict(
        id=ident,
        recording=ident,
        method="native_joint_clock_model",
        tile=tile,
        input_sha256=digest,
        native_sha256=files["native"]["sha256"],
        catalog_sha256=files["catalogue"]["sha256"],
        observation_sha256="graph",
        result=dict(result, boundary="audited pipeline", metrics={}),
    )
    replay = dict(
        id=ident,
        solver=solver,
        verified_against="native-clock-full",
        sealed_science_match=True,
        tile=tile,
        input_sha256=digest,
        observation_sha256="graph",
        input_files_sha256={key: rec["sha256"] for key, rec in files.items()},
        cutoff_utc_ns=12,
        catalogue_acquired_utc_ns=10,
        capture_utc_ns=14,
        interface_sha256=figures.app.hex_sha(
            encoded(dict(request=request, solver=solver, capture_utc_ns=14))
        ),
        worker_wall_s=1.0,
        address_space_limit_mib=512,
        memory_kib={"VmPeak": 40},
        source_sha256="portable-source",
        **deepcopy(result),
    )
    return replay, parent, request, solver, "omitted-tile", "native-clock-full"


def test_matched_output_keeps_withheld_status_parent_and_replay_identity(observation):
    replay, *_ = observation
    candidate, control = figures.matched_pair(*observation)
    assert candidate["method"] == "portable_native_clock"
    assert candidate["parent_method"] == control["method"] == "native_joint_clock_model"
    assert candidate["result"]["status"] == "withheld"
    assert candidate["result"]["arms"] is replay["arms"]
    assert all(candidate[key] == control[key] for key in figures.INPUTS)


@pytest.mark.parametrize("tampered", ["arm", "native", "parent-method"])
def test_matched_output_rejects_mismatched_factor_file_or_endpoint(observation, tampered):
    replay, parent, *_ = observation
    if tampered == "arm":
        replay["arms"]["fitted_c"]["latlon"] = [37.0, -122.0]
    elif tampered == "native":
        replay["input_files_sha256"]["native"] = "another detector archive"
    else:
        parent["method"] = "another worker"
    with pytest.raises(ValueError, match="changes sealed fields"):
        figures.matched_pair(*observation)
