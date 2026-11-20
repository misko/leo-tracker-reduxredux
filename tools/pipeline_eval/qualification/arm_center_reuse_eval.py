"""Time warmed detector triplets and count integer work in independent trace builds."""

import argparse
import gzip
import json
import os
import shutil
import subprocess
from pathlib import Path

from ..__main__ import ROOT, local_output, save_json, write
from ..variants.selective_capture import visit_pairs
from . import arm_center_reuse_build as build
from . import arm_receiver_eval as prior
from .exact_wide_iq_results import detector_rows
from .full_v5_check import _load_case, _sha
from .hinted_glrt_trial import load_selected
from .whole_center_union import WORK as WAVEFORMS

PARENT = build.parent.REPORT
PARENT_FIXTURES = "44ed29f8a3d017ad5f00db60760e3e907af9dc18b5d2b5e6f90cf9517533dae4"
VISITS = tuple(range(12, 18))
EDGES = ("lower", "upper")
DETECTORS = ("stock", "fifth")
ORDERS = (
    ("original", "center", "pair"),
    ("center", "pair", "original"),
    ("pair", "original", "center"),
    ("pair", "center", "original"),
)


def freeze(work):
    previous = build.read(build.parent.check(PARENT / "fixtures.json", PARENT_FIXTURES))
    authority = build.read(
        build.parent.check(prior.PARENT / "prediction-lock.json", prior.PARENT_PIN)
    )
    source = build.parent.WORK / "relocated-capsule"
    folder = work / "fixtures"
    folder.mkdir(exist_ok=False)
    roster, archive = {}, {}
    for edge in EDGES:
        ident = previous["roster"][edge][0]["id"]
        case = _load_case(ident)
        root = folder / edge
        root.mkdir()
        for asset, checksum in previous["templates"].items():
            if not Path(asset).name.startswith(edge + "-"):
                continue
            shutil.copyfile(build.parent.check(source / asset, checksum), root / Path(asset).name)
        archived, raw = {}, {}
        for mode, role in zip(DETECTORS, ("control", "candidate"), strict=True):
            member = f"native/{role}/{ident}.json.gz"
            doc = json.loads(
                gzip.decompress(
                    build.parent.check(
                        prior.PARENT / member, authority["files"][member]
                    ).read_bytes()
                )
            )
            archived[mode] = dict(visit_pairs(doc["source"]["probes"]))
            raw[mode] = detector_rows(WAVEFORMS / ident / role)[0]
        rows = []
        for visit in VISITS:
            stock, fifth = (raw[mode][visit] for mode in DETECTORS)
            if (
                stock["visit"] != visit
                or stock["status"] != "processed"
                or any(stock[k] != fifth[k] for k in stock if k != "probes")
            ):
                raise ValueError("fixed chronological visit lacks two matching admitted parents")
            for mode, data in zip(DETECTORS, (stock, fifth), strict=True):
                if tuple(data["probes"]) != archived[mode][visit]:
                    raise ValueError(
                        "original visit packets do not match the sealed native archive"
                    )
            physical = stock["probes"][0]
            item = dict(
                case=ident,
                visit=visit,
                segment=stock["segment"],
                sequence=stock["sequence"],
                iq_sha256=stock["iq_sha256"],
                counter=stock["sample_start"],
                channel=physical["channel"],
                edge=edge,
                receiver_ids=[0, 1],
                delivery_clock=stock["delivery_clock"],
                manifest_sha256=case["recording"]["segments"][stock["segment"]]["sha256"],
            )
            samples = load_selected(case, item).samples
            name = f"{edge}/{visit}-recorded.ci16"
            write(folder / name, samples.tobytes())
            build.parent.check(folder / name, item["iq_sha256"].removeprefix("sha256:"))
            rows.append(dict(item, kind="recorded", file=name))
        if any(
            a["delivery_clock"]["monotonic_ns"] >= b["delivery_clock"]["monotonic_ns"]
            or a["counter"] >= b["counter"]
            for a, b in zip(rows, rows[1:], strict=False)
        ):
            raise ValueError("physical order of the declared saved fixture changed")
        archive[edge] = {mode: [archived[mode][v] for v in VISITS] for mode in DETECTORS}
        for item in previous["roster"][edge]:
            if item["kind"] != "control":
                continue
            name = f"{edge}/{Path(item['file']).name}"
            shutil.copyfile(
                build.parent.check(source / item["file"], item["iq_sha256"]), folder / name
            )
            rows.append(dict(item, file=name))
        roster[edge] = rows
    path = work / "archived-probes.json"
    save_json(path, archive)
    save_json(
        work / "input-lock.json",
        dict(
            roster=roster,
            prior_native_prediction_sha256=prior.PARENT_PIN,
            prior_capsule_fixture_sha256=PARENT_FIXTURES,
            archived_probes_sha256=_sha(path),
            files={str(p.relative_to(folder)): _sha(p) for p in folder.rglob("*") if p.is_file()},
            source_sha256=_sha(Path(__file__)),
            require_exact=True,
        ),
    )


