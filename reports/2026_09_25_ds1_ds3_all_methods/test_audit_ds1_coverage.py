from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def module():
    path = Path(__file__).with_name("audit_ds1_coverage.py")
    spec = importlib.util.spec_from_file_location("ds1_coverage_audit_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_audit_maps_only_exact_sealed_historical_method_rows():
    m = module()
    value = m.build()
    findings = {row["method_id"]: row for row in value["findings"]}
    assert value["counts"]["sealed_method_matched_evaluations"] == 10
    assert findings["global-time"]["selector"] == {"method": "global_time"}
    assert findings["i02-regularized-per-scan-time"]["selector"] == {"method": "per_scan_time"}
    assert findings["causal-per-norad-orbit-rate"]["summary"]["matching_row_count"] == 8
    assert findings["i03-global-time-plus-orbit-rate-screen"]["status"] == "still_unavailable"
