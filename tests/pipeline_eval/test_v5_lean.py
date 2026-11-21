import io
import json
import zipfile
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import v5_postfit
from tools.pipeline_eval.variants import v5_lean


def roof_case(**fields):
    return dict(
        id="DS26-example",
        panel="DS26",
        regions=[{"id": "roof", "center": [37.906, -122.545]}],
        **fields,
    )


def test_ds30_uses_existing_native_and_region_checks(tmp_path):
    case = roof_case()
    case["panel"] = "DS30"
    result = v5_lean.run(case, tmp_path / "worker")
    assert result["reason"] == "Native detector input is unavailable"
    case["regions"] = [{"center": [0.0, 0.0]}]
    assert "tile" in v5_lean.run(case, tmp_path / "worker")["reason"]


@pytest.mark.parametrize(
    "regions",
    [[], [{"center": [37.91, -122.545]}], [{"center": [37.906, -122.545], "width_km": 10}]],
)
def test_unsupported_prior_has_no_fix(tmp_path, regions):
    case = roof_case(native_path=str(tmp_path / "native.json"))
    case["regions"] = regions
    result = v5_lean.run(case, tmp_path / "worker")
    assert result["status"] == "unavailable"
    assert "tile" in result["reason"]
    assert result["arms"] == {"c0": {"latlon": None}, "fitted_c": {"latlon": None}}
    assert not (tmp_path / "worker").exists()


def test_derived_tracks_cannot_replace_detector_input(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text("{}")
    result = v5_lean.run(roof_case(graph_path=str(graph)), tmp_path / "worker")
    assert result["status"] == "unavailable"
    assert "detector input" in result["reason"]
    assert not (tmp_path / "worker").exists()


def test_worker_request_cannot_contain_truth(tmp_path):
    native = tmp_path / "native.json"
    native.write_text("{}")
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "job": {
                    "evaluation_reference": {"latitude_deg": 37.8, "longitude_deg": -122.5},
                    "native_input": {},
                }
            }
        )
    )
    result = v5_lean.run(
        roof_case(native_path=str(native), request_path=str(request)), tmp_path / "worker"
    )
    assert result["status"] == "unavailable"
    assert "reference" in result["reason"]
    assert not (tmp_path / "worker").exists()


def test_endpoint_output_keeps_both_calibration_arms_and_selected_score():
    region = SimpleNamespace(latlon=lambda x: (38.0 + x[1], -122.5 + x[0]))
    problem = SimpleNamespace(scan=SimpleNamespace(search_region=region))
    result = v5_lean._position_result(
        {
            "context": {"problems": {"c0": (problem, (0, 0)), "fitted_c": (problem, (0.01, 0.01))}},
            "native": {"observations": ["a", "b"], "tracks": ["track0"]},
            "arms": {
                "c0": {"endpoint_latlon": (38.0, -122.5), "negative_twice_elbo": 15, "RMS_hz": 55},
                "fitted_c": {"endpoint_latlon": (38.01, -122.49), "objective": 11, "rms_hz": 41},
            },
            "owners": {"c0": {"a": 1}, "fitted_c": {"a": 1, "b": 2}},
            "stage_timings": [{"stage": "final", "seconds": 0.1}],
        }
    )
    assert result["status"] == "ok"
    assert result["arms"] == {
        "c0": {"latlon": [38.0, -122.5]},
        "fitted_c": {"latlon": [38.01, -122.49]},
    }
    assert result["metrics"] == {
        "native_observations": 2,
        "tracks": 1,
        "c0_associated_observations": 1,
        "c0_frequency_score": 15.0,
        "c0_conditional_rms_hz": 55.0,
        "fitted_c_associated_observations": 2,
        "fitted_c_frequency_score": 11.0,
        "fitted_c_conditional_rms_hz": 41.0,
    }
    json.dumps(result, allow_nan=False)


def test_postfit_reads_scientific_axes_instead_of_plot_coordinates(tmp_path):
    def encode(value):
        return (
            ["map", [[key, encode(item)] for key, item in value.items()]]
            if isinstance(value, dict)
            else value
        )

    evidence = tmp_path / "evidence.zip"
    arms, digests = {}, {}
    with zipfile.ZipFile(evidence, "w") as archive:
        for arm, axes in {"c0": (1.0, 2.0), "fitted_c": (3.0, 4.0)}.items():
            buffer = io.BytesIO()
            np.save(buffer, np.array(axes), allow_pickle=False)
            raw = buffer.getvalue()
            digest = v5_postfit.sha256(raw)
            archive.writestr(digest.removeprefix("sha256:"), raw)
            digests[arm] = digest
            arms[arm] = {"x": ["array", digest]}
        tree = encode(
            {
                "presentation": {"arms": {"c0": {"endpoint_latlon": [0, 0]}}},
                "audit": {
                    "reassociation_complete": {
                        "status": "reassociation_evaluated",
                        "recovery": {"final": arms},
                    }
                },
            }
        )
        archive.writestr("values.json", json.dumps({"tree": tree}, separators=(",", ":")))
    expected_sha = v5_postfit.sha256(evidence.read_bytes())
    region = SimpleNamespace(latlon=lambda axes: (38.0 + axes[1], -122.0 + axes[0]))
    result, actual_digests = v5_postfit._project(evidence, expected_sha, region)
    assert result["arms"] == {
        "c0": {"latlon": [40.0, -121.0]},
        "fitted_c": {"latlon": [42.0, -119.0]},
    }
    assert actual_digests == digests
    with pytest.raises(ValueError, match="archive digest mismatch"):
        v5_postfit._project(evidence, "sha256:other", region)
