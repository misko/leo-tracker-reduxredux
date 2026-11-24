from hashlib import sha256
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import named_0016_translated as trial


def test_named_packet_keeps_authority_cutoff_and_complete_opportunity_count(monkeypatch):
    calls = []
    monkeypatch.setattr(trial, "bind_native", lambda *args, **kwargs: calls.append((args[1:], kwargs)))
    binding = {"admission": dict(stock={"detector_sha256": "named-detector"}, session="session",
                                 inventory="manifest", raw_authority="raw", cutoff_utc_ns=100)}
    probes = [dict(candidates=[{}])] * 440 + [dict(candidates=[])] * (1426-440)
    native = dict(source=dict(raw_recording_authority_digest="raw", probes=probes),
                  provenance=dict(window_count=808, processed_windows=713),
                  clock_anchor={"before": {"realtime_ns": 100}})
    trial.validate_packet(native, binding)
    assert calls == [(('session', 'manifest', 'named-detector'), {'expected': trial.NATIVE})]
    with pytest.raises(ValueError, match="capture identity or scope"):
        trial.validate_packet(dict(native, source=dict(native["source"], probes=probes[:-1])), binding)
    with pytest.raises(ValueError, match="capture identity or scope"):
        trial.validate_packet(dict(native, clock_anchor={"before": {"realtime_ns": 99}}), binding)


def test_causal_archive_checks_cutoff_and_actual_body(tmp_path, monkeypatch):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    snapshot = tmp_path / "snapshot"
    snapshot.write_bytes(b"prior orbital bulletin")
    digest = sha256(snapshot.read_bytes()).hexdigest()
    ref = SimpleNamespace(path=snapshot, collected_utc_ns=20, sha256=digest)
    monkeypatch.setattr(TleArchiveReader, "list_snapshots", lambda self, provider: (ref,))
    admission = dict(cutoff_utc_ns=21, archive=dict(snapshots=1, sha256=canonical_digest({snapshot.name: digest})))
    assert trial.check_archive(tmp_path, admission)["latest_ns"] == 20
    with pytest.raises(ValueError, match="original 46 available causal"):
        trial.check_archive(tmp_path, dict(admission, cutoff_utc_ns=20))
    snapshot.write_bytes(b"modified orbital bulletin")
    with pytest.raises(ValueError, match="differs from its archived name and digest"):
        trial.check_archive(tmp_path, admission)
