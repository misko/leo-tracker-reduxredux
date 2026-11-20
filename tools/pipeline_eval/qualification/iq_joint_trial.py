"""One actual complete recorded-IQ-to-joint science run per frozen smoke recording."""

import argparse
import json
import os
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from ..__main__ import encoded, local_output, read_predictions, save_json
from ..reference.native_archive import NativeArchive
from ..variants import native_lean
from . import (
    iq_joint_archive_worker,
    raw_robust,
    raw_stream_archive_worker,
    raw_stream_reader,
    raw_stream_trial,
    recording_to_v5,
)
from . import iq_joint_resources as resources
from . import native_joint_trial as joint
from .full_v5_check import NATIVE_LIBRARY, REPO, _load_case, _sha
from .secant_end_to_end_worker import cpu_s, stamp

REPORT = REPO / "reports/2026_11_19_receiver_screening/factors/iq-to-joint"
SEAL = REPORT / "source-lock.json"
MODULE = "tools.pipeline_eval.qualification.iq_joint_archive_worker"
PINS = (14, 15)
CASES = ("DS26-0036", "DS29-0082")
METHOD = "iq_to_joint"
MISSING_ID = "DS26-0036-r0"
CAP_S = 480
WRONG_CAP_S = 60
BOUNDARY = (
    "Complete stored IQ through bounded ordinary GLRT, streaming Graph and joint orbit positioning"
)


def read(path):
    return json.loads(path.read_bytes())


def verify_lock(folder, name="prediction-lock.json"):
    path = folder / name
    lock = read(path)
    if any(_sha(folder / file) != digest for file, digest in lock["files"].items()):
        raise ValueError(f"{path} prediction archive changed")
    return _sha(path)


def missing_offer(case):
    entry = read(joint.phase.corpus.FROZEN / "roof-four-offers.json")[case["id"]]
    if entry["catalog_sha256"] != case["catalog"]["sha256"]:
        raise ValueError("alternate offer is bound to a different causal catalogue")
    (offer,) = (row for row in entry["regions"] if row["id"] == "r0")
    return offer


def source_lock(bundle):
    deployed = joint.sources(bundle)
    if deployed != read(joint.REPORT / "source-lock.json"):
        raise ValueError("joint or streaming Graph source differs from the prior lock")
    stream, compact = raw_stream_trial.REPORT, raw_stream_trial.CONTROL
    parents = [verify_lock(folder) for folder in (stream, compact, joint.REPORT)]
    if read(stream / "source-lock.json")["native_library_sha256"] != _sha(NATIVE_LIBRARY):
        raise ValueError("ordinary native detector differs from the previous whole replay")
    raw = read_predictions(stream / "positions.jsonl.gz")
    graph = read(stream / "graph-receipts.json")
    inputs = {}
    for ident in CASES:
        item = _load_case(ident)
        row = raw[ident]
        if (
            not graph[ident]["equal"]
            or row["capture_era_native_sha256"] != item["native"]["sha256"]
            or row["catalog_sha256"] != item["catalog"]["sha256"]
        ):
            raise ValueError("previous complete ordinary input authority changed")
        inputs[ident] = dict(
            ordinary_native_sha256=row["native_sha256"],
            ordinary_graph_sha256=graph[ident]["candidate"]["projection_sha256"],
            capture_era_native_sha256=item["native"]["sha256"],
            catalogue_sha256=item["catalog"]["sha256"],
            track_config_sha256=item["track_config"]["sha256"],
            window_count=item["recording"]["window_count"],
        )
    files = [
        Path(__file__),
        *[
            Path(module.__file__)
            for module in (
                iq_joint_archive_worker,
                resources,
                raw_stream_archive_worker,
                raw_stream_reader,
                raw_robust,
                recording_to_v5,
            )
        ],
    ]
    return dict(
        cases=CASES,
        pins=PINS,
        caps=dict(
            whole_s=CAP_S,
            wrong_tile_s=WRONG_CAP_S,
            raw_lane_as_mib=resources.RAW_AS_MIB,
            assembly_as_mib=resources.ASSEMBLY_AS_MIB,
            joint_as_mib=native_lean.AS_LIMIT_MIB,
        ),
        inputs=inputs,
        source_sha256={path.name: _sha(path) for path in files},
        joint_sources=deployed,
        ordinary_raw_lock_sha256=parents[0],
        ordinary_compact_lock_sha256=parents[1],
        capture_era_joint_lock_sha256=parents[2],
        detector_binary_sha256=_sha(NATIVE_LIBRARY),
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        wrong_offer=missing_offer(_load_case(CASES[0])),
    )


def bind_fresh(case, path, digest, offer=None):
    if _sha(path) != digest:
        raise ValueError("mounted file differs from the fresh native factor digest")
    packet, paths = joint.native.request(case, "native", offer=offer)
    packet["native"]["sha256"] = digest
    paths["native"] = path
    return packet, paths


