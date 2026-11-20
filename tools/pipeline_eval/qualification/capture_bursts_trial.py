"""Compare matched duty schedules on authenticated full capture-era factor inputs."""

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import capture_bursts, selective_capture
from . import margin_admission_inputs, support_cross_trial
from .fractional_runtime_whole import verify_request
from .full_v5_check import BULK, FROZEN, _sha
from .portable_gate_trials import compressed_rows

REPORT = ROOT / "reports/2026_11_19_receiver_screening/support-preserving/capture-bursts"
SALT = "capture-bursts-v1"
GATE = "passed_fractional_margin_gate"
EXCLUDED = frozenset(
    {
        "DS26-0014",
        "DS26-0026",
        "DS26-0036",
        "DS26-0076",
        "DS26-0122",
        "DS26-0146",
        "DS26-0162",
        "DS26-0168",
        "DS26-0172",
        "DS26-0191",
        "DS26-0217",
        "DS26-0237",
        "DS26-0285",
        "DS29-0082",
        "DS29-0127",
        "DS29-0174",
        "DS29-0316",
        "DS29-0519",
        "DS29-0604",
    }
)
GROUPS = ("DS26", "DS29")
ORDER = (
    ("full", "periodic", "burst", "burst_high", "periodic_high"),
    ("full", "burst", "periodic", "periodic_high", "burst_high"),
)
CORES = (16, 17)
read = whole_iq.read


def sources():
    files = (
        Path(__file__),
        Path(capture_bursts.__file__),
        Path(selective_capture.__file__),
        Path(support_cross_trial.__file__),
        Path(whole_iq.__file__),
        ROOT / "tools/pipeline_eval/qualification/margin_admission_trial.py",
        ROOT / "tools/pipeline_eval/qualification/fractional_runtime_whole.py",
        ROOT / "tools/pipeline_eval/qualification/recording_to_v5.py",
        REPORT / "PROTOCOL.md",
        FROZEN / "provenance.json",
    )
    return {str(p.relative_to(ROOT)): _sha(p) for p in files}


def ranked(group):
    inventory = FROZEN / "inputs.jsonl"
    whole_iq.checked(inventory, read(FROZEN / "provenance.json")["files"][inventory.name])
    ids = [
        rec["id"]
        for rec in map(json.loads, inventory.read_bytes().splitlines())
        if rec["panel"] == group and rec["id"] not in EXCLUDED
    ]
    return sorted(ids, key=lambda ident: sha256(f"{SALT}:{ident}".encode()).digest())


def choose(group):
    rejected = []
    for ident in ranked(group):
        try:
            case, parent = whole_iq.binding(ident)
            whole_iq.checked(BULK / case["catalog"]["path"], case["catalog"]["sha256"])
            native = whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"])
            document = read(native)
            original = document["source"]
            if (
                original["session_id"] != case["session_id"]
                or document["provenance"]["run_id"] != case["run_id"]
                or original["probe_ms"] != 20
                or original["sample_rate_hz"] != 10_000_000
            ):
                raise ValueError("original factor identity or short-window geometry differs")
            metadata = capture_bursts.inventories(document)
            assignments = {
                mode: capture_bursts.scheduled_visits(metadata, mode)
                for mode in capture_bursts.CALLS
            }
        except (ValueError, OSError, KeyError) as error:
            rejected.append(dict(id=ident, reason=str(error)))
            continue
        return case, parent, native, document, metadata, assignments, rejected
    raise ValueError(f"no eligible authenticated {group} capture: {rejected!r}")


