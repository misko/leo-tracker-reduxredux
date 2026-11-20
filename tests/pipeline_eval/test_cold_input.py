import json
from dataclasses import fields
from hashlib import sha256

import pytest

from tools.pipeline_eval.qualification import cold_input


def test_cold_receiver_gets_measurements_and_causal_tle_only(tmp_path, monkeypatch):
    monkeypatch.delenv("PIPELINE_EVAL_BULK_ROOT", raising=False)

    def locator(name, data):
        (tmp_path / name).write_bytes(data)
        return dict(path=name, sha256=sha256(data).hexdigest())

    candidate = {k: 0 for k in cold_input.CANDIDATE_FIELDS}
    candidate["private_association"] = "hidden"
    probe = {k: 0 for k in cold_input.PROBE_FIELDS}
    probe.update(candidates=[candidate], known_location=[1, 2])
    doc = dict(
        source=dict(
            qualified=True, session_id="s", probes=[probe], sample_rate_hz=100, probe_ms=20
        ),
        clock_anchor=dict(
            before=dict(realtime_ns=20), after=dict(realtime_ns=24), sample_counter=300
        ),
        last_sample_counter=500,
    )
    case = dict(
        id="example",
        native=locator("native", json.dumps(doc).encode()),
        catalog=locator("tle", b"catalogue"),
        session_id="s",
        catalog_timestamp_ns=19,
        cutoff_utc_ns=20,
        regions=[{"center": [1, 2]}],
        request={"path": "never-read"},
        observation="never-read",
    )
    monkeypatch.setattr(cold_input, "_load_case", lambda key: case)
    monkeypatch.setattr(cold_input, "BULK", tmp_path)
    capture = cold_input.load("example")
    assert (capture.duration_s, capture.anchor_utc_ns, capture.cutoff_utc_ns) == (2, 22, 20)
    assert capture.catalog == b"catalogue"
    assert not {"regions", "tracks", "truth", "request"} & {f.name for f in fields(capture)}
    assert "known_location" not in capture.probes[0]
    assert "private_association" not in capture.probes[0]["candidates"][0]
    assert cold_input.matched_offers("example") == case["regions"]
    monkeypatch.setenv("PIPELINE_EVAL_BULK_ROOT", str(tmp_path))
    monkeypatch.setattr(cold_input, "BULK", tmp_path / "absent")
    assert cold_input.load("example") == capture
    case["catalog_timestamp_ns"] = 21
    with pytest.raises(ValueError, match="future catalogue"):
        cold_input.load("example")
    case["catalog_timestamp_ns"] = 19
    (tmp_path / "tle").write_bytes(b"changed")
    with pytest.raises(ValueError, match="frozen digest"):
        cold_input.load("example")


def test_legacy_track_input_alone_is_unavailable_to_the_cold_receiver(monkeypatch):
    monkeypatch.setattr(
        cold_input,
        "_load_case",
        lambda _: dict(id="transfer", observation="legacy-track", catalog="archived-tle"),
    )
    with pytest.raises(FileNotFoundError, match="frozen GLRT candidate probes"):
        cold_input.load("transfer")
