from copy import deepcopy
from hashlib import sha256
from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def study(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("held_cfo_fixed_residual")


def test_signed_edit_binds_capture_factor_and_unchanged_control(study):
    def probe(counter, cfo):
        return dict(receiver_id=1, valid_start_counter=counter, visit_index=counter,
                    candidates=[{"passed_fractional_margin_gate": True, study.HERTZ: cfo}])

    first = dict(clock_anchor={}, delivery_clocks=[], last_sample_counter=30,
                 source=dict(session_id="session", sample_rate_hz=10, probe_ms=20,
                             raw_recording_authority_digest="raw", input_manifest_sha256="input",
                             capture_start_utc_ns=0, capture_end_utc_ns=30,
                             probes=[probe(10, -45), probe(20, 21)]))
    second = deepcopy(first)
    second["source"]["probes"][0]["candidates"][0][study.HERTZ] = -48
    oid = "sha256:" + sha256(b"session:1:10").hexdigest()
    ledger = [dict(observation_id=oid, radio=1, counter=10, visit=10, original_hz=-45, updated_hz=-48)]

    delta, winners, controls = study.signed_edits(first, second, ledger)
    assert delta == {oid: -3}
    assert len(winners) == 2
    assert controls == 1

    tampered = deepcopy(second)
    tampered["source"]["probes"][1]["candidates"][0][study.HERTZ] = 0
    with pytest.raises(ValueError, match="Unedited control"):
        study.signed_edits(first, tampered, ledger)

    tampered = deepcopy(second)
    tampered["source"]["probes"][0]["candidates"][0]["arrival"] = 220
    with pytest.raises(ValueError, match="CFO-only"):
        study.signed_edits(first, tampered, ledger)


def test_identical_aggregate_rms_allows_both_signed_effects(study):
    interval = study.fixed_bound(1, 5, [2])["fixed_SSE_change_interval_hz2"]
    assert interval == [(2-5)**2 - 25, (2+5)**2 - 25]
    assert interval[0] < 0 < interval[1]
    no_edit = study.fixed_bound(7, 5, [])
    assert no_edit["fixed_RMS_interval_hz"] == [5, 5]
    assert no_edit["fixed_SSE_change_interval_hz2"] == [0, 0]


def test_owner_overlap_separates_identity_role_and_observation_support(study):
    a = {"same": (1, "predictive"), "drop": (1, "conditional"), "changed": (1, "conditional")}
    b = {"same": (1, "predictive"), "add": (2, "predictive"), "changed": (1, "predictive")}
    result = study.overlap(a, b, {"changed", "drop", "add"})
    assert result["common"] == 2
    assert result["common_same_norad_and_role"] == 1
    assert result["common_norad_changed"] == 0
    assert result["common_role_changed"] == 1
    assert result["edited_common"] == result["edited_added"] == result["edited_dropped"] == 1
