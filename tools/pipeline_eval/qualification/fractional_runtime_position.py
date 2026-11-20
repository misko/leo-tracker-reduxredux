"""Refit and package the ordered fractional GLRT runtime experiment."""

import argparse
import gzip
import json
from pathlib import Path
from statistics import median, quantiles
from types import SimpleNamespace
from unittest.mock import patch

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import iq_stream
from . import fractional_runtime_eval as run
from . import ordinary_front_position, short_receiver_figures
from .full_v5_check import _load_case, _sha
from .pilot_kernel_eval import _digest

REPORT, CASES, MODES = run.REPORT, run.CASES, run.MODES
POSITION = "fractional_runtime_position"
CONTROL = "fractional_runtime_prepared_control"
BOUNDARY = "Held ordered fractional-epoch GLRT visits plus authenticated ordinary factor archive"


def source_hashes():
    paths = (
        REPORT / "PROTOCOL.md",
        Path(__file__),
        Path(run.__file__),
        run.variant.HEADER,
        Path(run.variant.__file__),
        Path(run.ordinary_prepared.__file__),
        Path(ordinary_front_position.__file__),
        Path(run.ordinary_prepared_eval.__file__),
    )
    return {str(path.resolve().relative_to(ROOT)): _sha(path) for path in paths}


def position(case, work, cpu):
    measured_path = REPORT / f"{case}-host.json.gz"
    measured = run.unpack(measured_path)
    expected = run.ordinary_prepared_eval.archive.SCHEDULE
    variant_path = work / "host-fractional_runtime" / run.NATIVE_LIBRARY.name
    if measured["executable_sha256"][run.METHOD] != _sha(variant_path):
        raise ValueError("the fresh fractional library no longer matches the measured binary")
    keys = [(r["segment"], r["sequence"]) for r in measured["rows"]]
    if keys != [(segment, seq) for segment, seqs in expected for seq in seqs]:
        raise ValueError("the matched native factor roster changed")
    for row in [*measured["rows"], *measured["controls"].values()]:
        if "calls" not in row:
            continue
        if not row["exact"] or any(
            _digest(encoded(row["payloads"][m])) != row["digest"] for m in MODES
        ):
            raise ValueError("Held candidate fields changed or differ from the matched measurement")
    seam = SimpleNamespace(SCHEDULE=expected, sources=source_hashes)
    with (
        patch.multiple(
            ordinary_front_position,
            REPORT=REPORT,
            METHOD=run.METHOD,
            CONTROL=CONTROL,
            BOUNDARY=BOUNDARY,
            ordinary_front_eval=seam,
        ),
        patch.object(
            iq_stream, "MAX_CHUNK_PREFIX", run.ordinary_prepared_eval.archive.CHUNK_PREFIX
        ),
    ):
        ordinary_front_position.position(case, work, cpu)
    receipt = work / f"{case}-position.json"
    data = json.loads(receipt.read_bytes())
    parent = run.ordinary_prepared_eval.REPORT
    parent_path = parent / "position-receipts.json"
    parent_sha = _sha(parent_path)
    if (
        json.loads((parent / "prediction-lock.json").read_bytes())["files"][parent_path.name]
        != parent_sha
    ):
        raise ValueError("Prepared position control differs from its evidence seal")
    control = json.loads(parent_path.read_bytes())[case]["trial"]
    trial, stock = data["trial"], data["stock"]
    for key in ("source_ordinary_sha256", "catalog_sha256", "observation_sha256", "tile"):
        if trial[key] != control[key]:
            raise ValueError(f"Held solve changed the measured prepared control's {key}")
    for role in (trial, stock):
        if any(role["result"][k] != control["result"][k] for k in ("status", "reason", "arms")):
            raise ValueError("Held solve changed a published or diagnostic endpoint")
    data.update(
        trial=dict(trial, method=POSITION),
        stock=dict(control, method=CONTROL),
        parent_position_receipt_sha256=parent_sha,
    )
    save_json(receipt, data)


def arm_summary(rows):
    wall = [r["wall_ms"] + r["read_wall_ms"] for r in rows]
    return dict(
        calls=len(rows),
        emulator_process_wall_median_ms=median(wall),
        emulator_process_wall_p90_ms=quantiles(wall, n=10)[8],
        detector_cpu_total_ms=sum(r["detector_cpu_ms"] for r in rows),
        fractional_epoch_cpu_total_ms=sum(v["fractional_epoch"] for r in rows for v in r["rows"]),
        emulator_peak_rss_kib=max(r["qemu_peak_kib"] for r in rows),
    )


