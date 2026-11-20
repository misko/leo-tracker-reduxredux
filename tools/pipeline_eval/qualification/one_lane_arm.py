"""Build and measure a one-physical-receiver port on two target ABIs."""

import argparse
import gzip
import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, local_output, save_json, write
from ..variants import iq_stream, one_lane_strided
from ..variants.selective_capture import visit_pairs
from ..variants.staggered_native import RfStagger
from . import arm_center_reuse_build as reuse
from . import arm_center_reuse_eval as panel
from . import arm_receiver_eval as receiver
from . import hinted_glrt_trial as fixtures
from .full_v5_check import _load_case, _sha

REPORT = reuse.REPORT.parents[1] / "pilot-influence/one-lane-arm"
WORK = reuse.WORK.with_name("one-lane-arm")
ARCHES = ("host", "arm64")
MODES = ("dual", "packed", "strided")
ORDERS = (MODES, ("strided", "packed", "dual"))
RUNNER = Path(__file__).with_name("one_lane_arm_stream.c")
PREVIOUS_LOCK = "5c4bfa088fd18927a97a0635119d93d2b7dbe6b1fdeb3949330b36a3906b633e"
WIDE_RUNTIME = Path("/var/tmp/leo-receiver-choice-fresh-20261119/runtime/wide-stock.so")
WIDE_PIN = "db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66"
BOARD = reuse.parent.REPORT / "board-access.json"
HARD_PREFIX_BYTES = 96 * 1_600_000
DWELL = "kernel/private/dwell_input.h"
NATIVE = "native_glrt.c"
checked = reuse.parent.check
read = reuse.read


def rf_key(probe):
    actual = probe["actual_rf_hz"]
    if float(actual).is_integer() and actual > 0:
        return int(actual)
    raise ValueError("missing integer recorded RF key")


def annotated(stock, fifth):
    """Freeze the physical lane using the entire actual prefix, before looking for hard visits."""
    schedule = RfStagger()
    for a, b in zip(stock[:96], fifth[:96], strict=True):
        if any(a[k] != b[k] for k in a if k != "probes"):
            raise ValueError("the archived detector choices changed the original physical visit")
        valid = a["status"] == "processed"
        rf = rf_key(a["probes"][0]) if valid else None
        lane = schedule.reserve(rf, valid=valid)
        if valid:
            if [p["receiver_id"] for p in a["probes"]] != [0, 1] or any(
                rf_key(p) != rf for p in a["probes"]
            ):
                raise ValueError("physical lane ordering or RF disagrees")
            yield a, b, lane, rf


def positive(probe):
    return any(c["passed_fractional_margin_gate"] for c in probe["candidates"])


def native_lazy(ident, role, authority):
    name = f"native/{role}/{ident}.json.gz"
    return dict(
        visit_pairs(
            json.loads(
                gzip.decompress(checked(receiver.PARENT / name, authority[name]).read_bytes())
            )["source"]["probes"]
        )
    )


