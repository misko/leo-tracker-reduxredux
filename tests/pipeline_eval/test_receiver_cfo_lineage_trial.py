import gzip
import json
from importlib import import_module
from pathlib import Path

import pytest

trial = import_module("reports.ALGO08.single-core-2x.receiver_cfo_lineage_trial")
restore = import_module("reports.ALGO08.single-core-2x.receiver_cfo_restore_object")
MEASUREMENTS = Path(trial.__file__).parent / "measurements"


def load(name):
    return json.loads(gzip.decompress((MEASUREMENTS / name).read_bytes()))


def test_exact_factor_comparison_does_not_treat_signed_zero_as_equal():
    factor = (0, 13331, -0.0, 423000.0, 0.7, 0.04)
    assert trial.same_factor(factor, factor)
    assert not trial.same_factor(factor, (0, 13331, 0.0, *factor[3:]))


def test_object_selection_keeps_link_order_and_packed_cancellation(tmp_path):
    recipe = {"args": ["-shared", "-O3", "-Wl,--gc-sections", "timing.c", "variants/pilot_cancel.c",
                       "variants/delay_product_kernel.c", "-lm"]}
    archive = tmp_path / "archived"
    cancellation = tmp_path / "packed"
    flags, objects = restore.compiler_inputs(recipe, archive, cancellation)
    assert flags == ["-O3"]
    assert list(objects.values()) == [archive / "timing.o", cancellation / restore.PILOT,
                                      archive / restore.DELAY]
    with pytest.raises(ValueError, match="both"):
        restore.compiler_inputs({"args": ["other.c"]}, archive, cancellation)


def test_restored_kernels_match_saved_primary_timing_and_keep_packed_object():
    original = load("receiver-cfo-lineage-stage.json.gz")
    corrected = load("receiver-cfo-lineage-restoration.json.gz")
    build = corrected["correction"]
    assert {name for name, digest in build["original_objects"].items()
            if build["corrected_objects"][name] != digest} == {restore.DELAY}
    assert build["corrected_objects"][restore.PILOT] == restore.PACKED_SHA
    assert build["packed_sha256"] == restore.INPUT_SHA
    assert corrected["detections"] == original["detections"] == trial.DETECTION_PINS
    assert {(row["visit"], row["lane"], row["channel"])
            for row in corrected["rows"]} == set(trial.VISITS)
    for before, after in zip(original["rows"], corrected["rows"], strict=True):
        assert before["iq_sha256"] == after["iq_sha256"]
        stages = {row["build"]: row for row in before["builds"]}
        updated = {row["build"]: row for row in after["builds"]}
        deployed = stages["deployed"]["verification"]["factor"]
        for stage in before["builds"][:7]:
            assert trial.same_factor(deployed, stage["verification"]["factor"])
        deployed_scout = stages["deployed"]["scout"]
        assert stages["floating-pgo"]["scout"]["hz"] != deployed_scout["hz"]
        assert stages["paired-covariance"]["scout"]["hz"] == stages["floating-pgo"]["scout"]["hz"]
        assert updated["restored-delay-product"]["scout"] == deployed_scout
        assert updated["packed-cancellation"]["scout"] == stages["paired-covariance"]["scout"]
        restored = updated["restored-delay-product"]["verification"]["factor"]
        assert trial.same_factor(deployed[:4] + [0., 0.], restored[:4] + [0., 0.])
        score_deltas = [abs(a - b) for a, b in zip(deployed[4:], restored[4:], strict=True)]
        assert max(score_deltas) < 3e-14


def test_tracing_places_each_change_in_the_same_wrapped_request():
    plain = load("receiver-cfo-lineage-restoration.json.gz")
    traced = load("receiver-cfo-lineage-native-readout.json.gz")
    for before, after in zip(plain["rows"], traced["rows"], strict=True):
        captures = {}
        for left, right in zip(before["builds"], after["builds"], strict=True):
            assert left == {key: value for key, value in right.items() if key != "refinement"}
            if "refinement" in right:
                captures[right["build"]] = right["refinement"]
        stock = captures["packed-fractional"]
        assert stock["scalar_requests"] == [stock["requests"][0]]
        assert stock["requests"][0][0] == 0
        assert len(stock["requests"]) == 4
        assert stock == captures["restored-delay-product"]
        for name in ("floating-pgo", "paired-covariance", "packed-cancellation"):
            pgo = captures[name]
            assert {k: v for k, v in pgo.items() if k != "outputs"} == {
                k: v for k, v in stock.items() if k != "outputs"
            }
            assert pgo["outputs"][1:] == stock["outputs"][1:]
            assert pgo["outputs"][0][1] != stock["outputs"][0][1]
