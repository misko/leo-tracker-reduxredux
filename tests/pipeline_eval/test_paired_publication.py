import json
import hashlib
import errno
import fcntl
import os
from types import SimpleNamespace

import pytest

from tools.pipeline_eval.qualification import paired_publication as bench
from tests.fast_scan_support import recording as synthetic_recording


@pytest.mark.parametrize("changed", [{"center": [37., -122.]}, {"screen_center": [37., -122.]}, {"width_km": 25}])
def test_each_timed_launcher_must_return_its_actual_assigned_region(tmp_path, monkeypatch, changed):
    args = SimpleNamespace(region=tmp_path/"offer.json", recording=tmp_path/"r", archive=tmp_path/"tle", timeout=5)
    args.region.write_text(json.dumps({"center": [-31., 129.], "width_km": 30}))
    region = {"center": [-31., 129.], "width_km": 30, "screen_center": [-31., 129.]}
    result = SimpleNamespace(returncode=0, stdout=json.dumps({"region": region | changed}))
    monkeypatch.setattr(bench.subprocess, "run", lambda *a, **kw: result)
    with pytest.raises(ValueError, match="assigned offer"):
        bench.measure(tmp_path/"launcher", tmp_path/"output", args)


def test_opt_in_pid_diagnostics_are_saved_with_unchanged_cpu_and_wall_markers(tmp_path, monkeypatch):
    args = SimpleNamespace(region=tmp_path / "offer.json", recording=tmp_path / "r",
                           archive=tmp_path / "tle", timeout=5, observe_scheduler=True)
    region = {"center": [-31., 129.], "width_km": 25., "screen_center": [-31., 129.]}
    args.region.write_text(json.dumps(region))
    elapsed = iter((10.0, 12.0))
    cpu = iter((3.0, 4.0))
    events = []

    def observed(command, *, env, timeout, started):
        assert started == 10.0 and timeout == 5
        assert events == ["prelaunch"]
        return SimpleNamespace(returncode=0, stdout="noise\n" + json.dumps({"region": region})), {"pid": 123}

    monkeypatch.setattr(bench.time, "monotonic", lambda: next(elapsed))
    monkeypatch.setattr(bench, "child_usage", lambda: {"cpu_s": next(cpu)})
    monkeypatch.setattr(bench.launcher_observation, "run", observed)
    monkeypatch.setattr(bench, "evidence", lambda *a: {"raw_authority": "sample"})
    row = bench.measure(tmp_path / "run", tmp_path / "output", args,
                        before_launch=lambda: events.append("prelaunch"))
    assert row["elapsed_s"] == 2.0 and row["cpu_s"] == 1.0
    assert row["scheduler_observation"] == {"pid": 123}


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


def test_named_v3_binds_verified_launcher_and_publication_marker(tmp_path, monkeypatch):
    launcher = tmp_path / "run"
    launcher.write_bytes(b"fixture")
    monkeypatch.setattr(bench, "V3_LAUNCHER_SHA", hashlib.sha256(b"fixture").hexdigest())
    monkeypatch.setattr(bench.subprocess, "check_output", lambda *a, **kw: json.dumps(bench.V3_IDENTITY))
    assert bench.verified_v3(launcher) == bench.V3_IDENTITY
    receipt = dict(session_id="recording", decision="withheld")
    (tmp_path / "algo08v3-release.json").write_text(json.dumps(bench.V3_IDENTITY | receipt))
    bench.verify_v3_publication(tmp_path, receipt)
    with pytest.raises(ValueError, match="Publication"):
        bench.verify_v3_publication(tmp_path, dict(receipt, decision="complete"))
    monkeypatch.setattr(bench.subprocess, "check_output", lambda *a, **kw: "{}")
    with pytest.raises(ValueError, match="payload changed"):
        bench.verified_v3(launcher)
    launcher.write_bytes(b"other")
    with pytest.raises(ValueError, match="launcher changed"):
        bench.verified_v3(launcher)


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
    assert "cache_observation" not in report
    if mismatch:
        assert "failure" in report and "elapsed_ratio" not in report
    else:
        assert report["elapsed_ratio"] == 0.5
    with pytest.raises(FileExistsError):
        bench.run_pair(args)


