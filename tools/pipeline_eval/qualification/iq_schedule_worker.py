"""Apply the recorded visit schedule before the unchanged ordinary detector."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.qualification import whole_cavity_worker as cavity
from tools.pipeline_eval.qualification import whole_memory_chain_worker as raw
from tools.pipeline_eval.variants.interleaved_visits import scheduled, select_document

CPUS, MEMORY, LIMIT = cavity.CPUS, cavity.MEMORY, cavity.LIMIT
METHOD = "iq_schedule"
BOUNDARY = "Complete saved IQ through scheduled ordinary GLRT and lifetime-bounded secant cavity"


def native_stub(receiver_ids):
    return dict(rows=[dict(receiver_id=rx, candidates=[]) for rx in receiver_ids])


def lane():
    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.storage.fast_scan import FastSegmentSource

    windows, analyze = FastSegmentSource.windows, NativeShortWindow.analyze
    current = None
    calls = []

    def dispatch(source):
        nonlocal current
        if source.receiver_ids != (0, 1):
            raise ValueError("dual-receiver archive required")
        for w in windows(source):
            visit = w.acquisition["global_visit"]
            current = (visit, scheduled(visit, w.target["channel"]))
            yield w
        current = None

    def gate(detector, *args, **kwargs):
        if current is None:
            raise ValueError("detector call does not belong to an authenticated visit")
        visit, include = current
        calls.append((visit, include))
        if include:
            return analyze(detector, *args, **kwargs)
        return native_stub((0, 1))

    with (
        patch.object(FastSegmentSource, "windows", dispatch),
        patch.object(NativeShortWindow, "analyze", gate),
    ):
        raw.raw_lane()
    print("schedule-lane: " + json.dumps(calls, separators=(",", ":")), file=sys.stderr, flush=True)


def verify_effective(emitted, full):
    expected, coverage = select_document(full)
    effective, fresh_coverage = select_document(emitted)
    if fresh_coverage != coverage:
        raise ValueError("fresh and full source differ in retained visit support")
    for fresh, original in zip(emitted["source"]["probes"], full["source"]["probes"], strict=True):
        keep = scheduled(original["visit_index"], original["channel"])
        want = original if keep else dict(original, candidates=[])
        if fresh != want:
            raise ValueError(
                "native retained factor or omitted envelope differs from full ordinary"
            )
    identities = {}
    for scope, key in (("source", "analysis_manifest_sha256"), ("provenance", "run_id")):
        if effective[scope][key] != expected[scope][key]:
            identities[f"{scope}.{key}"] = dict(
                emitted=effective[scope][key], effective=expected[scope][key]
            )
            effective[scope] = dict(effective[scope], **{key: expected[scope][key]})
    if effective != expected:
        raise ValueError("effective numerical input differs beyond the measured policy selection")
    return effective, coverage, identities


def assemble(out, ident, deadline, detector):
    from tools.pipeline_eval.qualification import cavity_lifetime_worker
    from tools.pipeline_eval.qualification import recording_to_v5 as previous
    from tools.pipeline_eval.qualification.full_v5_check import _load_case, _sha
    from tools.pipeline_eval.qualification.secant_end_to_end import capture_duration
    from tools.pipeline_eval.variants import orbit_projector, v5_lean

    start = raw.mark("raw complete; schedule audit enter")
    if json.loads((out / "raw-worker-exits.json").read_bytes())["exit_codes"] != [0, 0]:
        raise ValueError("both saved-IQ schedule lanes must complete")
    lanes, telemetry, calls = [], [], []
    for lane_id, cpu in enumerate(CPUS):
        with (out / f"replayed-{lane_id}.jsonl").open() as file:
            lanes.append(list(map(json.loads, file)))
        log = (out / f"replayed-{lane_id}.log").read_text().splitlines()
        stage = [
            json.loads(line.removeprefix("whole-lane-result: "))
            for line in log
            if line.startswith("whole-lane-result: ")
        ]
        decisions = [
            json.loads(line.removeprefix("schedule-lane: "))
            for line in log
            if line.startswith("schedule-lane: ")
        ]
        if (
            len(stage) != 1
            or len(decisions) != 1
            or any(
                stage[0][b]["cgroup"] != start["cgroup"] or stage[0][b]["cpus"] != [cpu]
                for b in ("start", "end")
            )
        ):
            raise ValueError("raw lane did not publish its bound schedule or resource receipt")
        row, marks = stage[0], decisions[0]
        row["original_valid_visit_count"] = len(marks)
        row["skipped_valid_visits"] = [v for v, keep in marks if not keep]
        row["native_timings_s"] = [
            times for (_, keep), times in zip(marks, row["native_timings_s"], strict=True) if keep
        ]
        calls.extend(marks)
        telemetry.append(row)
    case = _load_case(ident)
    capture = json.loads((out / "capture.json").read_bytes())
    document, counts = previous.native_document(case, lanes, capture, detector)
    del lanes
    emitted = out / "emitted-audit-native.json"
    previous.save(emitted, document)
    expected = json.loads((out.parent / "plan.json").read_bytes())["inputs"][ident]
    reference = Path(expected["full_native_path"])
    if _sha(reference) != expected["native_sha256"]:
        raise ValueError("full ordinary factor authority changed")
    full = json.loads(reference.read_bytes())
    effective, coverage, normalization = verify_effective(document, full)
    duration = capture_duration(document)
    truth = sorted(
        (p["visit_index"], scheduled(p["visit_index"], p["channel"]))
        for p in full["source"]["probes"]
        if p["receiver_id"] == 0
    )
    if (
        sorted(map(tuple, calls)) != truth
        or sum(len(r["native_timings_s"]) for r in telemetry) != coverage["retained_visits"]
    ):
        raise ValueError("actual native calls do not equal the expected physical visits")
    del document, full
    native = out / "native.json"
    previous.save(native, effective)
    del effective
    binding = previous.bind_request(case, native, out / "experiment.json")
    fit = out / "position"
    fit.mkdir()
    request = json.loads(Path(binding["request_path"]).read_bytes())
    archived = json.loads(Path(expected["prior_request_path"]).read_bytes())
    original_request = json.loads(Path(binding["request_path"]).read_bytes())
    for value in (request, archived):
        value["job"]["output_root"] = None
        value["job"]["native_input"] = None
        value["job"]["identity"].pop("input_sha256")
        value["job"]["identity"].pop("run_id")
    if request != archived or request["job"]["evaluation_reference"] is not None:
        raise ValueError("schedule changed the frozen truth-free position settings")
    original_request["job"]["output_root"] = str(fit)
    previous.save(fit / "request.json", original_request)
    library = fit / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    previous.save(
        out / "raw-stages.json",
        dict(
            id=ident,
            raw_complete=start,
            assembly_complete=raw.mark("assembly complete"),
            capture_seconds=duration,
            native_sha256=_sha(native),
            raw_counts=counts,
            raw_lanes=telemetry,
            full_native_sha256=expected["native_sha256"],
            emitted_audit_sha256=_sha(emitted),
            effective_matches_selected_full=True,
            normalization=normalization,
            schedule_coverage=coverage,
        ),
    )
    command = [
        str(v5_lean.PYTHON),
        "-B",
        str(Path(cavity.__file__)),
        "position",
        str(out),
        str(Path(cavity_lifetime_worker.__file__)),
    ]
    env = dict(
        os.environ,
        **previous.SINGLE_THREAD,
        PYTHONPATH=f"{v5_lean.SOURCE}:{v5_lean.RUNNER}:{previous.REPO}",
    )
    os.execve(command[0], command, env)


def main():
    from tools.pipeline_eval.qualification import recording_to_v5 as previous

    if sys.argv[1] != "chain":
        lane()
        return
    ident, out = sys.argv[2], Path(sys.argv[3])
    previous.save(out.parent / f"{ident}-begin.json", dict(start=raw.mark("raw enter"), id=ident))
    with patch.object(previous, "MODULE", "tools.pipeline_eval.qualification.iq_schedule_worker"):
        previous.run_recording(ident, out, CPUS, LIMIT, finish=assemble)


if __name__ == "__main__":
    main()
