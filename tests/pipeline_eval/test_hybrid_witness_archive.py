from hashlib import sha256
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import hybrid_witness_archive as audit


def test_pinned_evidence_supports_a_relocated_archive_and_explicit_external_root(tmp_path):
    reports, diagnostics = (tmp_path / name for name in ("relocated", "saved"))
    for directory in (reports, diagnostics):
        directory.mkdir()
    name = audit.relative_reports("/historic/checkout/reports/scan.json")
    data = b'{"capture": 1}'
    (diagnostics/name).write_bytes(data)
    (reports/name).symlink_to(diagnostics/name)
    pin = sha256(data).hexdigest()

    with pytest.raises(ValueError, match="declared evidence root"):
        audit.Archive(reports).read(name, pin)
    archive = audit.Archive(reports, external=(diagnostics,))
    with pytest.raises(ValueError, match="declared evidence root"):
        archive.read(name)
    with pytest.raises(ValueError, match="disagrees with its seal"):
        archive.read(name, "x")
    assert archive.read(name, pin) == {"capture": 1}
    assert archive.total == len(data)
    with pytest.raises(ValueError, match="byte cap"):
        audit.Archive(reports, limit=len(data)-1, external=(diagnostics,)).read(name, pin)


def test_enrolment_distinguishes_actual_trials_from_zero_trials_and_rejects_one_arm():
    cases = ["adopted", "held-tested", "held-empty", "pilot"]
    trial_cases = ["adopted", "held-tested"]
    arm_rows = [
        dict(case=case, policy=rule, arm=arm, accepted=case == "adopted", replacements=[])
        for case in cases for rule in ("equal_assignment_priors", "incumbent_sticky_prior")
        for arm in ("c0", "fitted_c")
    ]
    ledger = dict(rows=arm_rows, trials=[{"case": case} for case in trial_cases], evaluated_case_ids=cases)
    selection, _ = audit.enroll(ledger, {"pilot"})
    assert selection["positive"] == ["adopted"]
    assert selection["held"] == {
        "tested_alternatives": {"pool": 1, "cases": ["held-tested"]},
        "zero_trials": {"pool": 1, "cases": ["held-empty"]},
    }
    arm_rows[1]["accepted"] = False
    with pytest.raises(ValueError, match="matching calibration arms"):
        audit.enroll(ledger, {"pilot"})


def test_signed_qualified_existing_cold_adoption_does_not_predict_a_warm_skip():
    arms = {a: dict(gates={"tracks": [{"compatible": True}]}, linear_gates=[],
                    final_phase_change_s=0., endpoint_east_north_km=[1., 2.],
                    negative_twice_elbo=10., RMS_hz=2.) for a in ("c0", "fitted_c")}
    region = SimpleNamespace(half_width_km=12.5)
    signed = dict(selection={"qualified": True}, accepted=True, policy_arms=arms)
    assert audit.classify(None, signed, arms, region) == "qualified_warm_pair_unobserved"
    assert audit.classify("insufficient_family_witness", signed, arms, region) == "retains_competition"
    signed.update(selection={"qualified": False}, accepted=False)
    assert audit.classify(None, signed, arms, region) == "skips_competition_before_packet_evidence"
    signed["accepted"] = True
    with pytest.raises(ValueError, match="changed the original ordinary pair"):
        audit.classify(None, signed, arms, region)


def test_actual_adoption_requires_the_selected_paired_winner_and_original_mask():
    chosen = dict(paired_valid=True, replacements=[{"original_norad": 15, "norad": 18}],
                  arms={arm: {"endpoint_east_north_km": [2., 2.]} for arm in ("c0", "fitted_c")})
    original = {arm: {"endpoint_east_north_km": [1., 1.]} for arm in ("c0", "fitted_c")}
    position = dict(accepted=True, selected=chosen, policy_arms=chosen["arms"], baseline_arms=original,
                    original_mask=[True, False], selection_gain=40, search_penalty=20)
    value = audit.validate_stock(position, {"mask": [True, False]}, chosen)
    assert value["replacements"] == chosen["replacements"]
    position["policy_arms"] = original
    with pytest.raises(ValueError, match="actual adopted replacement"):
        audit.validate_stock(position, {"mask": [True, False]}, chosen)