def call(work, arch, edge, detector, variant, trace, fixture, asset):
    binary = build.parent.check(Path(asset["path"]), asset["sha256"])
    prefix = [str(prior.QEMU), "-cpu", "cortex-a53"] if arch == "arm64" else []
    count = 1 if trace else 2
    argv = [
        *prefix,
        str(binary),
        detector,
        *(f"{edge}/{edge}-{part}" for part in prior.PARTS),
        str(count),
        *(row["file"] for row in fixture),
    ]
    path = work / f"{arch}-{edge}-{detector}-{variant}{'-trace' if trace else ''}.time"
    result = subprocess.run(
        ["/usr/bin/time", "-o", str(path), "-f", "%e %U %S %M", *argv],
        cwd=work / "fixtures",
        capture_output=True,
        check=True,
        timeout=42,
    )
    elapsed, user, system, rss = path.read_text().split()
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    if rows[0]["kind"] != "setup" or [(r["repeat"], r["index"]) for r in rows[1:]] != [
        (r, i) for r in range(count) for i in range(len(fixture))
    ]:
        raise ValueError("fractional variant changed the chronological input inventory")
    return dict(
        setup=rows[0],
        visits=rows[1:],
        cpu_s=float(user) + float(system),
        wall_s=float(elapsed),
        max_process_rss_kib=int(rss),
        argv=argv,
    )


def measure(work, arch):
    affinity = sorted(os.sched_getaffinity(0))
    if len(affinity) != 1 or affinity[0] not in (8, 9):
        raise ValueError("pin matched detector timing to CPU 8 or 9")
    release = build.read(work / f"build-{arch}.json")
    inventory = build.read(work / "input-lock.json")
    build.parent.check(Path(__file__), inventory["source_sha256"])
    for name, digest in release["sources"].items():
        build.parent.check(ROOT / name, digest)
    for name, digest in inventory["files"].items():
        build.parent.check(work / "fixtures" / name, digest)
    records, traces = {}, {}
    for i, edge in enumerate(EDGES):
        records[edge], traces[edge] = {}, {}
        for j, detector in enumerate(DETECTORS):
            for trace, selected in ((False, records), (True, traces)):
                selected[edge][detector] = {}
                for variant in ORDERS[2 * i + j]:
                    asset = release["artifacts"][variant + ("-trace" if trace else "")]
                    value = call(
                        work, arch, edge, detector, variant, trace, inventory["roster"][edge], asset
                    )
                    selected[edge][detector][variant] = value
                    print(
                        arch,
                        edge,
                        detector,
                        variant,
                        "trace" if trace else "timed",
                        value["wall_s"],
                        flush=True,
                    )
    save_json(
        work / f"measured-{arch}.json",
        dict(
            arch=arch,
            cpus=affinity,
            build_sha256=_sha(work / f"build-{arch}.json"),
            input_lock_sha256=_sha(work / "input-lock.json"),
            timed=records,
            trace=traces,
            qemu_sha256=_sha(prior.QEMU) if arch == "arm64" else None,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", *build.ARCH))
    parser.add_argument("--work", type=local_output, default=build.WORK)
    args = parser.parse_args()
    freeze(args.work) if args.action == "freeze" else measure(args.work, args.action)
