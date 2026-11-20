"""Prepare and qualify a relocatable chronological AArch64 dual-RX detector capsule."""

import argparse
import gzip
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import differential_pilot
from . import arrival_queue, differential_pilot_eval, hinted_glrt_trial, whole_center_union
from .arm_receiver_build import BENCH, LAUNCHER, REPORT, SOURCE, WORK, check
from .exact_wide_iq_results import detector_rows
from .full_v5_check import _from_native, _load_case, _sha, compare_probes

CASES = ("DS26-0197", "DS29-0316")
CONTROLS = ("zero", "one-frame", "strong")
MODES = ("stock", "fifth")
PARENT = whole_center_union.REPORT
PARENT_PIN = "14ab3e27d00c79c090896a55c6d9340fe6eb2c99077d59ddfbc0f4d0a1a31c6a"
QEMU = Path("/usr/bin/qemu-aarch64")
REPEATS = 2
PARTS = ("exact.c16", "control.c16", "filters.c8", "energies.f64")


def read(path):
    return json.loads(path.read_bytes())


def inputs(work):
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    destination = work / "capsule"
    destination.mkdir(exist_ok=False)
    (destination / "templates").mkdir()
    prior = read(check(PARENT / "prediction-lock.json", PARENT_PIN))
    authority = read(check(PARENT / "source-lock.json", prior["files"]["source-lock.json"]))
    roster = {}
    archival = {}
    for ident in CASES:
        case = _load_case(ident)
        if case["recording"] != authority["cases"][ident]["recording"]:
            raise ValueError("chronological fixture is detached from the original capture")
        controls = {
            mode: detector_rows(whole_center_union.WORK / ident / role)[0]
            for mode, role in zip(MODES, ("control", "candidate"), strict=True)
        }
        rows = []
        packet = controls["stock"][0]["probes"][0]
        edge = packet["edge"]
        if edge in roster:
            raise ValueError("fixture requires both Qin pilot edges")
        folder = destination / "fixtures" / edge
        folder.mkdir(parents=True)
        for i, raw in enumerate(controls["stock"][:6]):
            probes = raw["probes"]
            if raw["visit"] != i or raw["status"] != "processed" or len(probes) != 2:
                raise ValueError("the declared first chronological valid batch is incomplete")
            if any(raw[k] != controls["fifth"][i][k] for k in raw if k != "probes"):
                raise ValueError("detector parents did not use the same physical visit")
            manifest = case["recording"]["segments"][raw["segment"]]["sha256"]
            locator = dict(
                segment=raw["segment"],
                sequence=raw["sequence"],
                visit=i,
                iq_sha256=raw["iq_sha256"],
                counter=raw["sample_start"],
                channel=probes[0]["channel"],
                receiver_ids=[0, 1],
                manifest_sha256=manifest,
            )
            iq = hinted_glrt_trial.load_selected(case, locator).samples
            path = folder / f"{i:02d}-{ident}-v{i}.ci16"
            write(path, iq.tobytes())
            check(path, raw["iq_sha256"].removeprefix("sha256:"))
            rows.append(
                dict(
                    **locator,
                    id=ident,
                    kind="recorded",
                    edge=edge,
                    file=str(path.relative_to(destination)),
                    delivery_clock=raw["delivery_clock"],
                )
            )
        chronological(rows)
        archival[edge] = {mode: [r["probes"] for r in data[:6]] for mode, data in controls.items()}
        for i, tag in enumerate(CONTROLS, start=6):
            iq, plant = differential_pilot_eval.synthetic(edge, tag)
            path = folder / f"{i:02d}-{tag}.ci16"
            write(path, iq.tobytes())
            rows.append(
                dict(
                    id=edge + "-" + tag,
                    kind="control",
                    control=tag,
                    edge=edge,
                    file=str(path.relative_to(destination)),
                    iq_sha256=_sha(path),
                    plant=plant,
                )
            )
        roster[edge] = rows
        for roll, name in ((0, "exact.c16"), (CONTROL_SYMBOL_ROLL, "control.c16")):
            source = qin_edge_pilot_frame(10_000_000, edge, symbol_roll=roll)
            np.asarray(source, dtype="<c16").tofile(destination / f"templates/{edge}-{name}")
        filters = differential_pilot.filters(edge)
        np.stack([k for k, _ in filters], dtype="<c8").tofile(
            destination / f"templates/{edge}-filters.c8"
        )
        np.stack([e for _, e in filters], dtype="<f8").tofile(
            destination / f"templates/{edge}-energies.f64"
        )
    paths = (
        Path(__file__),
        Path(differential_pilot.__file__),
        Path(differential_pilot_eval.__file__),
        Path(hinted_glrt_trial.__file__),
        Path(arrival_queue.__file__),
        REPORT / "PROTOCOL.md",
    )
    save_json(
        destination / "fixtures.json",
        dict(
            roster=roster,
            parent_prediction_lock=PARENT_PIN,
            parent_source_sha256=prior["files"]["source-lock.json"],
            sources={str(p.relative_to(ROOT)): _sha(p) for p in paths},
            templates={
                str(p.relative_to(destination)): _sha(p)
                for p in sorted((destination / "templates").glob("*"))
            },
        ),
    )
    save_json(work / "archived-probes.json", archival)


