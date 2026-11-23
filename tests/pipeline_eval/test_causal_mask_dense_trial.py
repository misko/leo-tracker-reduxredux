from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(HERE))

from causal_mask_dense_trial import BUY_SHA, purchase_list, restore


def test_exact_sealed_causal_plan_is_reproducible():
    from leo.contracts.digests import canonical_digest

    bought = purchase_list()
    assert len(bought) == len(set(bought)) == 1625
    assert canonical_digest(bought) == "sha256:" + BUY_SHA


def test_restore_changes_only_one_independent_original_short_measurement():
    rows = [dict(visit_index=n, receiver_id=r, valid_start_counter=n*10_000_000,
                 edge="upper", channel=1, actual_rf_hz=11_000_000_000,
                 candidates=[{"fractional_tracking_cfo_hz": -2000+10*n+r}]) for n in range(5) for r in (0, 1)]
    common = dict(schema_version=1, clock_anchor={}, delivery_clocks=[], last_sample_counter=40_000_000)
    source = dict(session_id="fixture", input_manifest_sha256="inventory", raw_recording_authority_digest="authority",
                  sample_rate_hz=10_000_000, probe_ms=20, radio_id="dual", stream_generation=0, capture_mode="fixture")
    provenance = dict(excluded_windows=[], detector_sha256="sha256:"+"a"*64)
    full = dict(common, source=dict(source, probes=rows), provenance=provenance)
    base_rows = [dict(p, candidates=[]) if i in (5, 6, 9) else p for i, p in enumerate(rows)]
    base = dict(common, source=dict(source, probes=base_rows), provenance=dict(provenance, detector_sha256="sha256:"+"b"*64))
    target, audit = restore(full, base, [(2, 1)])
    assert audit["purchased_short_lanes"] == 1
    assert audit["positive_buys"] == 1
    assert audit["paid_factors"] == 8
    assert target["source"]["probes"] == [p if i not in (6, 9) else base_rows[i] for i, p in enumerate(rows)]
    with pytest.raises(ValueError, match="only buy an originally omitted"):
        restore(full, base, [(0, 1)])
