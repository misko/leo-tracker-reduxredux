import pytest

from reports.ALGO08.v3 import ds30_0003_native_agreement as audit


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
