"""Use the measured alternate detector in the unchanged capped whole-IQ service."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.qualification import whole_cavity_worker as cavity
from tools.pipeline_eval.qualification import whole_memory_chain_worker as raw

CPUS, MEMORY, LIMIT = cavity.CPUS, cavity.MEMORY, cavity.LIMIT
METHOD = "whole_fractional"
BOUNDARY = "Saved IQ through exact prepared-fractional ordinary GLRT and bounded secant cavity"
LIBRARY = Path(
    "/tmp/ordinary-fractional-runtime-20261119/host-fractional_runtime/libleo-adaptive-detector.so"
)
LIBRARY_SHA256 = "e545c28554c9db50fe5aece28e7c8ce6ab2b2504db13ab946fbff0f0a190fe0d"
BUILD_SHA256 = "33ff39af0615b29cb2ddc112d5da1059ae0f0f0cb70bd776cce45cf9cef997f8"


def assemble(out, ident, deadline, detector):
    from tools.pipeline_eval.qualification import cavity_lifetime_worker
    from tools.pipeline_eval.qualification import fractional_runtime_whole as parity
    from tools.pipeline_eval.qualification import recording_to_v5 as previous
    from tools.pipeline_eval.qualification.full_v5_check import NATIVE_LIBRARY, _load_case, _sha
    from tools.pipeline_eval.qualification.secant_end_to_end import capture_duration
    from tools.pipeline_eval.variants import orbit_projector, v5_lean

    start = raw.mark("raw complete; candidate factor parity enter")
    if json.loads((out / "raw-worker-exits.json").read_bytes())["exit_codes"] != [0, 0]:
        raise ValueError("both prepared-fractional raw lanes must complete")
    lanes, telemetry = [], []
    for lane, cpu in enumerate(CPUS):
        with (out / f"replayed-{lane}.jsonl").open() as stream:
            lanes.append(list(map(json.loads, stream)))
        log = (out / f"replayed-{lane}.log").read_text().splitlines()
        rows = [
            json.loads(line.removeprefix("whole-lane-result: "))
            for line in log
            if line.startswith("whole-lane-result: ")
        ]
        if len(rows) != 1 or any(
            rows[0][b]["cgroup"] != start["cgroup"] or rows[0][b]["cpus"] != [cpu]
            for b in ("start", "end")
        ):
            raise ValueError("raw lane did not publish its bound resource receipt")
        telemetry.append(rows[0])
    case = _load_case(ident)
    capture = json.loads((out / "capture.json").read_bytes())
    document, counts = previous.native_document(case, lanes, capture, detector)
    del lanes
    native = out / "native.json"
    previous.save(native, document)
    expected = json.loads((out.parent / "plan.json").read_bytes())["inputs"][ident]
    duration = capture_duration(document)
    receipt = dict(
        id=ident,
        raw_complete=start,
        capture_seconds=duration,
        native_sha256=_sha(native),
        raw_counts=counts,
        raw_lanes=telemetry,
        control_native_sha256=expected["native_sha256"],
        detector_sha256=LIBRARY_SHA256,
    )
    try:
        if (
            sum(len(row["native_timings_s"]) for row in telemetry) != counts["processed_windows"]
            or duration <= 0
        ):
            raise ValueError("candidate visit count differs from its authentic raw call receipt")
        receipt["factor_parity"] = parity.verify_native(
            document, expected["native_sha256"], LIBRARY_SHA256
        )
        receipt["lane_parity"] = parity.compare_lanes(
            out,
            Path(expected["stock_lane_path"]),
            expected_binary=LIBRARY_SHA256,
            control_binary=_sha(NATIVE_LIBRARY),
        )
        if receipt["lane_parity"] != dict(
            visits=case["recording"]["window_count"],
            segments=len(case["recording"]["segments"]),
            lanes=len(CPUS),
        ):
            raise ValueError("raw authoritative lane count differs from the complete recording")
    except ValueError as error:
        previous.save(
            out / "raw-stages.json",
            dict(
                receipt,
                factor_parity_error=str(error),
                assembly_complete=raw.mark("factor parity failed"),
            ),
        )
        raise
    del document
    binding = previous.bind_request(case, native, out / "experiment.json")
    fit = out / "position"
    fit.mkdir()
    request = json.loads(Path(binding["request_path"]).read_bytes())
    archived = json.loads(Path(expected["prior_request_path"]).read_bytes())
    request["job"]["output_root"] = str(fit)
    try:
        parity.verify_request(
            request,
            archived,
            native_path=str(native),
            native_sha256=binding["native_sha256"],
        )
    except ValueError as error:
        previous.save(
            out / "raw-stages.json",
            dict(
                receipt,
                request_parity_error=str(error),
                assembly_complete=raw.mark("request parity failed"),
            ),
        )
        raise
    receipt["request_parity"] = True
    previous.save(fit / "request.json", request)
    receipt["worker_request_sha256"] = _sha(fit / "request.json")
    library = fit / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    previous.save(
        out / "raw-stages.json", dict(receipt, assembly_complete=raw.mark("assembly complete"))
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
        raw.raw_lane()
        return
    ident, out = sys.argv[2], Path(sys.argv[3])
    previous.save(out.parent / f"{ident}-begin.json", dict(start=raw.mark("raw enter"), id=ident))
    with patch.object(
        previous, "MODULE", "tools.pipeline_eval.qualification.whole_fractional_worker"
    ):
        previous.run_recording(ident, out, CPUS, LIMIT, native_library=LIBRARY, finish=assemble)


if __name__ == "__main__":
    main()
