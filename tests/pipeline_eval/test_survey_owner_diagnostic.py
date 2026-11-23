from hashlib import sha256
from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("survey_owner_diagnostic"), import_module("survey_owner_oracle")


def test_paid_join_and_owner_age_distinguish_missing_rows_labels_and_roles(modules):
    audit, _ = modules
    stock = dict(a=(17, "conditional"), b=(17, "predictive"), c=(25, "conditional"),
                 d=(42, "conditional"), e=(42, "predictive"))
    survey = dict(a=(17, "conditional"), b=(17, "conditional"), c=(27, "conditional"), f=(28, "predictive"))
    metadata = {oid: dict(time_s=i * 30., third=i // 2, rf_hz=10.5e9, channel=1, receiver=i % 2,
                          paid=oid != "d", verified=True) for i, oid in enumerate("abcdef")}
    got = audit.compare(stock, survey, metadata, ages={17: 5., 25: 12., 42: 6., 27: 7., 28: 8.})
    populations = got["populations"]
    assert {k: populations[k]["rows"] for k in ("stock", "unpaid_stock", "paid_stock", "survey", "common_stock",
                                                 "missing_paid_stock", "survey_only", "changed_norad", "changed_role",
                                                 "exact_common")} == dict(stock=5, unpaid_stock=1, paid_stock=4,
        survey=4, common_stock=3, missing_paid_stock=1, survey_only=1, changed_norad=1, changed_role=1, exact_common=1)
    assert populations["stock"]["orbit_age_hours"]["median"] == 6.
    assert populations["paid_stock"]["time_thirds"][1] == dict(rows=1, norads=1)
    metadata["f"]["paid"] = False
    with pytest.raises(ValueError, match="unpaid visit"):
        audit.compare(stock, survey, metadata, ages={})


def test_support_witness_checks_published_map_and_role_counts(modules):
    audit, _ = modules
    from leo.presentation.localization_v3 import owner_digest

    rows = dict(c0=[("p", 10, "conditional")], fitted_c=[("p", 10, "conditional")])
    expected = dict(associated=dict(c0=1, fitted_c=1), owners=dict.fromkeys(rows, owner_digest({"p": 10})))
    roles = {arm: dict(conditional=1) for arm in rows}
    assert audit.exact_owners(rows, expected, roles) == {arm: {"p": (10, "conditional")} for arm in rows}
    rows["fitted_c"] = [("p", 10, "predictive")]
    with pytest.raises(ValueError, match="fitted_c support"):
        audit.exact_owners(rows, expected, roles)


def test_original_receiver_and_counter_define_paid_observation_identity(modules):
    audit, _ = modules
    native = dict(source=dict(session_id="fixed", sample_rate_hz=100, probe_ms=20, probes=[
        dict(receiver_id=1, valid_start_counter=200, visit_index=7, channel=2, actual_rf_hz=12.e9,
             candidates=[dict(passed_fractional_margin_gate=True)]),
    ]), clock_anchor=dict(sample_counter=100), last_sample_counter=400, provenance=dict(window_count=8))
    metadata, duration, count = audit.native_rows(native, {7})
    oid = "sha256:" + sha256(b"fixed:1:200").hexdigest()
    assert (duration, count) == (3., 8)
    assert metadata[oid] == dict(time_s=1.01, visit=7, paid=True, channel=2, rf_hz=12.e9,
                                 receiver=1, third=1, verified=True)


def test_stock_oracle_only_keeps_membership_and_archived_discrete_alias(modules):
    _, oracle = modules
    ids = [str(i) for i in range(11)]
    times = [float(i * 5) for i in range(11)]
    original = dict(key="t", receiver=1, channel=1, rf_hz=10.5e9, observation_ids=ids, times=times,
                    values=[t * t * 10 for t in times], optimizer_seed=[1, 2],
                    pieces=[dict(start_s=0, end_s=50, degree=2, coefficients_hz=[4, 5])])
    paid = {oid: (123, "conditional") for oid in ids[1:10]}
    aliases = {oid: [123, 1] for oid in ids}
    members, labels, checks = oracle.restrict(dict(tracks=[original]), paid, aliases)
    assert members[0]["observation_ids"] == ids[1:10] and labels == [(123, "conditional", 1)]
    assert "optimizer_seed" not in members[0] and "coefficients_hz" not in members[0]["pieces"][0]
    assert not checks[0]["issues"]
    small = {oid: paid[oid] for oid in ids[2:5]}
    aliases.pop("3")
    _, _, rejected = oracle.restrict(dict(tracks=[original]), small, aliases)
    assert set(rejected[0]["issues"]) == {"insufficient_original_track_gate_points", "lost_contiguous_curvature",
                                          "missing_exact_stock_alias"}
