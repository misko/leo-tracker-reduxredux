from hashlib import sha256
from importlib import import_module
from pathlib import Path

import pytest


def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("local_future_policy"), import_module("local_future_inputs")


def packet(inputs, probes):
    return dict(source=dict(probes=probes, raw_recording_authority_digest="sha256:"+"5"*64,
                            session_id="session", sample_rate_hz=10_000_000, probe_ms=20),
                provenance=dict(detector_sha256="sha256:" + inputs.RECIPE_SHA),
                clock_anchor=dict(before=dict(realtime_ns=100, monotonic_ns=0),
                                  after=dict(realtime_ns=110, monotonic_ns=10), sample_counter=0),
                delivery_clocks=[], last_sample_counter=13_000_000)


def test_native_selected_once_then_reused_for_an_orbit_retry(monkeypatch, tmp_path):
    from tools.pipeline_eval.variants.carrier_continuation import Continuation

    policy, inputs = modules(monkeypatch)
    (tmp_path / "tracks.json").write_text("{}")
    monkeypatch.setattr(policy, "TRACKS_SHA256", sha256(b"{}").hexdigest())
    original, calls = Continuation.select, []

    def observe(self, row):
        calls.append(row["valid_start_counter"])
        return original(self, row)

    monkeypatch.setattr(Continuation, "select", observe)
    probes = [dict(receiver_id=0, channel=1, actual_rf_hz=11e9, valid_start_counter=i*2_000_000,
                   candidates=[dict(fractional_tracking_cfo_hz=10000+100*i, candidate_rank=0,
                                    fractional_margin=.5, integer_epoch_sample=0,
                                    fractional_epoch_offset_samples=.2, passed_fractional_margin_gate=True)])
              for i in range(7)]
    native = packet(inputs, probes)
    entry = policy.LocalFuturePolicy("raw")
    entry.bind(native, tmp_path)
    assert len(calls) == 14
    assert len(entry.future) == 3
    assert sum(bool(row["candidates"]) for row in entry.forward["source"]["probes"]) == 4
    assert entry.prepare(lambda n: n, native) is entry.prepare(lambda n: n, native)
    assert len(calls) == 14 and entry.prepare_calls == 2
    with pytest.raises(ValueError, match="already selected"):
        entry.bind(native, tmp_path)
    assert native["source"]["probes"] == probes and all(row["candidates"] for row in probes)


@pytest.mark.parametrize(("route", "details", "empty", "status"), [
    ("withheld_empty_receiver", None, True, "no_probes"),
    ("fallback", {"decision": "fallback"}, False, "forward_fallback"),
    ("complete", {"local_future_repair": {"decision": "rejected"}}, False, "rejected"),
])
def test_policy_binding_stays_separate_on_empty_and_fallback(monkeypatch, tmp_path, route, details, empty, status):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastScanStore

    policy, inputs = modules(monkeypatch)
    (tmp_path / "tracks.json").write_text("{}")
    monkeypatch.setattr(policy, "TRACKS_SHA256", sha256(b"{}").hexdigest())
    monkeypatch.setattr(FastScanStore, "automatic_workspace", lambda *args, **kwargs: tmp_path)
    native = packet(inputs, [])
    entry = policy.LocalFuturePolicy("saved")
    entry.bind(native, tmp_path)
    assert entry.future == [] and entry.prepare_calls == 0
    from aperture_trial import read, write

    terminal = dict(native_sha256=canonical_digest(native))
    write(tmp_path / "terminal.json", terminal)
    report = dict(receipt=dict(run_id="run", terminal_sha256=canonical_digest(terminal)),
                  route=route, route_details=details, solve={"empty_receiver_withhold": empty})
    policy_sha = entry.seal(tmp_path, report)
    seal = read(tmp_path / "local-future-policy.json")
    assert seal["status"] == status
    assert seal["original_receiver_sha256"] == native["provenance"]["detector_sha256"] != policy_sha
    assert seal["native_sha256"] == canonical_digest(native)
    assert seal["implementation"]["local_future_repair.py"] == sha256(
        Path(policy.__file__).with_name("local_future_repair.py").read_bytes()).hexdigest()


def test_launcher_defaults_and_explicit_repair_modes(monkeypatch):
    policy, _ = modules(monkeypatch)
    cli = import_module("full_short_run")
    invoked = []
    monkeypatch.setattr(cli, "run", lambda args, **kwargs: invoked.append(kwargs))
    monkeypatch.setattr(cli, "write", lambda *_: None)
    monkeypatch.setattr(policy.LocalFuturePolicy, "seal", lambda *_: "bound-policy")
    monkeypatch.setattr(cli, "MixedApertureDetector", lambda *args, **kwargs: type("Detector", (), {"detector": 0})())
    common = ["--recording", "capture", "--archive", "tle", "--region", "offer", "--output", "out"]
    saved = ["--saved", "immutable.json", "--saved-digest", "bound-native"]
    cli.main(common + saved)
    cli.main(common + saved + ["--local-future-repair"])
    cli.main(common + ["--local-future-repair", "--short-binary", "receiver.so"])
    assert invoked[0]["track_config"] is cli.graph_config and "local_future_policy" not in invoked[0]
    assert invoked[1]["track_config"] is None and invoked[1]["local_future_policy"].ingress == "saved"
    assert invoked[1]["saved_receiver"] == cli.RECIPE_SHA
    assert invoked[2]["local_future_policy"].ingress == "raw" and invoked[2]["saved_receiver"] is None
    with pytest.raises(SystemExit):
        cli.main(common + saved + ["--local-future-repair", "--causal-selection"])
    with pytest.raises(SystemExit):
        cli.main(common + saved + ["--local-future-repair", "--track-graph", "quadratic"])
