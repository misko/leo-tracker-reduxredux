import masked_cfo_next_two_replay as replay
import pytest


def test_panel_preserves_reopened_accession_and_requested_identity(tmp_path, monkeypatch):
    row = replay.cases()["DS30-0442"]
    case = row["case"]
    accession = row["manifest_raw_authority_sha256"]
    requested = row["catalogue_custody"]["historical_request_raw_authority_sha256"]
    assert accession != requested
    plan = dict(cases=[{"case":f"earlier-{i}"} for i in range(65)] + [row], smoke=[])
    pin = replay.saved.write(tmp_path/"plan.json", plan)
    monkeypatch.setattr(replay.held, "PLAN", pin)
    assert replay.enrolled(tmp_path, row)["manifest_raw_authority_sha256"] == requested
    assert replay.saved.document(tmp_path/"plan.json", pin)["cases"][-1]["manifest_raw_authority_sha256"] == accession
    with pytest.raises(ValueError, match="accession"):
        replay.enrolled(tmp_path, dict(row, manifest_raw_authority_sha256=requested))


def test_refusal_is_pair_bound_and_forbids_staging(tmp_path):
    row = replay.cases()["DS30-0442"]
    with pytest.raises(ValueError, match="refusal"):
        replay.refusal(row, {"pair_sha256":"sha256:wrong"})
    proof = replay.saved.document(replay.HERE/"measurements/0442-cache-custody.json", replay.REFUSAL_PIN)
    pair = "sha256:"+proof["field_receipts"]["pair_sha256"]
    decision = replay.refusal(row,{"pair_sha256":pair})
    assert decision["decision"] == "custody_refused"
    assert decision["accession_raw_sha256"] != decision["requested_raw_sha256"]
    with pytest.raises(ValueError, match="cannot stage"):
        replay.prepare(tmp_path/"unopened",row)
    assert not (tmp_path/"unopened").exists()


def test_reused_verifier_stops_at_survey_until_panel_release(tmp_path, monkeypatch):
    observed = []

    def geography(case):
        observed.append(case)
        raise AssertionError("The held survey was accessed before panel closure")

    def base(root, mode, pin, field_pair, ordinary):
        if mode == "ordinary":
            return "ordinary-parity"
        replay.saved.write(root/"verification-pins.json", {"ordinary":ordinary,"corrected":pin})
        replay.scoring.geography("DS30-0212")

    monkeypatch.setattr(replay.scoring, "geography", geography)
    monkeypatch.setattr(replay, "BASE_FINISH", base)
    assert replay.finish(tmp_path,"ordinary","plan","raw-pair",None) == "ordinary-parity"
    for mode in replay.capsule.CELLS:
        role = tmp_path/mode
        role.mkdir()
        (role/"worker-resource.txt").write_text("1.00 0.04 10000 0 0\n")
    pin = replay.finish(tmp_path,"corrected","plan","raw-pair",{"plan":"ordinary"})
    result = replay.saved.document(tmp_path/"pair-verified-before-survey.json",pin)
    assert result["closure_sha256"] == replay.saved.identifier(tmp_path/"verification-pins.json")
    assert result["field_pair"] == "raw-pair"
    assert observed == [] and not (tmp_path/"score.json").exists()


def test_field_authority_keeps_the_frozen_exact_request_and_requires_pair(tmp_path):
    base = tmp_path/"cases/DS30-0212"
    base.mkdir(parents=True)
    authority = dict(raw_authority_sha256="request",archive_sha256="archive",causal_cutoff_utc_ns=10)
    tag = lambda bare: "sha256:"+bare
    a = tag(replay.saved.write(base/"authority.json",authority))
    q = tag(replay.saved.write(base/"input.json",dict(authority=authority,authority_sha256=a)))
    p = tag(replay.saved.write(base/"pair.json",dict(authority_sha256=a)))
    row = dict(case="DS30-0212",catalogue_custody=dict(authority_sha256=a,request_sha256=q,
        historical_request_raw_authority_sha256="request",signed_archive_sha256="archive",signed_cutoff_ns=10))
    assert replay.field_authority(row,dict(verified_pair=True,pair_sha256=p),tmp_path) == authority
    with pytest.raises(ValueError,match="verified both"):
        replay.field_authority(row,dict(verified_pair=False,pair_sha256=p),tmp_path)
    with pytest.raises(ValueError,match="frozen request"):
        custody = dict(row["catalogue_custody"],historical_request_raw_authority_sha256="accession")
        replay.field_authority(dict(row,catalogue_custody=custody),dict(verified_pair=True,pair_sha256=p),tmp_path)
