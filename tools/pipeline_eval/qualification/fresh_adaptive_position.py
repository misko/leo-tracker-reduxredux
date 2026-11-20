"""Bind the fresh paced emissions to ordinary compact paired position solves."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic, sleep

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from . import (
    adaptive_arrival,
    adaptive_arrival_position,
    arrival_queue,
    fresh_replay,
    support_cross_trial,
)
from .fractional_runtime_whole import verify_request
from .fresh_adaptive import CPUS, ORDER, REPORT, checked_inputs, read
from .full_v5_check import _sha
from .portable_gate_trials import compressed_rows

POSITION_CPUS = {"DS26-0026": 12, "DS29-0047": 13}
STOCK = "stock"
MODES = (STOCK, "adaptive", "fifth")
METHODS = {m: "fresh_adaptive_" + m for m in MODES}


def terminal(path, deadline):
    while not path.is_file():
        if monotonic() >= deadline:
            raise TimeoutError(f"source receipt did not settle for {path.name}")
        sleep(2)
    return read(path)


def raw_trace(raw, ident, mode, source, deadline):
    stem = f"{ident}-{mode}"
    # The per-lane receipt is atomically written by the frozen sealer.
    folder = raw / ident / "receipt"
    end = terminal(folder / (stem + "-lock.json"), deadline)
    actual = folder / "source-lock.json"
    if (end["id"], end["mode"], end["source_lock_sha256"]) != (ident, mode, _sha(actual)):
        raise ValueError("the raw receipt does not belong to this original policy attempt")
    if read(actual) != source:
        raise ValueError("position stage read different raw packet authority")
    for name, digest in end["files"].items():
        whole_iq.checked(folder / name, digest)
    if end["status"] != "complete" or end["raw_verified"] is not True:
        return end, None
    return end, arrival_queue.readgz(folder / (stem + "-trace.json.gz"))


def exact_packets(raw, parent, ident, source, published, trace, mode):
    refs, docs, bindings = checked_inputs(raw, parent, ident)
    identity = source["cases"][ident]
    if bindings != identity["parents"]:
        raise ValueError("whole-replay source receipts changed after the paced worker launched")
    part = identity["modes"][mode]
    events = arrival_queue.readgz(whole_iq.checked(REPORT / part["events"], part["sha256"]))
    if len(events) != len(trace):
        raise ValueError("the real paced attempt does not cover the complete scheduled inventory")
    for out, reference in zip(trace, events, strict=True):
        adaptive_arrival.validate_event(out, reference, mode)
    file = whole_iq.checked(
        fresh_replay.REPORT / "visits.jsonl.gz", published["files"]["visits.jsonl.gz"]
    )
    adaptive_arrival_position.verify_original_packet_hashes(file, ident, docs, refs)
    return docs, refs, bindings


def position(work, ident, mode, source, original, parent, raw, child, deadline):
    cpu = POSITION_CPUS[ident]
    case, request = original
    spec = parent["cases"][ident]
    folder = work / ident / mode
    recording = folder / "recording"
    recording.mkdir(parents=True, exist_ok=False)
    entry = dict(
        id=ident,
        condition=mode,
        method=METHODS[mode],
        mode="matched-tile",
        cpu=cpu,
        tile=spec["tile"],
        paired_capture_sha256=spec["capture_native_sha256"],
        catalog_sha256=spec["catalog_sha256"],
        original_request_sha256=spec["request_sha256"],
    )
    if mode == STOCK:
        basis = raw / ident / "control"
        record = read(basis / "raw.json")
        native = whole_iq.checked(basis / "recording/native.json", record["native_sha256"])
        write(recording / "native.json", native.read_bytes())
        entry.update(raw_status="complete parent stock", raw_verified=True)
    else:
        receipt, trace = raw_trace(child, ident, mode, source, deadline)
        entry.update(
            raw_status=receipt["status"],
            raw_verified=receipt["raw_verified"],
            raw_lock_sha256=_sha(child / ident / "receipt" / f"{ident}-{mode}-lock.json"),
        )
        if trace is None:
            return dict(
                entry,
                native_sha256=None,
                result=adaptive_arrival_position.empty_result(
                    "unavailable", "paced detector did not complete an exact verified packet stream"
                ),
                position_resources=None,
            )
        published = terminal(fresh_replay.REPORT / "prediction-lock.json", deadline)
        docs, refs, bindings = exact_packets(raw, parent, ident, source, published, trace, mode)
        kept, paths, dropped, counts = adaptive_arrival_position.chosen_packets(
            trace, mode, docs, refs
        )
        entry.update(counts=counts, matched_raw_envelopes=len(paths), parent_native=bindings)
        trace_sha = receipt["files"][f"{ident}-{mode}-trace.json.gz"]
        document, _ = adaptive_arrival_position.materialize(
            ident, mode, trace_sha, docs, bindings, kept, paths
        )
        save_json(folder / "emissions.json", dict(emissions=paths, dropped=dropped))
        if not kept:
            return dict(
                entry,
                native_sha256=None,
                result=adaptive_arrival_position.empty_result(
                    "withheld", "no verified detector packets"
                ),
                position_resources=None,
            )
        write(recording / "native.json", encoded(document) + b"\n")
    bound = whole_iq.recording.bind_request(
        case, recording / "native.json", recording / "request.json"
    )["native_sha256"]
    verify_request(
        read(recording / "request.json"),
        request,
        native_path=recording / "native.json",
        native_sha256=bound,
    )
    save_json(folder / "plan.json", dict(receiver=parent["receiver"]))
    save_json(
        folder / "raw.json",
        dict(native_sha256=bound, request_sha256=_sha(recording / "request.json")),
    )
    entry.update(
        native_sha256=bound.removeprefix("sha256:"),
        prepared_request_sha256=_sha(recording / "request.json"),
    )
    return support_cross_trial.service(work, entry)


def run(work, raw, child):
    if (REPORT / "position-plan.json").exists():
        raise FileExistsError("a frozen fresh numerical plan already exists")
    work.mkdir(parents=True)
    initial = read(REPORT / "preregister.json")
    parent = read(
        whole_iq.checked(fresh_replay.REPORT / "source-lock.json", initial["source_receipt_sha256"])
    )
    if whole_iq.receiver_identity(Path(parent["receiver"])) != parent["receiver_files"]:
        raise ValueError("installed numerical receiver differs from the waveform controls")
    with fresh_replay.patched_case(parent):
        originals = {ident: whole_iq.binding(ident) for ident in CPUS}
    programs = (
        Path(__file__),
        Path(adaptive_arrival_position.__file__),
        Path(support_cross_trial.__file__),
    )
    save_json(
        REPORT / "position-plan.json",
        dict(
            cases=POSITION_CPUS,
            order={k: [STOCK, *ORDER[k]] for k in CPUS},
            preregister_sha256=_sha(REPORT / "preregister.json"),
            sources={str(k): _sha(k) for k in programs},
            installed=parent["receiver_files"],
            cap_s=support_cross_trial.LIMIT,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
        ),
    )
    deadline = monotonic() + 1500

    def lane(ident):
        items = []
        # Start the genuine complete-stock control as soon as this parent raw file is sealed.
        terminal(raw / ident / "control/raw.json", deadline)
        items.append(
            position(work, ident, STOCK, None, originals[ident], parent, raw, child, deadline)
        )
        source = terminal(REPORT / f"{ident}-source-lock.json", deadline)
        for mode in ORDER[ident]:
            items.append(
                position(work, ident, mode, source, originals[ident], parent, raw, child, deadline)
            )
        return items

    with ThreadPoolExecutor(2) as pool:
        out = [r for batch in pool.map(lane, CPUS) for r in batch]
    write(REPORT / "predictions.jsonl.gz", compressed_rows(out))
    names = ("position-plan.json", "predictions.jsonl.gz", "preregister.json")
    save_json(
        REPORT / "prediction-lock.json",
        dict(cases=list(CPUS), attempted=len(out), files={p: _sha(REPORT / p) for p in names}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--raw", type=local_output, default=fresh_replay.WORK)
    parser.add_argument("--child", type=local_output, required=True)
    args = parser.parse_args()
    run(args.work, args.raw, args.child)