@pytest.mark.parametrize("tamper", [False, True])
def test_cache_snapshot_is_bound_and_precedes_both_clocks_under_the_lock(tmp_path, monkeypatch, tamper):
    recording = synthetic_recording(tmp_path / "raw")
    manifest = recording / "manifest.json"
    region_file = tmp_path / "offer.json"
    region = dict(center=[-31., 129.], width_km=25., screen_center=[-31., 129.])
    region_file.write_text(json.dumps(region))
    library = tmp_path / "helper.so"
    library.touch()
    lock = tmp_path / "gauss.lock"
    args = SimpleNamespace(
        cpu=2, output=tmp_path / "out", recording=recording, region=region_file,
        archive=tmp_path, first="candidate", baseline=tmp_path / "stock",
        candidate=tmp_path / "candidate", candidate_config=None, blind_panel=None, timeout=5,
        cache_library=library,
        cache_manifests=((manifest, "sha256:" + hashlib.sha256(manifest.read_bytes()).hexdigest()),),
    )
    events = []

    def query(fd, length):
        assert os.fstat(fd).st_size == length
        assert os.lseek(fd, 0, os.SEEK_CUR) == 0
        with lock.open("rb") as other:
            with pytest.raises(BlockingIOError):
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        first = events.count("timed launch") == 0
        events.append("cache")
        code = errno.ENOSYS if first else errno.EPERM
        raise OSError(code, os.strerror(code))

    def execute(command, **kwargs):
        if command[0] == "ionice":
            return None
        events.append("timed launch")
        if tamper:
            data = json.loads(manifest.read_bytes())
            data["stop_reason"] = "changed before the second arm"
            manifest.write_text(json.dumps(data))
        return SimpleNamespace(returncode=0, stdout=json.dumps(dict(region=region)))

    def clock_start():
        events.append("stage clock")
        return 0

    def cpu_clock():
        events.append("child counters")
        return {"cpu_s": 1.0}

    def wall_clock():
        events.append("elapsed clock")
        return float(len(events))

    monkeypatch.setattr(bench, "LOCK", lock)
    monkeypatch.setattr(bench.os, "sched_getaffinity", lambda _: {2})
    monkeypatch.setattr(bench.os, "sched_setaffinity", lambda *args: None)
    monkeypatch.setattr(bench.os, "setpriority", lambda *args: None)
    monkeypatch.setattr(bench.subprocess, "run", execute)
    monkeypatch.setattr(bench.time, "time_ns", clock_start)
    monkeypatch.setattr(bench.time, "monotonic", wall_clock)
    monkeypatch.setattr(bench, "child_usage", cpu_clock)
    monkeypatch.setattr(bench.cache_residency, "load_query", lambda _: query)
    monkeypatch.setattr(bench, "evidence", lambda *args: dict(
        raw_authority="scope", receipt=dict(region=region, session_id="session", window_count=3),
    ))

    if tamper:
        with pytest.raises(ValueError, match="assigned sealed manifests"):
            bench.run_pair(args)
    else:
        bench.run_pair(args)
    arm_events = ["cache", "stage clock", "child counters", "elapsed clock",
                  "timed launch", "elapsed clock", "child counters"]
    assert events == arm_events * (1 if tamper else 2)
    result = json.loads((args.output / "pair.json").read_bytes())
    observations = result["cache_observation"]
    assert observations["manifests"] == bench.cache_residency.manifest_pins(args.cache_manifests)
    assert observations["arms"]["candidate"]["unavailable"] == {"ENOSYS": 1}
    assert observations["arms"]["candidate"]["cached_pages"] is None
    if tamper:
        assert set(result["runs"]) == {"candidate"}
        assert "baseline" not in observations["arms"]
    else:
        assert observations["arms"]["baseline"]["unavailable"] == {"EPERM": 1}


