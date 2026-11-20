"""Smoke-test the incremental ABI under each held recording's installed producer."""

import argparse
import json
from pathlib import Path

from .full_v5_check import _sha
from .recording_to_v5 import ARCHIVE_PYTHON


def payload(samples, edge, release):
    import numpy as np

    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    from ..variants.incremental_rescue import IncrementalRescueCall, SingleLaneScout
    from .full_v5_check import _from_native

    config = dict(sample_rate_hz=10_000_000, fractional_epoch=True)
    templates = [
        np.asarray(qin_edge_pilot_frame(10_000_000, edge, symbol_roll=roll), dtype="<c16")
        for roll in (0, CONTROL_SYMBOL_ROLL)
    ]
    paths = release["paths"]
    for name, path in paths.items():
        if _sha(Path(path)) != release["sha256"][name]:
            raise ValueError("preflight detector or sidecar changed")
    with (
        NativeShortWindow(paths["stock"], *templates, **config) as stock,
        NativeShortWindow(paths["detector"], *templates, **config) as incremental,
        SingleLaneScout(paths["scout"], edge) as scout,
    ):
        before = stock.analyze(samples)
        out, _, lanes, timing = IncrementalRescueCall(incremental, edge, scout=scout)(samples)

    def probes(native):
        return [
            [p for i, c in enumerate(row["candidates"]) if (p := _from_native(i, c)) is not None]
            for row in native["rows"]
        ]

    return dict(
        stock=probes(before),
        incremental=probes(out),
        lanes=lanes,
        timing=timing,
        numpy=np.__version__,
    )


def worker(root):
    import numpy as np

    from leo.analysis.starlink import native_short_window

    manifest = json.loads((root / "fixtures.json").read_bytes())
    if not Path(native_short_window.__file__).is_relative_to(manifest["producer"]):
        raise ValueError("preflight did not load the installed producer")
    rows = []
    for index, row in enumerate(manifest["fixtures"]):
        samples = np.load(root / f"fixture-{index}.npy", allow_pickle=False)
        data = payload(samples, row["archive"][0]["edge"], manifest["release"])
        if data["stock"] != [p["candidates"] for p in row["archive"]]:
            raise ValueError("installed stock preflight did not reproduce archived factors")
        for old, new, lane in zip(data["stock"], data["incremental"], data["lanes"], strict=True):
            gated = any(p["passed_fractional_margin_gate"] for p in old)
            if lane["stock_positive"] != gated or (gated and old != new):
                raise ValueError(
                    "incremental installed ABI unexpectedly changed a stock-positive lane"
                )
        rows.append(
            dict(
                visit=row["visit"],
                iq_sha256=row["iq_sha256"],
                timings=data["timing"],
                trace=data["lanes"],
                numpy=data["numpy"],
            )
        )
    print(json.dumps(rows, sort_keys=True))


def run(ident, work, source, cpu):
    import os
    import subprocess

    import numpy as np

    from .. import whole_iq
    from ..__main__ import ROOT, save_json
    from . import capture_release, hinted_glrt_trial, whole_center_union, whole_incremental_trial
    from .exact_wide_iq_results import detector_rows

    lock = whole_incremental_trial.inputs(whole_incremental_trial.WORK)
    case, _ = whole_iq.binding(ident)
    capture = capture_release.read_capture(case)
    producer = capture_release.producer(case, capture).root
    stock = detector_rows(whole_center_union.WORK / ident / "control")[0]
    modes, fixtures = set(), []
    work.mkdir(parents=True, exist_ok=False)
    for row in stock:
        if row["status"] != "processed":
            continue
        old = row["probes"]
        positives = sum(
            any(c["passed_fractional_margin_gate"] for c in p["candidates"]) for p in old
        )
        if positives in modes:
            continue
        modes.add(positives)
        spec = dict(
            segment=row["segment"],
            sequence=row["sequence"],
            visit=row["visit"],
            iq_sha256=row["iq_sha256"],
            counter=row["sample_start"],
            channel=old[0]["channel"],
            manifest_sha256=lock["cases"][ident]["recording"]["segments"][row["segment"]]["sha256"],
            receiver_ids=[0, 1],
            archive=old,
        )
        samples = hinted_glrt_trial.load_selected(case, spec).samples
        np.save(work / f"fixture-{len(fixtures)}.npy", samples, allow_pickle=False)
        fixtures.append(spec)
        if len(modes) == 3:
            break
    asset = whole_iq.read(source)
    save_json(
        work / "fixtures.json", dict(producer=str(producer), release=asset, fixtures=fixtures)
    )
    (work / "fixtures.json").chmod(0o644)
    with (work / "installed.json").open("xb") as out:
        subprocess.run(
            [
                "timeout",
                "35s",
                "taskset",
                "-c",
                str(cpu),
                "sudo",
                "-n",
                "-u",
                "leo",
                "--",
                "env",
                f"PYTHONPATH={producer}:{ROOT}",
                "OPENBLAS_NUM_THREADS=1",
                "OMP_NUM_THREADS=1",
                "MKL_NUM_THREADS=1",
                str(ARCHIVE_PYTHON),
                "-B",
                "-m",
                "tools.pipeline_eval.qualification.whole_incremental_preflight",
                "worker",
                os.fspath(work),
            ],
            check=True,
            stdout=out,
            cwd=ROOT,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    launch = commands.add_parser("run")
    launch.add_argument("case")
    launch.add_argument("work", type=Path)
    launch.add_argument("release", type=Path)
    launch.add_argument("cpu", type=int)
    commands.add_parser("worker").add_argument("work", type=Path)
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.work)
    else:
        run(args.case, args.work, args.release, args.cpu)