def package(work):
    auth = json.loads((short_receiver_figures.ORDINARY / "recording-receipts.json").read_bytes())
    measurements, stage_rows, build_sources = {}, [], {}
    names = [
        "PROTOCOL.md",
        "figures.json",
        "qualification.json",
        "source-lock.json",
        "stage-results.jsonl.gz",
        "positions.jsonl.gz",
        "control-positions.jsonl.gz",
        "position-receipts.json",
    ]
    for arch in ("host", "arm"):
        inventories = {}
        summarize = run.ordinary_prepared_eval.timing_summary if arch == "host" else arm_summary
        streams = {m: [] for m in MODES}
        for case in CASES:
            path = REPORT / f"{case}-{arch}.json.gz"
            if arch == "arm" and not path.exists():
                continue
            names.append(path.name)
            entry = run.unpack(path)
            visits = [r for r in entry["rows"] if r["status"] == "processed"]
            rows = [c for r in visits for c in r["calls"]]
            for call in rows:
                streams[call["mode"]].append(call)
            inventories[case] = dict(
                visits=len(visits),
                excluded=len(entry["rows"]) - len(visits),
                exact_visits=sum(r["exact"] for r in visits),
                controls={
                    k: dict(exact=v["exact"], positives=v["positives"])
                    for k, v in entry["controls"].items()
                },
                context_wall_ms=entry["context_wall_ms"],
                runner_peak_rss_kib=entry["runner_peak_rss_kib"],
                libraries=entry["executable_sha256"],
            )
            if arch == "host":
                for mode in MODES:
                    method = run.METHOD if mode == run.METHOD else "fractional_runtime_stage_parent"
                    stage_rows.append(
                        dict(
                            id=case,
                            method=method,
                            host_visit_receipt_sha256=_sha(path),
                            catalog_sha256=_load_case(case)["catalog"]["sha256"],
                            source_ordinary_sha256=auth["recordings"][case]["native_sha256"],
                            result=dict(
                                status="withheld",
                                boundary="Warm saved mmap through GLRT",
                                reason="native detector timing stage only",
                                metrics=dict(
                                    position_attempted=False,
                                    visits=len(visits),
                                    timing=summarize([r for r in rows if r["mode"] == mode]),
                                ),
                            ),
                        )
                    )
        if inventories:
            measurements[arch] = dict(
                cases=inventories, totals={k: summarize(v) for k, v in streams.items()}
            )
        for mode in MODES:
            receipt = work / f"{arch}-{mode}" / "build-receipt.json"
            if receipt.exists():
                build_sources[f"{arch}-{mode}"] = _sha(receipt)
    save_json(REPORT / "source-lock.json", dict(sources=source_hashes(), builds=build_sources))
    hl = measurements["host"]["totals"][run.METHOD]
    parity = all(
        v["visits"] == v["exact_visits"] and all(c["exact"] for c in v["controls"].values())
        for v in measurements["host"]["cases"].values()
    )
    save_json(
        REPORT / "qualification.json",
        dict(
            architectures=measurements,
            host_exact=parity,
            passes_20_ms_median=parity and hl["full_wall_median_ms"] < 20,
        ),
    )
    positions = {case: json.loads((work / f"{case}-position.json").read_bytes()) for case in CASES}
    save_json(REPORT / "position-receipts.json", positions)
    files = {
        "stage-results.jsonl.gz": stage_rows,
        "positions.jsonl.gz": [v["trial"] for v in positions.values()],
        "control-positions.jsonl.gz": [v["stock"] for v in positions.values()],
    }
    for name, rows in files.items():
        write(REPORT / name, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))
    save_json(
        REPORT / "prediction-lock.json",
        dict(cases=list(CASES), files={name: _sha(REPORT / name) for name in names}),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, required=True)
    cli.add_argument("--case", choices=CASES)
    cli.add_argument("--cpu", type=int, default=16)
    args = cli.parse_args()
    if args.case:
        position(args.case, local_output(args.work), args.cpu)
    else:
        package(local_output(args.work))
