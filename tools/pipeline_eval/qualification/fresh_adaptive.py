"""Run the unchanged five-or-four arrival worker on two fresh whole-IQ sources."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from .. import iq_service, whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..variants import arrival_policy
from . import (
    adaptive_arrival,
    adaptive_arrival_worker,
    arrival_queue,
    fresh_replay,
    recording_to_v5,
)
from .capture_release import producer, read_capture
from .exact_wide_iq_results import detector_rows
from .full_v5_check import _sha

PARENT = fresh_replay.REPORT
REPORT = PARENT.with_name("fresh-adaptive")
CPUS = {"DS26-0026": 18, "DS29-0047": 19}
ORDER = {"DS26-0026": ("adaptive", "fifth"), "DS29-0047": ("fifth", "adaptive")}
EXPECTED = {
    "DS26-0026": (6770, "0810faed57cd5407eeddff62bba50406fdb4fd9a7657f639303e1ca74e1679ee"),
    "DS29-0047": (6769, "0035ccd0e1d68b5385896bea53aa1f28db82a83dad5552837a130c0c4ed73434"),
}
BRANCHES = {"stock": "control", "fifth": "candidate"}
read = whole_iq.read


def freeze(work):
    if (REPORT / "preregister.json").exists() or work.exists():
        raise FileExistsError("fresh adaptive policy already preregistered")
    parent = read(PARENT / "source-lock.json")
    cases = parent["cases"]
    physical = {
        ident: (row["recording"]["window_count"], row["recording"]["segments"][0]["sha256"])
        for ident, row in cases.items()
    }
    if physical != EXPECTED:
        raise ValueError("fresh metadata roster changed before integration")
    programs = [
        Path(m.__file__)
        for m in (
            arrival_policy,
            adaptive_arrival,
            adaptive_arrival_worker,
            arrival_queue,
            recording_to_v5,
        )
    ] + [Path(__file__), REPORT / "PROTOCOL.md"]
    work.mkdir(parents=True)
    save_json(
        REPORT / "preregister.json",
        dict(
            raw_cpus=CPUS,
            order=ORDER,
            cases=physical,
            receiver=parent["receiver"],
            assets=parent["detectors"],
            source_receipt_sha256=_sha(PARENT / "source-lock.json"),
            selection_sha256=_sha(PARENT / "selection.json"),
            programs={str(p): _sha(p) for p in programs},
            cap_s=arrival_queue.LIMIT_S,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
        ),
    )


def checked_inputs(raw, plan, ident):
    by_branch, documents, bindings = {}, {}, {}
    for name, role in BRANCHES.items():
        attempt = raw / ident / role
        receipt = read(attempt / "raw.json")
        public = plan["cases"][ident]
        local = read(attempt / "plan.json")
        asset = plan["detectors"][role]
        if (
            local["detector_sha256"] != asset["sha256"]
            or local["capture_era_request"] != public["request_sha256"]
            or local["receiver_files"] != plan["receiver_files"]
        ):
            raise ValueError("raw comparison input differs from the selected exact release")
        native = whole_iq.checked(attempt / "recording/native.json", receipt["native_sha256"])
        doc = read(native)
        raw_authority = doc["source"]["raw_recording_authority_digest"]
        if (
            doc["source"]["input_manifest_sha256"] != public["clock_authority"]
            or doc["source"]["session_id"] != public["case"]["session_id"]
            or raw_authority != receipt["raw_authority"]
            or doc["provenance"]["detector_sha256"] != "sha256:" + asset["sha256"]
        ):
            raise ValueError("native analysis source differs from the authenticated waveform")
        entire, clocks, _ = detector_rows(attempt)
        by_clock = {row["visit"]: row for row in clocks}
        by_branch[name] = arrival_queue.reference_events(
            doc,
            [
                dict(
                    visit=r["visit"],
                    status=r["status"],
                    full_visit_sha256=arrival_queue.fingerprint(r),
                    **{k: by_clock.get(r["visit"], {}).get(k) for k in ("wall_s", "cpu_s")},
                )
                for r in entire
            ],
        )
        documents[name] = doc
        bindings[name] = dict(
            native_sha256=_sha(native),
            raw_sha256=_sha(attempt / "raw.json"),
            visit_envelopes_sha256={
                f"replayed-{i}.jsonl": _sha(attempt / "recording" / f"replayed-{i}.jsonl")
                for i in (0, 1)
            },
        )
    keys = (
        "session_id",
        "sample_rate_hz",
        "probe_ms",
        "input_manifest_sha256",
        "raw_recording_authority_digest",
    )
    a, b = (documents[k] for k in BRANCHES)
    if (
        any(a[k] != b[k] for k in ("clock_anchor", "last_sample_counter", "delivery_clocks"))
        or any(a["source"][k] != b["source"][k] for k in keys)
        or a["provenance"]["excluded_windows"] != b["provenance"]["excluded_windows"]
    ):
        raise ValueError("the two full-detector sources have different physical inputs")
    return by_branch, documents, bindings


def prepare_lane(work, raw, ident):
    seal = read(REPORT / "preregister.json")
    parent = read(whole_iq.checked(PARENT / "source-lock.json", seal["source_receipt_sha256"]))
    for name, digest in seal["programs"].items():
        whole_iq.checked(Path(name), digest)
    refs, docs, lineage = checked_inputs(raw, parent, ident)
    events = adaptive_arrival.join_events(refs["stock"], refs["fifth"])
    if len(events) != EXPECTED[ident][0]:
        raise ValueError("missing physical opportunities")
    content = REPORT / f"{ident}-events.json.gz"
    arrival_queue.writegz(content, events)
    capture_case = fresh_replay.local_case(parent, ident)
    capture = dict(
        read_capture(capture_case),
        case=capture_case,
        segments_sha256=recording_to_v5.digest(capture_case["recording"]["segments"]),
    )
    if capture["input_manifest_sha256"] != parent["cases"][ident]["clock_authority"]:
        raise ValueError("replay decoder would consume a different capture manifest")
    case = dict(
        cpu=CPUS[ident],
        capture=capture,
        producer=str(producer(capture_case, capture).root),
        modes={mode: dict(events=content.name, sha256=_sha(content)) for mode in ORDER[ident]},
        raw_recording_sha256=docs["stock"]["source"]["raw_recording_authority_digest"],
        parents=lineage,
    )
    bound = dict(
        cases={ident: case},
        programs=seal["programs"],
        assets=seal["assets"],
        order=ORDER,
        preregistration_sha256=_sha(REPORT / "preregister.json"),
        memory_max=whole_iq.MEMORY,
        memory_swap_max=0,
        limit_s=arrival_queue.LIMIT_S,
    )
    report = work / ident / "receipt"
    report.mkdir(parents=True, exist_ok=False)
    # The existing raw sealer binds a study-local source-lock and exact event file.
    (report / content.name).write_bytes(content.read_bytes())
    save_json(report / "source-lock.json", bound)
    save_json(REPORT / f"{ident}-source-lock.json", bound)
    return case, bound, report


def run_lane(work, raw, ident):
    case, source, receipts = prepare_lane(work, raw, ident)
    assets = source["assets"]
    for asset in assets.values():
        whole_iq.checked(Path(asset["path"]), asset["sha256"])
    print(ident, "both full parent envelope streams verified", flush=True)
    for mode in ORDER[ident]:
        with (
            patch.object(arrival_queue, "MODULE", adaptive_arrival_worker.MODULE),
            patch.object(iq_service, "MODULE", adaptive_arrival_worker.MODULE),
        ):
            arrival_queue.launch(work / ident / mode, case, mode, assets, receipts)
        adaptive_arrival.seal(work, receipts, ident, mode, source)
        for path in receipts.glob(f"{ident}-{mode}-*"):
            (REPORT / path.name).write_bytes(path.read_bytes())


def run(work, raw, ident):
    if ident:
        run_lane(work, raw, ident)
        return
    # Separate processes avoid changing a shared launch module between lane contexts.
    from subprocess import run as run_process
    from sys import executable

    def lane(case):
        run_process(
            [
                executable,
                "-m",
                __name__.replace("__main__", "tools.pipeline_eval.qualification.fresh_adaptive"),
                "replay",
                str(work),
                "--raw",
                str(raw),
                "--case",
                case,
            ],
            cwd=ROOT,
            check=True,
        )

    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lane, CPUS))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "replay"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--raw", type=local_output, default=fresh_replay.WORK)
    parser.add_argument("--case", choices=tuple(CPUS))
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    else:
        run(args.work, args.raw, args.case)