@pytest.mark.parametrize("wrong_screen", [False, True])
def test_verified_withholding_binds_the_terminal_region(tmp_path, wrong_screen):
    scans=bench.FastScanStore(tmp_path)
    publications=bench.FastStandardAnalysisStore(tmp_path)
    rid="algo08-v2-trial"
    region=dict(center=[-32.0,95.0], width_km=25.0, screen_center=[-32.0,95.0])
    arms={a: {"latlon":None} for a in ("c0","fitted_c")}
    terminal_region = dict(region, screen_center=[37.5, -122.]) if wrong_screen else region
    terminal=dict(reason="no probes", arms=arms, region=terminal_region)
    digest=bench.canonical_digest(terminal)
    bench.immutable_json(scans.automatic_workspace(rid)/"terminal.json",terminal)
    scans.publish(rid,dict(session_id="s", points=[]))
    publications.withhold(rid,terminal["reason"],terminal_sha256=digest,region=region,raw_authority="raw")
    receipt=dict(run_id=rid,session_id="s",region=region,decision="withheld",terminal_sha256=digest)
    if wrong_screen:
        with pytest.raises(ValueError, match="Terminal region differs"):
            bench.evidence(tmp_path, receipt, 0)
    else:
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
    terminal = {"arms": {}, "region": region}
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
    from tools import algo08_scan
    from tools.pipeline_eval.qualification import experimental_publication as trial
    offers = []

    def analyze(recording, root, assets, archive, offer):
        offers.append(offer.document())
        assert algo08_scan.PINS["cancellation-factors.so"] == "c"*64
        return {"decision":"withheld"}

    monkeypatch.setattr(algo08_scan, "analyze", analyze)
    root=tmp_path/"output"
    root.mkdir()
    detector=tmp_path/"receiver.so"
    detector.touch()
    spec={"solver":"stock", "detector":str(detector), "detector_sha256":"c"*64}
    args=SimpleNamespace(recording=tmp_path/"opaque", bulk_root=root,
                         archive=tmp_path/"tle", region=tmp_path/"offer.json")
    pin=algo08_scan.PINS["cancellation-factors.so"]
    for center in ([46,13],[-28,116]):
        args.region.write_text(json.dumps({"center":center,"width_km":30}))
        trial.run(args,spec)
    assert [item["screen_center"] for item in offers]==[[46,13],[-28,116]]
    assert algo08_scan.PINS["cancellation-factors.so"]==pin
    (root/"prior-result").touch()
    with pytest.raises(ValueError, match="empty output root"):
        trial.run(args,spec)


@pytest.mark.parametrize("rendering", ["individual", "raster-layout"])
def test_experimental_entry_scopes_the_selected_publication_renderer(tmp_path, monkeypatch, rendering):
    from tools import algo08_scan
    from tools.pipeline_eval.qualification import experimental_publication as trial
    from tools.pipeline_eval.variants.experimental import raster_layout

    stock = algo08_scan.render
    packet = {"selected_model": "fixture"}
    expected = {"position": b"layout"}

    def candidate(science, *, title):
        assert science is packet
        assert title == "opaque"
        return expected

    def analyze(recording, root, assets, archive, offer):
        if rendering == "raster-layout":
            return algo08_scan.render(packet, title=recording.name)
        assert algo08_scan.render is stock
        return expected

    monkeypatch.setattr(raster_layout, "render_layout", candidate)
    monkeypatch.setattr(algo08_scan, "analyze", analyze)
    output = tmp_path / "output"
    output.mkdir()
    detector = tmp_path / "receiver.so"
    detector.touch()
    region = tmp_path / "offer.json"
    region.write_text(json.dumps({"center": [-33, 113], "width_km": 35}))
    args = SimpleNamespace(recording=tmp_path / "opaque", bulk_root=output,
                           archive=tmp_path / "tle", region=region)
    spec = dict(solver="stock", rendering=rendering, detector=str(detector), detector_sha256="c" * 64)
    assert trial.run(args, spec) == expected
    assert algo08_scan.render is stock


