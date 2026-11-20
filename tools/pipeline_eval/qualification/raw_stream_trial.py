"""Replay two complete ordinary native captures with bounded compressed IQ reads."""

import argparse
import json
import os
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from ..__main__ import local_output, save_json
from . import raw_robust, raw_stream_archive_worker, raw_stream_reader, recording_to_v5
from . import secant_end_to_end as reference
from .full_v5_check import NATIVE_LIBRARY, REPO, _load_case, _sha
from .secant_end_to_end_worker import cpu_s, stamp

METHOD = "raw_stream"
CASES = reference.CASES
PINS = (1, 23)
REPORT = REPO / "reports/2026_11_19_receiver_screening/inference/raw-stream"
CONTROL = REPORT.parents[1] / "end-to-end"
MODULE = "tools.pipeline_eval.qualification.raw_stream_archive_worker"
SEAL = REPORT / "source-lock.json"


def source_lock():
    control = json.loads((CONTROL / "prediction-lock.json").read_bytes())
    if any(_sha(CONTROL / name) != digest for name, digest in control["files"].items()):
        raise ValueError("whole-IQ ordinary control outputs changed")
    inputs = {}
    for ident in CASES:
        prior = reference.preflight(ident, NATIVE_LIBRARY)
        item = _load_case(ident)
        inputs[ident] = dict(
            capture_era_native_sha256=item["native"]["sha256"],
            expected_ordinary_native_sha256=prior["native_sha256"],
            catalogue_sha256=item["catalog"]["sha256"],
            track_config_sha256=item["track_config"]["sha256"],
        )
    paths = (
        Path(__file__),
        Path(raw_stream_archive_worker.__file__),
        Path(raw_stream_reader.__file__),
        Path(recording_to_v5.__file__),
        Path(reference.__file__),
        reference.FIT_WORKER,
    )
    return dict(
        cases=CASES,
        pins=PINS,
        candidate_sources={p.name: _sha(p) for p in paths},
        inputs=inputs,
        read_block_bytes=raw_stream_reader.READ_BYTES,
        native_library_sha256=_sha(NATIVE_LIBRARY),
        control_prediction_lock_sha256=_sha(CONTROL / "prediction-lock.json"),
        position_source_sha256=_sha(reference.SOURCE),
        cap_s=reference.CAP_S,
    )


def lane_metrics(path):
    marker = raw_stream_archive_worker.METRIC_PREFIX
    lines = [
        line.removeprefix(marker)
        for line in path.read_text().splitlines()
        if line.startswith(marker)
    ]
    if len(lines) != 1:
        raise ValueError("successful raw worker must report one bounded read receipt")
    return json.loads(lines[0])


def run(case_id, directory):
    locked = json.loads(SEAL.read_bytes())
    if locked != json.loads(recording_to_v5.encoded(source_lock())) or os.sched_getaffinity(
        0
    ) != set(PINS):
        raise ValueError("raw replay source, controls or CPU affinity changed")
    case = _load_case(case_id)
    science = locked["inputs"][case_id]
    started, cpu = perf_counter(), cpu_s()

    def finish(out, ident, deadline, detector):
        raw_envelope = stamp(started, cpu)
        assembly_wall, assembly_cpu = perf_counter(), cpu_s()
        lanes = [lane_metrics(out / f"replayed-{worker}.log") for worker in range(len(PINS))]
        raw = raw_robust.assemble_raw(out, ident, deadline, detector)
        path = out / "native.json"
        document = json.loads(path.read_bytes())
        duration = reference.capture_duration(document)
        del document
        if (
            duration <= 0
            or sum(row["decoded_visits"] for row in lanes) != raw["recording_windows"]
            or sum(row["decoded_bytes"] for row in lanes) != raw["iq_bytes"]
            or any(row["largest_read_bytes"] > raw_stream_reader.READ_BYTES for row in lanes)
            or raw["native_sha256"] != _sha(path)
        ):
            raise ValueError("bounded replay did not cover the complete sealed CI16 inventory")
        binding = recording_to_v5.bind_request(case, path, out / "experiment.json")
        assembly = stamp(assembly_wall, assembly_cpu)
        position = reference.profile_fit(case, path, binding, out, "secant", started)
        whole = stamp(started, cpu)
        position.update(
            method=METHOD,
            variant="fresh-iq-streamed-zstd",
            source_lock_sha256=_sha(SEAL),
            whole_chain=whole,
            worker_wall_s=whole["wall_s"],
            worker_cpu_s=whole["cpu_s"],
            raw_replayed_here=True,
        )
        position["result"]["boundary"] = (
            "Bounded authenticated compressed IQ through ordinary GLRT and compact secant v5"
        )
        position["result"]["metrics"].update(
            capture_seconds=duration, actual_wall_s_per_recorded_s=whole["wall_s"] / duration
        )
        save_json(out / "position.json", position)
        save_json(
            out / "stage-receipt.json",
            dict(
                id=ident,
                capture_seconds=duration,
                raw=raw,
                lanes=lanes,
                raw_envelope=raw_envelope,
                factor_assembly_and_binding=assembly,
                fits=position["fit_envelope"],
                whole_chain=whole,
                exact_ordinary_native=raw["native_sha256"]
                == science["expected_ordinary_native_sha256"],
            ),
        )
        print(
            ident,
            position["result"]["status"],
            round(whole["wall_s"], 2),
            raw["native_sha256"],
            flush=True,
        )

    with patch.object(recording_to_v5, "MODULE", MODULE):
        recording_to_v5.run_recording(
            case_id, directory, PINS, reference.CAP_S, NATIVE_LIBRARY, finish=finish
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="action", required=True)
    command.add_parser("lock")
    replay = command.add_parser("run")
    replay.add_argument("case", choices=CASES)
    replay.add_argument("--work", type=Path, required=True)
    opts = parser.parse_args()
    if opts.action == "lock":
        if SEAL.exists():
            raise ValueError("raw adapter source is already locked")
        save_json(SEAL, source_lock())
    else:
        run(opts.case, local_output(opts.work) / opts.case)


if __name__ == "__main__":
    main()