def chronological(rows):
    if [x["visit"] for x in rows] != list(range(6)) or any(
        a["counter"] >= b["counter"]
        or a["delivery_clock"]["monotonic_ns"] >= b["delivery_clock"]["monotonic_ns"]
        for a, b in zip(rows, rows[1:], strict=False)
    ):
        raise ValueError("saved fixture must preserve the first six chronological visits")


def pack_capsule(work):
    dst = work / "capsule"
    binary = read(work / "build-arm64.json")["executable"]
    files = (
        (check(Path(binary["path"]), binary["sha256"]), "arm-receiver"),
        (BENCH, "benchmark"),
        (LAUNCHER, "arm_receiver_stream.c"),
        (SOURCE / "SOURCE_LICENSE.md", "detector-license.md"),
        (work / "source/fftw-3.3.10/COPYING", "fftw-COPYING.txt"),
    )
    for source, target in files:
        shutil.copyfile(source, dst / target)
    for name in ("arm-receiver", "benchmark"):
        (dst / name).chmod(0o755)
    members = sorted(p for p in dst.rglob("*") if p.is_file())
    write(
        dst / "SHA256SUMS", "".join(f"{_sha(p)}  {p.relative_to(dst)}\n" for p in members).encode()
    )
    capsule = REPORT / "arm64-detector-capsule.tar.gz"
    with (
        capsule.open("xb") as file,
        gzip.GzipFile(fileobj=file, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for path in [*members, dst / "SHA256SUMS"]:
            info = archive.gettarinfo(str(path), arcname=str(path.relative_to(dst)))
            info.mtime = info.uid = info.gid = 0
            info.uname = info.gname = ""
            with path.open("rb") as stream:
                archive.addfile(info, stream)
    relocated = work / "relocated-capsule"
    relocated.mkdir(exist_ok=False)
    with tarfile.open(capsule, mode="r:gz") as archive:
        archive.extractall(relocated, filter="data")
    subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS"],
        cwd=relocated,
        check=True,
        capture_output=True,
        timeout=12,
    )


def scientific(row):
    return dict(
        top16=row["top16"],
        added_epochs=row["added_epochs"],
        rows=[
            {key: value for key, value in lane.items() if key != "timings_ms"}
            for lane in row["rows"]
        ],
    )


def projection(lane):
    return [
        value for i, x in enumerate(lane["candidates"]) if (value := _from_native(i, x)) is not None
    ]


def ordered(lane):
    return [(c["epoch"], c["coarse_bin"]) for c in lane["candidates"]]


def parity(host, arm):
    first, second = scientific(host), scientific(arm)
    lanes = []
    for source, target in zip(first["rows"], second["rows"], strict=True):
        a, b = projection(source), projection(target)
        pa = [
            (x["candidate_rank"], x["integer_epoch_sample"], x["passed_fractional_margin_gate"])
            for x in a
        ]
        pb = [
            (x["candidate_rank"], x["integer_epoch_sample"], x["passed_fractional_margin_gate"])
            for x in b
        ]
        diffs = [
            (
                abs(x["fractional_tracking_cfo_hz"] - y["fractional_tracking_cfo_hz"]),
                abs(x["fractional_epoch_offset_samples"] - y["fractional_epoch_offset_samples"]),
            )
            for x, y in zip(a, b, strict=False)
            if x["candidate_rank"] == y["candidate_rank"]
        ]
        gate = compare_probes(dict(candidates=a), dict(candidates=b), 10_000_000)
        lanes.append(
            dict(
                ordered_integer_keys=ordered(source) == ordered(target),
                ordered_fractional_gates=pa == pb,
                max_cfo_difference_hz=max((d[0] for d in diffs), default=0),
                max_fractional_difference_samples=max((d[1] for d in diffs), default=0),
                gate=gate,
            )
        )
    return dict(
        scientific_bytes_agree=encoded(first) == encoded(second),
        full_ranks_agree=first["top16"] == second["top16"],
        added_epochs_agree=first["added_epochs"] == second["added_epochs"],
        lanes=lanes,
    )


def execute(work, arch, edge, mode, fixture):
    capsule = work / "relocated-capsule"
    artifact = read(work / f"build-{arch}.json")["executable"]
    if arch == "arm64":
        binary = check(capsule / "arm-receiver", artifact["sha256"])
        prefix = [str(QEMU), "-cpu", "cortex-a53"]
    else:
        binary = check(Path(artifact["path"]), artifact["sha256"])
        prefix = []
    argv = [
        *prefix,
        str(binary),
        mode,
        *(f"templates/{edge}-{part}" for part in PARTS),
        str(REPEATS),
        *(r["file"] for r in fixture),
    ]
    name = f"{arch}-{edge}-{mode}"
    receipt = work / (name + ".time")
    result = subprocess.run(
        ["/usr/bin/time", "-o", str(receipt), "-f", "%e %U %S %M", *argv],
        cwd=capsule,
        capture_output=True,
        check=True,
        timeout=90,
    )
    elapsed, user, system, rss = receipt.read_text().split()
    table = [json.loads(s) for s in result.stdout.splitlines()]
    setup, rows = table[0], table[1:]
    expected = [(r, i) for r in range(REPEATS) for i in range(len(fixture))]
    if [(r["repeat"], r["index"]) for r in rows] != expected or setup["kind"] != "setup":
        raise ValueError("standalone receiver lost a fixture or reordered the stream")
    for a, b in zip(rows[: len(fixture)], rows[len(fixture) :], strict=True):
        if scientific(a) != scientific(b):
            raise ValueError("warm context changed the same signal on its second visit")
    return dict(
        setup=setup,
        visits=rows,
        process_wall_s=float(elapsed),
        process_cpu_s=float(user) + float(system),
        max_process_rss_kib=int(rss),
        argv=argv,
    )


def measure(work, arch):
    if len(os.sched_getaffinity(0)) != 1 or not os.sched_getaffinity(0) <= {0, 1}:
        raise ValueError("pin detector timing to CPU 0 or 1")
    capsule = work / "relocated-capsule"
    data = read(capsule / "fixtures.json")
    for fixtures in data["roster"].values():
        for entry in fixtures:
            check(capsule / entry["file"], entry["iq_sha256"].removeprefix("sha256:"))
    for part, digest in data["templates"].items():
        check(capsule / part, digest)
    results = {
        edge: {
            mode: execute(work, arch, edge, mode, data["roster"][edge])
            for mode in (MODES if edge == "lower" else MODES[::-1])
        }
        for edge in ("lower", "upper")
    }
    save_json(
        work / f"measurement-{arch}.json",
        dict(
            arch=arch,
            affinity=sorted(os.sched_getaffinity(0)),
            qemu_sha256=_sha(QEMU) if arch == "arm64" else None,
            qemu_version=subprocess.check_output([QEMU, "--version"], text=True).splitlines()[0]
            if arch == "arm64"
            else None,
            results=results,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inputs", "pack", "arm64", "host"))
    parser.add_argument("--work", type=local_output, default=WORK)
    args = parser.parse_args()
    if args.action == "inputs":
        inputs(args.work)
    elif args.action == "pack":
        pack_capsule(args.work)
    else:
        measure(args.work, args.action)