def freeze(work):
    base = read(checked(reuse.REPORT / "qualification-lock.json", PREVIOUS_LOCK))["files"]
    inventory = read(checked(reuse.REPORT / "input-lock.json", base["input-lock.json"]))
    authority = read(checked(receiver.PARENT / "prediction-lock.json", receiver.PARENT_PIN))[
        "files"
    ]
    checked(WIDE_RUNTIME, WIDE_PIN)
    folder = work / "fixtures"
    folder.mkdir(parents=True)
    roster, expected = {}, {}
    for edge in panel.EDGES:
        (folder / edge).mkdir()
        originals = inventory["roster"][edge]
        name = originals[0]["case"]
        case = _load_case(name)
        stock, fifth = [
            panel.detector_rows(panel.WAVEFORMS / name / role)[0]
            for role in ("control", "candidate")
        ]
        archives = [native_lazy(name, role, authority) for role in ("control", "candidate")]
        rows, truth, hard = [], {}, set()
        prior = {item["visit"]: item for item in originals if item["kind"] == "recorded"}
        for a, b, lane, rf in annotated(stock, fifth):
            v = a["visit"]
            wanted = (
                v not in prior
                and lane not in hard
                and not positive(a["probes"][lane])
                and positive(b["probes"][lane])
            )
            if not wanted and v not in prior:
                continue
            if any(tuple(d["probes"]) != past[v] for d, past in zip((a, b), archives, strict=True)):
                raise ValueError("stress or held visit did not match the published archive")
            filename = f"{edge}/{v}-recorded.ci16"
            entry = dict(
                case=name,
                visit=v,
                edge=edge,
                lane=lane,
                rf_hz=rf,
                channel=a["probes"][0]["channel"],
                receiver_ids=[0, 1],
                kind="hard" if wanted else "held",
                file=filename,
                segment=a["segment"],
                sequence=a["sequence"],
                iq_sha256=a["iq_sha256"],
                counter=a["sample_start"],
                delivery_clock=a["delivery_clock"],
                manifest_sha256=case["recording"]["segments"][a["segment"]]["sha256"],
            )
            if wanted:
                hard.add(lane)
                with (
                    patch.object(fixtures, "PREFIX_MAX", HARD_PREFIX_BYTES),
                    patch.object(iq_stream, "MAX_DECODE_BYTES", HARD_PREFIX_BYTES),
                ):
                    data = fixtures.load_selected(case, entry).samples.tobytes()
                write(folder / filename, data)
            else:
                if any(
                    entry[k] != prior[v][k]
                    for k in ("counter", "delivery_clock", "iq_sha256", "manifest_sha256")
                ):
                    raise ValueError("the chronological held fixture differs from its prior lock")
                shutil.copyfile(
                    checked(reuse.WORK / "fixtures" / filename, inventory["files"][filename]),
                    folder / filename,
                )
            checked(folder / filename, a["iq_sha256"].removeprefix("sha256:"))
            rows.append(entry)
            truth[filename] = a["probes"]
        if {r["visit"] for r in rows if r["kind"] == "held"} != set(panel.VISITS):
            raise ValueError("a preregistered held visit was missing")
        first = next(r for r in rows if r["kind"] == "held")
        unchanged = np.fromfile(folder / first["file"], dtype="<i2").reshape(-1, 2, 2)
        unchanged[:, 1 - first["lane"], :] = 0
        witness = f"{edge}/partner-zero.ci16"
        write(folder / witness, unchanged.tobytes())
        rows.append(
            dict(
                first,
                file=witness,
                kind="partner-zero",
                parent=first["file"],
                iq_sha256="sha256:" + _sha(folder / witness),
            )
        )
        for item in originals:
            if item["kind"] == "control":
                filename = item["file"]
                shutil.copyfile(
                    checked(reuse.WORK / "fixtures" / filename, inventory["files"][filename]),
                    folder / filename,
                )
                rows.append(dict(item, lane=len(rows) % 2))
        for filename in inventory["files"]:
            if filename.startswith(f"{edge}/{edge}-"):
                shutil.copyfile(
                    checked(reuse.WORK / "fixtures" / filename, inventory["files"][filename]),
                    folder / filename,
                )
        roster[edge], expected[edge] = rows, truth
    path = work / "expected.json"
    save_json(path, expected)
    save_json(
        work / "input-lock.json",
        dict(
            files={
                str(p.relative_to(folder)): _sha(p)
                for p in sorted(folder.rglob("*"))
                if p.is_file()
            },
            roster=roster,
            expected_sha256=_sha(path),
            previous_lock_sha256=PREVIOUS_LOCK,
            stock_sha256=WIDE_PIN,
            source_sha256=_sha(Path(__file__)),
            protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
            hard_prefix_bytes=HARD_PREFIX_BYTES,
            archive_prediction_lock_sha256=receiver.PARENT_PIN,
            board_access_sha256=_sha(BOARD),
        ),
    )


