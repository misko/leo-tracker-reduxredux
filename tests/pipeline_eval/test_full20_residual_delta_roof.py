import json
from pathlib import Path

import pytest

from reports.ALGO08.v3 import full20_residual_delta_roof as audit


def test_support_counts_include_successfully_exported_residuals():
    support = audit.readout()["support"]
    assert support["scans"] == 92 and support["exported_rank1"] == 38
    assert support["covariance_rows"] == 1288 and support["unchanged_covariance_rows"] == 0
    assert support["fir_unchanged_counts"] == {200: 91, 228: 1}
    assert support["min_native_changed_fraction"] == pytest.approx(.961605)


def test_price_uses_every_original_lane_and_distinct_primary_clock():
    measured = audit.readout()
    deltas = measured["measured_native_delta_0049"]
    assert deltas["lane_counts"] == {"empty": 485, "primary_only": 186, "with_residual": 53}
    assert deltas["all"]["20-two_cpu_ns"] - deltas["all"]["20-primary_cpu_ns"] == 389_602_132
    model = measured["field_price"]
    assert model["issued_lanes_modeled"] == 300_522
    assert model["remaining_if_entire_primary_helper_free_ns_per_lane"] == pytest.approx(42_253.37)
    assert model["all_empty_free_preserve_positives_cpu_ns_per_lane"] > 2*model["conditional_all_native_cpu_ns_per_lane"]
    assert measured["exact_oracle"]["dense"]["exact_oracle_cpu_ms_mean"]*1e6 > model["conditional_all_native_cpu_ns_per_lane"]


def test_packaged_readout_recomputes_and_input_tampering_fails(tmp_path):
    path = audit.ALGO / "v3/measurements/full20-residual-delta-roof.json"
    sealed = json.loads(path.read_bytes())
    assert sealed.pop("native_calls") == sealed.pop("new_waveform_reads") == 0
    assert sealed.pop("verified_sources") == {str(path): pin for path, pin in audit.PROBES.items()}
    assert sealed == json.loads(json.dumps(audit.readout()))
    substituted = Path(tmp_path) / "source.json"
    substituted.write_text("{}")
    with pytest.raises(ValueError, match="Changed archived input"):
        audit.load(substituted, "0"*64)
