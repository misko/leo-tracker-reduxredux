import json
import hashlib
from types import SimpleNamespace

import pytest

from tools.pipeline_eval.qualification import paired_publication as bench


def test_source_pins_bind_the_measured_launcher_to_the_reviewed_variant(tmp_path):
    runner = tmp_path/"run"
    variant = tmp_path/"solver.py"
    runner.write_bytes(b"run solver")
    variant.write_bytes(b"original")
    pins = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (runner, variant)}
    bench.verify_sources(runner, pins)
    variant.write_bytes(b"changed after freezing")
    with pytest.raises(ValueError, match="source changed"):
        bench.verify_sources(runner, pins)


@pytest.mark.parametrize("mismatch", [False, True])
def test_pair_uses_empty_outputs_and_only_credits_same_recording(tmp_path, monkeypatch, mismatch):
    args = SimpleNamespace(cpu=2, first="candidate", recording=tmp_path/"recording",
                           region=tmp_path/"region", output=tmp_path/"results",
                           baseline="baseline", candidate="candidate", candidate_config=None, blind_panel=None)
    calls = []

    def measure(launcher, root, _args, specification):
        assert not root.exists()
        assert specification is None
        root.mkdir()
        calls.append(launcher)
        return dict(elapsed_s=4 if launcher=="baseline" else 2,
                    raw_authority=launcher if mismatch else "same",
                    receipt=dict(session_id="s", region={"width_km":25}, window_count=4))

    monkeypatch.setattr(bench, "measure", measure)
    monkeypatch.setattr(bench, "LOCK", tmp_path/"test.lock")
    monkeypatch.setattr(bench.os, "sched_getaffinity", lambda _: {2})
    monkeypatch.setattr(bench.os, "sched_setaffinity", lambda *args: None)
    monkeypatch.setattr(bench.os, "setpriority", lambda *args: None)
    monkeypatch.setattr(bench.subprocess, "run", lambda *args, **kwargs: None)
    if mismatch:
        with pytest.raises(ValueError, match="different waveform"):
            bench.run_pair(args)
    else:
        bench.run_pair(args)
    report=json.loads((args.output/"pair.json").read_bytes())
    assert calls == ["candidate", "baseline"]
    if mismatch:
        assert "failure" in report and "elapsed_ratio" not in report
    else:
        assert report["elapsed_ratio"] == 0.5
    with pytest.raises(FileExistsError):
        bench.run_pair(args)


def test_verified_withholding_counts_as_a_terminal_publication(tmp_path):
    scans=bench.FastScanStore(tmp_path)
    publications=bench.FastStandardAnalysisStore(tmp_path)
    rid="algo08-v2-trial"
    region=dict(center=[-32.0,95.0], width_km=25.0, screen_center=[-32.0,95.0])
    arms={a: {"latlon":None} for a in ("c0","fitted_c")}
    terminal=dict(reason="no probes", arms=arms)
    digest=bench.canonical_digest(terminal)
    bench.immutable_json(scans.automatic_workspace(rid)/"terminal.json",terminal)
    scans.publish(rid,dict(session_id="s", points=[]))
    publications.withhold(rid,terminal["reason"],terminal_sha256=digest,region=region,raw_authority="raw")
    receipt=dict(run_id=rid,session_id="s",region=region,decision="withheld",terminal_sha256=digest)
    result=bench.evidence(tmp_path,receipt,0)
    assert result["arms"]==arms and result["reason"]=="no probes" and result["artifacts"]==[]