def build(work, arch):
    prior_path = checked(reuse.parent.REPORT / f"build-{arch}.json", reuse.PARENT_BUILD[arch])
    prior = read(prior_path)
    for name, digest in prior["sources"].items():
        checked(ROOT / name, digest)
    for name, digest in prior["detector_source_manifest"].items():
        checked(reuse.parent.SOURCE / name, digest)
    for name, digest in prior["fftw_libraries"].items():
        checked(Path(name), digest)
    checked(Path(prior["compiler"]["path"]), prior["compiler"]["sha256"])
    folder = work / arch
    clone = folder / "source"
    shutil.copytree(reuse.parent.SOURCE, clone, ignore=shutil.ignore_patterns("__pycache__"))
    for relative, transform in ((NATIVE, one_lane_strided.kernel), (DWELL, one_lane_strided.dwell)):
        path = clone / relative
        path.write_text(transform(path.read_text()))
    common, link = prior["commands"][:-1], prior["commands"][-1]
    commands, changed, other = [], {}, {}
    (work / "compiler-temp").mkdir(exist_ok=True)
    for cmd in common:
        filename, obj = Path(cmd[cmd.index("-c") + 1]), cmd[-1]
        if filename == reuse.parent.SOURCE / NATIVE:
            updated = [v.replace(str(reuse.parent.SOURCE), str(clone)) for v in cmd]
        elif filename == reuse.parent.LAUNCHER:
            updated = [str(RUNNER) if v == str(filename) else v for v in cmd]
        else:
            other[obj] = _sha(Path(obj))
            continue
        updated[-1] = str(folder / Path(obj).name)
        reuse.parent.command(work, updated, timeout=45)
        changed[obj] = updated[-1]
        commands.append(updated)
    binary = folder / "one-lane-arm"
    linked = [changed.get(v, v) for v in link]
    linked[-1] = str(binary)
    reuse.parent.command(work, linked, timeout=65)
    commands.append(linked)
    sections = reuse.parent.command(work, ["/usr/bin/size", "-A", str(binary)])
    delta = {
        n: _sha(clone / n)
        for n, h in prior["detector_source_manifest"].items()
        if _sha(clone / n) != h
    }
    if set(delta) != {DWELL, NATIVE}:
        raise ValueError("one-lane build edited extra source files")
    materials = [RUNNER, Path(__file__), Path(one_lane_strided.__file__), REPORT / "PROTOCOL.md"]
    save_json(
        work / f"build-{arch}.json",
        dict(
            parent_sha256=_sha(prior_path),
            unchanged_objects=other,
            source_delta=delta,
            sources={str(p.relative_to(ROOT)): _sha(p) for p in materials},
            commands=commands,
            binary=str(binary),
            sha256=_sha(binary),
            binary_bytes=binary.stat().st_size,
            sections={
                fields[0]: int(fields[1])
                for line in sections.splitlines()
                if (fields := line.split()) and fields[0] in {".text", ".rodata", ".data", ".bss"}
            },
            changed_project_bytes=sum(p.stat().st_size for p in materials[:3]),
            measured_project_code_lines=sum(len(p.read_text().splitlines()) for p in materials[:3]),
        ),
    )


def measure(work, arch):
    inventory = read(work / "input-lock.json")
    checked(Path(__file__), inventory["source_sha256"])
    checked(REPORT / "PROTOCOL.md", inventory["protocol_sha256"])
    release = read(work / f"build-{arch}.json")
    for name, digest in release["sources"].items():
        checked(ROOT / name, digest)
    for name, digest in inventory["files"].items():
        checked(work / "fixtures" / name, digest)
    binary = checked(Path(release["binary"]), release["sha256"])
    result = {}
    for edge, order in zip(panel.EDGES, ORDERS, strict=True):
        roster = inventory["roster"][edge]
        files = [arg for r in roster for arg in (str(r["lane"]), r["file"])]
        result[edge] = {}
        for mode in order:
            estimate = work / f"{arch}-{edge}-{mode}.time"
            prefix = [str(receiver.QEMU), "-cpu", "cortex-a53"] if arch == "arm64" else []
            args = [
                *prefix,
                str(binary),
                mode,
                f"{edge}/{edge}-exact.c16",
                f"{edge}/{edge}-control.c16",
                *files,
            ]
            executed = subprocess.run(
                ["/usr/bin/time", "-o", str(estimate), "-f", "%e %U %S %M", *args],
                cwd=work / "fixtures",
                capture_output=True,
                check=True,
                timeout=42,
            )
            wall, user, system, rss = estimate.read_text().split()
            setup, *rows = map(json.loads, executed.stdout.splitlines())
            if [(r["repeat"], r["index"], r["selected"]) for r in rows] != [
                (t, i, r["lane"]) for t in range(2) for i, r in enumerate(roster)
            ]:
                raise ValueError("chronological roster or lane binding changed")
            result[edge][mode] = dict(
                setup=setup,
                rows=rows,
                wall_s=float(wall),
                cpu_s=float(user) + float(system),
                peak_rss_kib=int(rss),
                argv=args,
            )
            print(arch, edge, mode, wall, rss, flush=True)
    save_json(
        work / f"measurement-{arch}.json",
        dict(
            arch=arch,
            cpu=7,
            results=result,
            input_sha256=_sha(work / "input-lock.json"),
            build_sha256=_sha(work / f"build-{arch}.json"),
            qemu_sha256=_sha(receiver.QEMU) if arch == "arm64" else None,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", *ARCHES))
    parser.add_argument("--work", type=local_output, default=WORK)
    args = parser.parse_args()
    if os.sched_getaffinity(0) != {7}:
        raise SystemExit("run on pinned CPU 7")
    if args.action == "freeze":
        freeze(args.work)
    else:
        build(args.work, args.action)
        measure(args.work, args.action)
