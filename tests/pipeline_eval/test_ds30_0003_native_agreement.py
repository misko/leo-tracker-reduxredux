import pytest

from reports.ALGO08.v3 import ds30_0003_native_agreement as audit
from reports.ALGO08.v3.ds30_0003_witness_attribution import observation_id, owner_support, plotted_opportunities, valid_owners


def test_metered_read_verifies_body_with_one_bounded_read(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "CASE", tmp_path)
    monkeypatch.setattr(audit, "NVME", tmp_path)
    original = audit.os.read
    calls = []

    def observe(fd, length):
        calls.append(length)
        return original(fd, length)

    monkeypatch.setattr(audit.os, "read", observe)
    body = b'{"signed":true}'
    path = tmp_path/"native.json"
    path.write_bytes(body)
    payload, evidence = audit.metered_read(path, len(body), audit.tag(body))
    assert payload == {"signed": True}
    assert evidence["byte_count"] == len(body) and calls == [len(body)]
    with pytest.raises(ValueError, match="pinned extent"):
        audit.metered_read(path, len(body)-1, audit.tag(body))
    assert calls == [len(body)]


def test_canonical_native_identity_binds_the_case_authority():
    provenance = dict(detector_sha256="sha256:detector")
    source = dict(sample_rate_hz=audit.RATE, session_id="session", input_manifest_sha256="inventory",
                  raw_recording_authority_digest="authority", probes=[])
    source["analysis_manifest_sha256"] = audit.canonical(["cancellation", "authority", "detector", []])
    result = dict(raw_identity=dict(session_id="session", inventory_sha256="inventory", raw_authority_sha256="authority"))
    audit.native_identity(dict(provenance=provenance, source=source), result)
    with pytest.raises(ValueError, match="original signed acquisition"):
        audit.native_identity(dict(provenance=provenance, source=source | {"probes": [1]}), result)


def test_final_owner_join_classifies_same_cfo_with_different_epoch_as_changed():
    native = {"installed": {"probes": []}, "successor": {"probes": []}}
    reports = {}
    for role in native:
        points = []
        for visit in (0, 1):
            for radio in (0, 1):
                start = 100+visit*100
                observed = radio == 0 or (role == "successor" and visit == 0)
                epoch = 1+5*(role == "successor" and visit == 1)
                peaks = [dict(fractional_tracking_cfo_hz=8., integer_epoch_sample=epoch,
                              fractional_epoch_offset_samples=.1, passed_fractional_margin_gate=True)] if observed else []
                native[role]["probes"].append(dict(receiver_id=radio, visit_index=visit, valid_start_counter=start,
                                                   edge="upper", actual_rf_hz=1e10, channel=1, candidates=peaks))
                if observed:
                    points.append(dict(visit=visit, receiver_id=radio, time_s=(start-100)/audit.RATE,
                                       cfo_hz=8., channel=1))
        native[role]["session_id"] = "session"
        reports[role] = plotted_opportunities(dict(points=points, session_id="session", time_basis="relative sample counter",
                                                   policy={"sample_rate_hz":audit.RATE}), 100)
    roster = [[observation_id("session", radio, start), 123, "conditional"] for radio,start in ((0,100),(1,100),(0,200))]
    pin = audit.canonical({row[0]:row[1] for row in roster})
    owners = valid_owners(dict(evidence=dict(owner_rows={"c0":roster})), {"c0":pin})
    assert owner_support({"source":native["installed"]}, {"source":native["successor"]}, reports, owners) == {
        "c0": {"unjoinable":0, "strata":{"anchor":{"matched_conditional":1, "added_conditional":1},
                                      "short":{"changed_conditional":1}}}
    }