def test_blind_pair_needs_a_separate_scorer_and_frozen_recording_offer_assignment(tmp_path, monkeypatch):
    public = tmp_path/"public"
    public.mkdir()
    (tmp_path/"scorer").mkdir()
    recording, region, archive = public/"aa", public/"bb.json", public/"tle"
    recording.mkdir()
    region.touch()
    archive.mkdir()
    panel = public/"panel.json"
    monkeypatch.setattr(bench, "ShortWindowReader", lambda _: SimpleNamespace(manifest_sha256="raw digest"))
    inputs = {"offers": {"bb": hashlib.sha256(region.read_bytes()).hexdigest()},
              "recordings": {"aa": "raw digest"}, "tle_objects": []}
    panel.write_text(json.dumps({"commitment": "a"*64, "jobs": [{"recording": "aa", "offer": "bb"}],
                                 "inputs": inputs}))
    digest = hashlib.sha256(panel.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="scorer directory access"):
        bench.blind_assignment(panel, digest, recording, region, archive)
    monkeypatch.setattr(bench.os, "access", lambda path, mode: False)
    assert bench.blind_assignment(panel, digest, recording, region, archive)["job"] == {"recording": "aa", "offer": "bb"}
    with pytest.raises(ValueError, match="manifest changed"):
        bench.blind_assignment(panel, "0"*64, recording, region, archive)
    unassigned = public/"cc.json"
    unassigned.touch()
    with pytest.raises(ValueError, match="frozen blind panel"):
        bench.blind_assignment(panel, digest, recording, unassigned, archive)
    region.write_bytes(b"moved offer")
    with pytest.raises(ValueError, match="inventory changed"):
        bench.blind_assignment(panel, digest, recording, region, archive)


def test_comparison_rejects_a_grid_published_in_another_site_frame(tmp_path, monkeypatch):
    run = "algo08-v2-trial"
    region = dict(center=[-32., 95.], width_km=25., screen_center=[-32., 95.])
    terminal = {"arms": {}}
    receipt = dict(run_id=run, session_id="s", region=region, decision="complete",
                   terminal_sha256=bench.canonical_digest(terminal))
    scans = bench.FastScanStore(tmp_path)
    bench.immutable_json(scans.automatic_workspace(run)/"terminal.json", terminal)
    scans.publish(run, dict(session_id="s", points=[]))
    detail = dict(terminal_sha256=receipt["terminal_sha256"], state="complete", region=region,
                  raw_authority="raw", arms={}, artifacts=[{"name": n, "sha256": n} for n in bench.PLOTS])
    path = dict(region_center=region["center"], box_width_km=25., binding={"build": "A"})
    grid = dict(path, elapsed_seconds=1)
    store = SimpleNamespace(detail=lambda _: detail, position_path=lambda _: path,
                            position_grid=lambda _: grid, artifact=lambda *args: b"")
    monkeypatch.setattr(bench, "FastStandardAnalysisStore", lambda _: store)
    evidence = bench.evidence(tmp_path, receipt, 0)
    grid.update(elapsed_seconds=3, binding={"build": "B"})
    assert bench.evidence(tmp_path, receipt, 0)["scientific_digests"] == evidence["scientific_digests"]
    grid["region_center"] = [36., -122.]
    with pytest.raises(ValueError, match="different search region"):
        bench.evidence(tmp_path, receipt, 0)


def test_experimental_entry_passes_each_offer_without_a_station_reference(tmp_path, monkeypatch):
    from tools.pipeline_eval.qualification import experimental_publication as trial
    offers = []

    def analyze(recording, root, assets, archive, offer):
        offers.append(offer.document())
        assert trial.algo08_scan.PINS["cancellation-factors.so"] == "c"*64
        return {"decision":"withheld"}

    monkeypatch.setattr(trial.algo08_scan, "analyze", analyze)
    root=tmp_path/"output"
    root.mkdir()
    detector=tmp_path/"receiver.so"
    detector.touch()
    spec={"solver":"stock", "detector":str(detector), "detector_sha256":"c"*64}
    args=SimpleNamespace(recording=tmp_path/"opaque", bulk_root=root,
                         archive=tmp_path/"tle", region=tmp_path/"offer.json")
    pin=trial.algo08_scan.PINS["cancellation-factors.so"]
    for center in ([46,13],[-28,116]):
        args.region.write_text(json.dumps({"center":center,"width_km":30}))
        trial.run(args,spec)
    assert [item["screen_center"] for item in offers]==[[46,13],[-28,116]]
    assert trial.algo08_scan.PINS["cancellation-factors.so"]==pin
    (root/"prior-result").touch()
    with pytest.raises(ValueError, match="empty output root"):
        trial.run(args,spec)