@pytest.mark.parametrize("supported", [True, False])
@pytest.mark.parametrize("endpoint_reuse", [False, True])
def test_experimental_entry_paired_ingress_uses_reviewed_bytes_and_stock_fallback(
    tmp_path, monkeypatch, supported, endpoint_reuse,
):
    from leo.storage.short_window import ShortWindowReader
    from tools import algo08_scan
    from tools.pipeline_eval.qualification import experimental_publication as trial
    from tools.pipeline_eval.variants import v5_direct_cavity
    from tools.pipeline_eval.variants.experimental import paired_sha256
    from leo.analysis.localization_v3 import conservative_recovery

    stock = ShortWindowReader.windows
    optimizer = v5_direct_cavity.bounded_secant
    recover = conservative_recovery.conservative_recovery
    def acquire():
        assert (ShortWindowReader.windows is not stock) == supported
        return {"decision": "withheld"}

    def analyze(*args):
        assert ShortWindowReader.windows is stock
        assert (v5_direct_cavity.bounded_secant is not optimizer) == endpoint_reuse
        assert (conservative_recovery.conservative_recovery is not recover) == endpoint_reuse
        result = algo08_scan.acquire()
        assert ShortWindowReader.windows is stock
        return result

    def load(path):
        assert path != library and path.read_bytes() == library.read_bytes()
        return object() if supported else None

    monkeypatch.setattr(algo08_scan, "analyze", analyze)
    monkeypatch.setattr(algo08_scan, "acquire", acquire)
    monkeypatch.setattr(paired_sha256, "_library", load)
    output = tmp_path / "output"
    output.mkdir()
    detector = tmp_path / "receiver.so"
    detector.touch()
    library = tmp_path / "paired.so"
    library.write_bytes(b"reviewed library")
    region = tmp_path / "offer.json"
    region.write_text(json.dumps({"center": [-33, 113], "width_km": 35}))
    args = SimpleNamespace(recording=tmp_path / "opaque", bulk_root=output,
                           archive=tmp_path / "tle", region=region)
    pin = dict(library=str(library), sha256=hashlib.sha256(library.read_bytes()).hexdigest())
    spec = dict(solver="shared-tables" if endpoint_reuse else "stock",
                ingress="paired-sha256", detector=str(detector),
                detector_sha256="c" * 64, paired_sha256=pin, endpoint_reuse=endpoint_reuse,
                recovery_reuse=endpoint_reuse)
    result = trial.run(args, spec)
    assert result["decision"] == "withheld"
    assert ("endpoint_reuse" in result) == endpoint_reuse
    assert ("recovery_reuse" in result) == endpoint_reuse
    assert conservative_recovery.conservative_recovery is recover
    assert v5_direct_cavity.bounded_secant is optimizer
    library.write_bytes(b"substituted")
    with pytest.raises(ValueError, match="library differs"):
        trial.run(args, spec)
def test_failed_orbit_attempt_preserves_acquisition_and_stops_on_unrelated_failures(tmp_path):
    error = dict(exit_code=1, stderr='File "/experiment/orbit_projector.py", line 66, in prepare\n'
                                     'ValueError: orbit phase interpolation never extrapolates\n')
    folder = tmp_path / "fast-scan-automatic-work/native"
    folder.mkdir(parents=True)
    native = dict(source=dict(session_id="test", raw_recording_authority_digest="raw"),
                  provenance=dict(window_count=12, processed_windows=9, invalid_capture=3, skipped_fast_score=0))
    (folder / "detections.json").write_text(json.dumps(native))
    evidence = bench.failed_solver_evidence(tmp_path, {"center": [0, 0]}, error)
    assert evidence["receipt"]["decision"] == "solver_failed" and evidence["artifacts"] == []
    assert evidence["raw_authority"] == "raw" and evidence["arms"]["c0"]["latlon"] is None
    with pytest.raises(ValueError, match="Unrecognized"):
        bench.failed_solver_evidence(tmp_path, {}, dict(exit_code=1, stderr="FileNotFoundError"))
    (folder / "terminal.json").write_text("{}")
    with pytest.raises(ValueError, match="published terminal"):
        bench.failed_solver_evidence(tmp_path, {}, error)