def fit(case, path, digest, bundle, cap, *, offer=None):
    packet, paths = bind_fresh(case, path, digest, offer)
    ident = case["id"] if offer is None else MISSING_ID
    query = dict(
        id=ident,
        recording=case["id"],
        cohort="roof" if offer is None else "wrong_offer",
        packet=packet,
    )
    t0, cpu = perf_counter(), cpu_s()
    with patch.object(joint, "CAP", cap):
        row = joint.attempt(query, paths, PINS[0], bundle)
    if row["input_sha256"] != sha256(encoded(packet)).hexdigest():
        raise ValueError("native worker request digest differs from the submitted packet")
    if row["result"]["status"] in ("ok", "withheld") and (
        row["counts"]["native_bytes"] != path.stat().st_size
        or not row["observation_sha256"]
        or row["address_space_limit_mib"] != native_lean.AS_LIMIT_MIB
        or any("localization_v3" in p or "v5_" in p for p in row["imported_first_party"])
    ):
        raise ValueError(
            "candidate did not consume its complete factors with the frozen capped Graph path"
        )
    row.update(
        method=METHOD,
        mode="matched-tile" if offer is None else "wrong-region",
        capture_era_native_sha256=case["native"]["sha256"],
        fit_envelope=stamp(t0, cpu),
    )
    row["result"]["boundary"] = BOUNDARY if offer is None else joint.BOUNDARY
    return row, packet


def run(case_id, directory, bundle):
    resources.cap_address_space(resources.ASSEMBLY_AS_MIB)
    locked = read(SEAL)
    if locked != json.loads(encoded(source_lock(bundle))) or os.sched_getaffinity(0) != set(PINS):
        raise ValueError("expected locked complete recording and CPUs 14/15")
    case = _load_case(case_id)
    expected = locked["inputs"][case_id]
    start, cpu = perf_counter(), cpu_s()

    def finish(out, ident, deadline, detector):
        raw_envelope = stamp(start, cpu)
        t0, cpu0 = perf_counter(), cpu_s()
        logs = [out / f"replayed-{lane}.log" for lane in range(len(PINS))]
        lanes = [raw_stream_trial.lane_metrics(log) for log in logs]
        raw_rss = resources.raw_memory(logs)
        raw = raw_robust.assemble_raw(out, ident, deadline, detector)
        native = out / "native.json"
        digest = raw["native_sha256"]
        if (
            digest != expected["ordinary_native_sha256"]
            or sum(lane["decoded_bytes"] for lane in lanes) != raw["iq_bytes"]
            or sum(lane["decoded_visits"] for lane in lanes) != expected["window_count"]
            or any(lane["largest_read_bytes"] > raw_stream_reader.READ_BYTES for lane in lanes)
        ):
            raise ValueError("fresh bounded source is incomplete or differs from ordinary GLRT")
        with native.open("rb") as stream:
            clock = NativeArchive(native_lean.VerifiedBlocks(stream)).meta
        actual = clock["duration_s"]
        assembly = stamp(t0, cpu0)
        cap = min(joint.CAP, int(deadline - (perf_counter() - start)) - 2)
        if cap < 1:
            raise TimeoutError("whole-recording budget exhausted at the native checkpoint")
        row, packet = fit(case, native, digest, bundle, cap)
        whole = stamp(start, cpu)
        if row.get("counts") and row["counts"]["probes"] != raw["probe_rows"]:
            raise ValueError("streaming Graph did not read the complete two-receiver probe set")
        row.update(
            worker_wall_s=whole["wall_s"],
            worker_cpu_s=whole["cpu_s"],
            raw_replayed_here=True,
            source_lock_sha256=_sha(SEAL),
        )
        save_json(out / "position.json", row)
        save_json(
            out / "stages.json",
            dict(
                id=ident,
                clock=clock,
                duration_s=actual,
                wall_s_per_recorded_s=whole["wall_s"] / actual,
                raw=raw,
                raw_lanes=lanes,
                raw_memory=raw_rss,
                raw_envelope=raw_envelope,
                factor_assembly=assembly,
                whole_chain=whole,
                parent_process_memory=resources.memory(),
                native_query=packet,
                graph_sha256=row.get("observation_sha256"),
                equals_prior_ordinary_graph=row.get("observation_sha256")
                == expected["ordinary_graph_sha256"],
            ),
        )
        if ident == CASES[0]:
            wrong, wrong_packet = fit(
                case, native, digest, bundle, WRONG_CAP_S, offer=locked["wrong_offer"]
            )
            wrong.update(raw_replayed_here=False, source_lock_sha256=_sha(SEAL))
            save_json(out / "missing-tile.json", dict(prediction=wrong, native_query=wrong_packet))
        print(
            ident,
            "whole raw-to-joint",
            row["result"]["status"],
            round(whole["wall_s"], 2),
            flush=True,
        )

    with patch.object(recording_to_v5, "MODULE", MODULE):
        recording_to_v5.run_recording(
            case_id, directory, PINS, CAP_S, NATIVE_LIBRARY, finish=finish
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=joint.BUNDLE)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("lock")
    replay = actions.add_parser("run")
    replay.add_argument("case", choices=CASES)
    replay.add_argument("--work", type=Path, required=True)
    options = parser.parse_args()
    if options.action == "lock":
        if SEAL.exists():
            raise ValueError("the complete chain is already locked")
        save_json(SEAL, source_lock(options.bundle))
    else:
        run(options.case, local_output(options.work) / options.case, options.bundle)


if __name__ == "__main__":
    main()
