import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))

import ds7_historical_init_adapter as adapter  # noqa: E402


def write_source(tmp_path, index, latitude, longitude, tau, qualified=True):
    response = tmp_path / f"response-{index}.json"
    request = tmp_path / f"request-{index}.json"
    seal = tmp_path / f"seal-{index}.json"
    session_id = f"session-{index}"
    response.write_text(
        json.dumps(
            {
                "unit_id": f"single-{index:03}",
                "status": "ok",
                "converged": qualified,
                "boundary_hit": False,
                "estimate": {"latitude_deg": latitude, "longitude_deg": longitude},
                "diagnostics": {"timing_offsets_s": [tau]},
            }
        )
    )
    request.write_text(
        json.dumps(
            {
                "unit": {
                    "unit_id": f"single-{index:03}",
                    "session_ids": [session_id],
                }
            }
        )
    )

    def digest(path):
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    seal.write_text(
        json.dumps(
            {
                "schema": "ds7-run-seal/v1",
                "files": {response.name: digest(response), request.name: digest(request)},
            }
        )
    )
    return {
        "unit_id": f"single-{index:03}",
        "session_id": session_id,
        "response_path": str(response),
        "response_sha256": digest(response),
        "request_path": str(request),
        "request_sha256": digest(request),
        "seal_path": str(seal),
        "seal_sha256": digest(seal),
    }


def test_historical_starts_use_spherical_mean_and_independent_taus(tmp_path):
    bindings = [
        write_source(tmp_path, 1, 10.0, 20.0, -0.25),
        write_source(tmp_path, 2, 10.0, 20.0, 0.75),
    ]
    mean, center = adapter.load_initialization(
        {"single_fit_bindings": bindings, "geographic_prior_center_deg": [10.0, 20.0]},
        ["session-1", "session-2"],
    )
    np.testing.assert_allclose(mean, [0.0, 0.0, -0.25, 0.75], atol=1e-10)
    np.testing.assert_array_equal(center, [0.0, 0.0, -0.25, 0.75])


def test_unqualified_single_does_not_fabricate_timing_start(tmp_path):
    binding = write_source(tmp_path, 1, 10.0, 20.0, -0.25, qualified=False)
    with pytest.raises(ValueError, match="unqualified"):
        adapter.load_initialization(
            {"single_fit_bindings": [binding], "geographic_prior_center_deg": [10.0, 20.0]},
            ["session-1"],
        )


def test_single_session_order_mismatch_is_rejected(tmp_path):
    binding = write_source(tmp_path, 1, 10.0, 20.0, -0.25)
    with pytest.raises(ValueError, match="unqualified or duplicated"):
        adapter.load_initialization(
            {"single_fit_bindings": [binding], "geographic_prior_center_deg": [10.0, 20.0]},
            ["different-session"],
        )