def stage(work, receiver, cpu, order, case, parent, native, document, metadata, assignments):
    tasks = []
    clocks = document["delivery_clocks"]
    elapsed = (clocks[-1]["monotonic_ns"] - clocks[0]["monotonic_ns"]) / 1e9
    for mode in order:
        path = work / case["id"] / mode
        recording = path / "recording"
        recording.mkdir(parents=True, exist_ok=False)
        candidate, request = recording / "native.json", recording / "request.json"
        picked = assignments.get(mode)
        if picked is None:
            payload = document
            write(candidate, native.read_bytes())
        else:
            identity = whole_iq.recording.digest([SALT, mode, case["native"]["sha256"], picked])
            payload = capture_bursts.select_document(document, picked, identity)
            write(candidate, encoded(payload) + b"\n")
        digest = whole_iq.recording.bind_request(case, candidate, request)["native_sha256"]
        verify_request(read(request), parent, native_path=candidate, native_sha256=digest)
        save_json(path / "plan.json", dict(receiver=str(receiver)))
        save_json(path / "raw.json", dict(native_sha256=digest, request_sha256=_sha(request)))
        chosen = set(v for v, _ in metadata) if picked is None else set(picked)
        liveliness = [
            p for p in payload["source"]["probes"] if any(c[GATE] for c in p["candidates"])
        ]
        tasks.append(
            dict(
                id=case["id"],
                condition=mode,
                method="capture_bursts_" + mode,
                mode="matched-tile",
                cpu=cpu,
                native_sha256=digest.removeprefix("sha256:"),
                prepared_request_sha256=_sha(request),
                paired_capture_sha256=case["native"]["sha256"],
                original_request_sha256=case["request"]["sha256"],
                catalog_sha256=case["catalog"]["sha256"],
                tile={
                    "center": parent["job"]["search_center"],
                    "screen": parent["job"]["screen_center"],
                },
                total_visits=document["provenance"]["window_count"],
                valid_visits=len(metadata),
                detector_calls=len(chosen),
                scheduled_by_channel=Counter(channel for v, channel in metadata if v in chosen),
                positive_probes=len(liveliness),
                positive_stereo_visits=len({p["visit_index"] for p in liveliness}),
                candidates=sum(len(p["candidates"]) for p in payload["source"]["probes"]),
                delivery_span_s=elapsed,
            )
        )
    return tasks


def freeze(work):
    if (REPORT / "plan.json").exists():
        raise FileExistsError("the prospective experiment plan already exists")
    work.mkdir(exist_ok=False)
    source = read(support_cross_trial.checked(margin_admission_inputs.WIDE, "source-lock.json"))
    receiver = Path(source["receiver"])
    if whole_iq.receiver_identity(receiver) != source["receiver_files"]:
        raise ValueError("installed compact receiver differs from prior sealed runtime")
    trials, decisions, authority = [], {}, {}
    for group, cpu, order in zip(GROUPS, CORES, ORDER, strict=True):
        case, parent, native, document, metadata, assignments, rejected = choose(group)
        ident = case["id"]
        decisions[ident] = assignments
        authority[ident] = dict(
            candidate_order=ranked(group),
            rejected=rejected,
            causal_tle=parent["causal_snapshots"],
            track_config=parent["job"]["track_config"],
            capture_source_sha256=whole_iq.recording.digest(
                [
                    document["clock_anchor"],
                    document["delivery_clocks"],
                    metadata,
                    document["provenance"]["excluded_windows"],
                ]
            ),
        )
        trials.extend(
            stage(work, receiver, cpu, order, case, parent, native, document, metadata, assignments)
        )
    save_json(REPORT / "schedule.json", decisions)
    plan = dict(
        cases=list(decisions),
        salt=SALT,
        excluded=sorted(EXCLUDED),
        trials=trials,
        authority=authority,
        sources=sources(),
        worker_limit_s=support_cross_trial.LIMIT,
        limit_bytes=whole_iq.MEMORY,
        swap_bytes=0,
        receiver=str(receiver),
        receiver_files=source["receiver_files"],
        schedule_sha256=_sha(REPORT / "schedule.json"),
    )
    save_json(REPORT / "plan.json", plan)
    return plan


def run(work):
    plan = freeze(work)
    print("sealed", plan["cases"], _sha(REPORT / "plan.json"), flush=True)

    def lane(cpu):
        return [
            support_cross_trial.service(work, row) for row in plan["trials"] if row["cpu"] == cpu
        ]

    with ThreadPoolExecutor(2) as pool:
        result = [row for batch in pool.map(lane, CORES) for row in batch]
    write(REPORT / "positions.jsonl.gz", compressed_rows(result))
    files = ("positions.jsonl.gz", "plan.json", "schedule.json", "PROTOCOL.md")
    save_json(
        REPORT / "prediction-lock.json",
        dict(cases=plan["cases"], files={name: _sha(REPORT / name) for name in files}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    run(parser.parse_args().work)
