from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def module():
    path = Path(__file__).with_name("build_method_registry.py")
    spec = importlib.util.spec_from_file_location("method_registry_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_registry_covers_frozen_models_and_numbered_slots():
    m = module()
    value = m.build()
    rows = {row["method_id"]: row for row in value["methods"]}
    assert value["counts"] == {"method_arms": 49, "required_for_publication": 49}
    assert len(rows) == 49
    assert {row["iteration"] for row in rows.values() if row["iteration"] is not None} == set(
        range(1, 32)
    )
    for method_id in {
        "baseline-doppler",
        "global-time",
        "regularized-per-scan-time",
        "independent-per-track-time",
        "global-time-plus-per-norad-orbit-rate",
        "causal-per-norad-orbit-rate",
        "soft-association",
        "soft-association-plus-global-time",
        "fixed-hard-cone-orientation",
        "staged-full-fov-cone-sweep",
        "local-fitted-full-fov-cone-position",
        "i07-independent-gaussian-rerank",
        "i07-ar1-student-t-rerank",
    }:
        assert method_id in rows


def test_registry_separates_iteration_arms_and_supersession():
    m = module()
    rows = {row["method_id"]: row for row in m.build()["methods"]}
    assert rows["i02-shared-global-time"]["ds3_binding"]["estimate_label"] == (
        "shared_global_tau"
    )
    assert rows["i02-regularized-per-scan-time"]["ds3_binding"]["estimate_label"] == (
        "regularized_per_scan_tau"
    )
    assert rows["i15-information-weighted"]["superseded_by"] == "i19-rate-bound-audit"
    assert rows["i26-quartic-rate-marginal"]["classification"] == "nonportable"
    assert rows["i30-fixed-topk-soft-preflight"]["method_id"] != (
        rows["soft-association"]["method_id"]
    )
    assert rows["global-time"]["ds3_binding"]["artifact"]["path"].endswith(
        "exact-method-arms/global_time.json"
    )
    assert rows["i12-expanded-exact-rate-only"]["ds3_binding"]["terminal_status"] == (
        "unqualified_boundary"
    )
    assert rows["i12-shared-norad-rate"]["ds3_binding"]["terminal_status"] == (
        "no_position_diagnostic"
    )


def test_registry_binds_only_exact_sealed_ds1_historical_method_evidence():
    m = module()
    rows = {row["method_id"]: row for row in m.build()["methods"]}
    expected = {
        "baseline-doppler": "baseline",
        "global-time": "global_time",
        "regularized-per-scan-time": "per_scan_time",
        "i02-shared-global-time": "global_time",
        "i02-regularized-per-scan-time": "per_scan_time",
        "independent-per-track-time": "independent_per_track_time",
        "causal-per-norad-orbit-rate": "causal_per_norad_orbit_rate",
        "global-time-plus-per-norad-orbit-rate": "global_time_plus_per_norad_orbit_rate",
        "soft-association": "soft_association",
        "soft-association-plus-global-time": "soft_association_plus_global_time",
    }
    for method_id, selector in expected.items():
        evidence = rows[method_id]["ds1"]["historical_evidence"]
        assert evidence["kind"] == "sealed_method_rows"
        assert evidence["selector"] == {"method": selector}
        assert evidence["artifact"]["sha256"].startswith("sha256:")
    assert "historical_evidence" not in rows["i03-global-time-plus-orbit-rate-screen"]["ds1"]
