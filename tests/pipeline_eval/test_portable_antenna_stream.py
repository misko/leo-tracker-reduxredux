import json
import sys
import tarfile
from threading import Event
from types import SimpleNamespace

import pytest

from tools.pipeline_eval.qualification import portable_antenna_build as builder
from tools.pipeline_eval.qualification import portable_antenna_stream as stream
from tools.pipeline_eval.variants.staggered_native import RfStagger


def test_ordered_starts_only_bounded_work_and_preserves_order():
    started = []

    def prepare(item):
        started.append(item)
        return item

    tasks = stream.ordered(range(7), prepare, 2)
    assert next(tasks) == 0 and started == [0, 1]
    assert next(tasks) == 1 and started == [0, 1, 2]
    assert list(tasks) == list(range(2, 7))
    with pytest.raises(ValueError, match="in-flight"):
        list(stream.ordered([], prepare, 3))


def test_relocated_reader_orders_out_of_order_results_across_rf_and_invalid_visits(
    tmp_path, monkeypatch
):
    from leo.analysis.starlink import native_short_window
    from leo.scanner import fast_scan_analysis

    second_completed = Event()
    contexts = []

    class Native:
        def __init__(self, *args, receiver_count, **kwargs):
            assert receiver_count == 1
            contexts.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    def detect(native, samples, primary, *, on_hit):
        assert native in contexts and on_hit
        if samples == 0:
            assert second_completed.wait(timeout=2)
        elif samples == 1:
            second_completed.set()
        rows = [dict(receiver_id=rx, candidates=[samples]) for rx in (0, 1)]
        return {"rows": rows}, primary == 0

    def analyze(window, receivers, predictor, policy, detector):
        if window.samples == 2:
            return "invalid"
        assert [rx.receiver_id for rx in detector(window, receivers)] == [0, 1]
        return "valid"

    results = []

    def run_raw(*args, observation_factory, outputs):
        with observation_factory(receiver_count=2) as process:
            for batch in [[(0, 10), (1, 20), (2, 10)], [(3, 10), (4, 20)]]:
                windows = [
                    SimpleNamespace(
                        acquisition={"global_visit": visit},
                        target={"rf_center_hz": rf},
                        samples=visit,
                    )
                    for visit, rf in batch
                ]
                source = SimpleNamespace(receiver_ids=(0, 1), windows=windows.__iter__)
                results.extend(process(source, None))

    bridge = SimpleNamespace(
        _sha=lambda _: "library",
        encoded=json.dumps,
        _probe=lambda win, lane, candidates: (win.samples, lane, list(candidates)),
        _from_native=lambda i, c: c,
        stream_range=run_raw,
    )
    monkeypatch.setitem(sys.modules, "native_bridge", bridge)
    monkeypatch.setitem(
        sys.modules, "conditional_policy", SimpleNamespace(RfStagger=RfStagger, detect=detect)
    )
    monkeypatch.setattr(native_short_window, "NativeShortWindow", Native)
    monkeypatch.setattr(fast_scan_analysis, "analyze_window", analyze)
    monkeypatch.setattr(stream.os, "sched_setaffinity", lambda *_: None)
    stream.capture(
        dict(
            visit_workers=2,
            cpus=[0, 1],
            detector="partner-on-hit",
            detector_sha256="library",
            out=str(tmp_path),
            segments=[],
            authority={},
            count=5,
        )
    )
    assert len(contexts) == 2
    assert [w.samples for w, _ in results] == [0, 1, 2, 3, 4]
    assert results[2][1] == ("invalid", [], 0.0)
    assert all(
        result[1] == [(w.samples, lane, [w.samples]) for lane in (0, 1)]
        for w, result in results
        if result[0] == "valid"
    )
    ledger = (tmp_path / "conditional-visits.jsonl").read_text().splitlines()
    events = [json.loads(s) for s in ledger]
    assert [(e["visit"], e["primary_receiver"], e["partner_required"]) for e in events] == [
        (0, 0, True),
        (1, 0, True),
        (3, 1, False),
        (4, 1, False),
    ]


def test_portable_build_keeps_native_assets_and_previous_policy_digest(tmp_path):
    report = tmp_path / "public"
    report.mkdir()
    (report / "USAGE.md").write_bytes((builder.REPORT / "USAGE.md").read_bytes())
    folder = builder.build(tmp_path / "installed", report)
    current = json.loads((folder / "files.json").read_bytes())["files"]
    release = json.loads((report / "release.json").read_bytes())
    assert release["manifest_entries"] == 206 and release["application_files"] == 203
    with tarfile.open(builder.PREVIOUS / "portable-receiver-conditional.tar.gz") as previous:
        original = json.load(previous.extractfile("portable-receiver/files.json"))["files"]
    assert set(current) == set(original)
    assert len([k for k in current if k.endswith(".so")]) == 3
    assert all(current[name] == original[name] for name in current if name.endswith(".so"))
    for name in ("receive.py", "capture/native_bridge.py", "capture/conditional_capture.py"):
        compile((folder / name).read_text(), name, "exec")
    # The original miss identity is a public contract. A hit-only run binds the actual packet.
    import ast

    from tools.pipeline_eval.variants import second_on_miss

    path = folder / "capture/conditional_policy.py"
    definitions = ast.parse(path.read_text())
    nodes = [n for n in definitions.body if isinstance(n, ast.FunctionDef) and n.name == "mark"]
    from hashlib import sha256

    scope = {"json": json, "sha256": sha256, "POLICY": second_on_miss.POLICY}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
    doc = dict(
        source=dict(input_manifest_sha256="raw", analysis_manifest_sha256="old"),
        provenance=dict(detector_sha256="detector", excluded_windows=[]),
    )
    assert scope["mark"](doc, []) == second_on_miss.mark(doc, [])
    hit = scope["mark"](doc, [], builder.HIT)
    doc["source"]["analysis_manifest_sha256"] = "a different historical parent"
    assert hit == scope["mark"](doc, [], builder.HIT)
    assert (
        hit["source"]["analysis_manifest_sha256"]
        != second_on_miss.mark(doc, [])["source"]["analysis_manifest_sha256"]
    )
