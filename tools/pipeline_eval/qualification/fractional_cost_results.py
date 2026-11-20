"""Publish paired fractional detector timing and an offline x86-64 release."""

import argparse
import csv
import gzip
import io
import json
import shutil
import subprocess
import tarfile
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp

import matplotlib
import numpy as np

from ..__main__ import encoded, local_output, save_json, write
from ..variants import differential_pilot
from . import fractional_cost_build as build
from . import fractional_cost_eval as evaluate
from . import native_hotpath_results as native_results
from .fifth_arm import check, science
from .full_v5_check import _sha
from .wide_regional_eval import templates

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


def group_geometry(epoch):
    if not 2 <= epoch <= 13330:
        return None
    count = 0
    for frame in range(16):
        start = round(frame * (10_000_000 / 750.0))
        low, high = epoch - 2 + start + 66 * 44, epoch + 2 + start + 66 * 44
        if low > 200_000:
            break
        if high > 200_000:
            return None
        count += 1
    return count


def grid_work(record):
    rows = record["grid_calls"]
    first, second = record["candidate_counts"]
    if len(rows) != first + second:
        raise ValueError("a candidate skipped the fractional pass in the work audit")
    unique = [tuple(x) for lane in (rows[:first], rows[first:]) for x in {tuple(y) for y in lane}]
    clocks = [group_geometry(epoch) for epoch, _ in unique]
    used = [frames for frames in clocks if frames is not None]
    return dict(
        calls=len(unique),
        grouped=len(used),
        saved_grid_hypotheses=len(used),
        saved_frame_ffts=2 * sum(used),
        saved_final_ffts=4 * len(used),
    )


def collect(work, folder):
    lock = work / "input-lock.json"
    roster = json.loads(lock.read_bytes())["roster"]
    runs, table, checks, memory = {}, [], {}, {}
    for case, core in evaluate.CASES.items():
        data = json.loads((work / f"{case}-results.json").read_bytes())
        selected = [f for f in roster[case] if f["status"] == "valid"]
        edge = selected[0]["edge"]
        if (
            data["core"] != core
            or data["lock_sha256"] != _sha(lock)
            or [row["fixture"] for row in data["rows"]] != selected + roster[edge]
        ):
            raise ValueError("final measurement differs from the input seal")
        runs[case] = data
        checks[case] = {
            mode: dict(
                candidates=0,
                gated=0,
                windows=0,
                within_20ms={role: 0 for role in evaluate.ROLES},
                work={},
            )
            for mode in evaluate.MODES
        }
        memory[case] = {role: data["workers"][role]["peak_kib"] for role in evaluate.ROLES}
        for row in data["rows"]:
            fixture = row["fixture"]
            genuine = fixture["kind"] == "genuine"
            for mode, pairs in row["modes"].items():
                if len(pairs) != 3 or not all(evaluate.validate(pair) for pair in pairs):
                    raise ValueError("final measured pair or schedule failed")
                reference = pairs[0]["typed"]
                gates = reference["gates"]
                if fixture["kind"] in ("noise", "zero") and any(gates):
                    raise ValueError("negative controls admitted a candidate")
                if fixture["kind"] == "strong":
                    target = fixture["target"]
                    if not all(
                        any(
                            abs(h["fractional_tracking_cfo_hz"] - target["cfo_hz"]) < 800
                            and abs(h["integer_epoch_sample"] - target["epoch"]) <= 2
                            for h in lane
                        )
                        for lane in gates
                    ):
                        raise ValueError(
                            "signed control did not recover its expected pilot on both receivers"
                        )
                if genuine:
                    now = checks[case][mode]
                    now["candidates"] += sum(reference["candidate_counts"])
                    now["gated"] += sum(len(lane) for lane in gates)
                    now["windows"] += 1
                    for key, value in grid_work(reference).items():
                        now["work"][key] = now["work"].get(key, 0) + value
                for rep, pair in enumerate(pairs):
                    for role, values in pair.items():
                        memory[case][role] = max(memory[case][role], values["peak_kib"])
                        table.append(
                            dict(
                                case=case,
                                fixture=fixture["name"],
                                kind=fixture["kind"],
                                edge=edge,
                                mode=mode,
                                role=role,
                                rep=rep,
                                **values["timing"],
                            )
                        )
                        if genuine:
                            now["within_20ms"][role] += values["timing"]["decoded_wall_ms"] <= 20
    metrics = sorted(
        set().union(*(r.keys() for r in table))
        - {"case", "fixture", "kind", "edge", "mode", "role", "rep"}
    )
    fields = ["case", "fixture", "kind", "edge", "mode", "role", "rep", *metrics]
    with (folder / "stage.csv").open("w", newline="") as stream:
        output = csv.DictWriter(stream, fieldnames=fields)
        output.writeheader()
        output.writerows(table)
    timing, paired = {}, {}
    for case in ("all", *evaluate.CASES):
        genuine = [
            r for r in table if r["kind"] == "genuine" and (case == "all" or r["case"] == case)
        ]
        timing[case], paired[case] = {}, {}
        for mode in evaluate.MODES:
            data = [
                [row for row in genuine if row["mode"] == mode and row["role"] == role]
                for role in evaluate.ROLES
            ]
            timing[case][mode] = {
                role: {
                    metric: v
                    for metric in metrics
                    if (v := native_results.distribution([r[metric] for r in rows if metric in r]))
                    is not None
                }
                for role, rows in zip(evaluate.ROLES, data, strict=True)
            }
            paired[case][mode] = {
                k: native_results.distribution([b[k] - a[k] for a, b in zip(*data, strict=True)])
                for k in (
                    "fractional_epoch_cpu_ms",
                    "typed_cpu_ms",
                    "decoded_cpu_ms",
                    "decoded_wall_ms",
                )
            }
    summary = dict(checks=checks, peak_kib=memory, timing=timing, paired=paired)
    save_json(folder / "summary.json", summary)
    write(folder / "measurements.json.gz", gzip.compress(encoded(runs), mtime=0))
    return summary, runs


def plot(folder, data):
    fig, ax = plt.subplots(1, 2, figsize=(9.6, 4.6))
    summary = data["timing"]["all"]
    for off, role, color, label in (
        (-0.17, "typed", "#566f86", "Typed detector"),
        (0.17, "grouped", "#0c8175", "Grouped fractional grid"),
    ):
        for index, metric in enumerate(("decoded_wall_ms", "fractional_epoch_cpu_ms")):
            stages = [summary[mode][role][metric] for mode in evaluate.MODES]
            x = np.arange(len(stages)) + off
            ax[index].bar(x, [s["p50"] for s in stages], width=0.31, color=color, label=label)
            ax[index].scatter(
                x,
                [s["p95"] for s in stages],
                s=28,
                marker="D",
                color=color,
                edgecolor="white",
                linewidth=0.5,
                zorder=3,
            )
    ax[0].axhline(20, color="#969696", linestyle="--", linewidth=0.9)
    for target, label in zip(
        ax, ("Complete call (ms wall)", "Fractional refinement (ms CPU)"), strict=True
    ):
        target.set_xticks([0, 1], ["Stock", "Fifth center"])
        target.set_ylabel(label)
        target.spines[["top", "right"]].set_visible(False)
        target.grid(axis="y", alpha=0.18)
    lines, names = ax[0].get_legend_handles_labels()
    fig.legend(lines, names, frameon=False, loc="lower center", ncol=2, bbox_to_anchor=(0.5, 0.025))
    fig.text(
        0.07, 0.95, "Reuse the center of the fractional GLRT grid", fontsize=16, fontweight="bold"
    )
    fig.text(
        0.07,
        0.895,
        "96 held saved-IQ visits. Bars show medians. Diamonds show 95th percentiles.",
        fontsize=10,
    )
    fig.subplots_adjust(left=0.10, top=0.84, bottom=0.20, wspace=0.27)
    fig.savefig(folder / "stage.png", dpi=170)
    fig.savefig(folder / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def capsule(work, folder, runs):
    stage = Path(mkdtemp(dir=work, prefix="package."))
    compiled = work / "build-v2"
    for role in ("grouped", "whole"):
        for item in (compiled / role).iterdir():
            shutil.copyfile(item, stage / item.name)
    shutil.copytree(
        compiled / "source", stage / "source", ignore=shutil.ignore_patterns("__pycache__")
    )
    previous = build.typed.REPORT / "build.json"
    originals = json.loads(previous.read_bytes())["sources"]
    for name in (
        "native_hotpath.h",
        "native_hotpath.c",
        "native_hotpath_rank.h",
        "differential_runtime_fft.c",
    ):
        source = build.typed.VARIANTS / name
        shutil.copyfile(check(source, originals[str(source)]), stage / "source" / name)
    cli = Path(native_results.__file__).with_name("native_hotpath_replay.c")
    shutil.copyfile(cli, stage / "source" / cli.name)
    shutil.copyfile(build.PARENT / "hotpath.exports", stage / "source/hotpath.exports")
    runner = stage / "fractional-detector"
    subprocess.run(
        [
            "/usr/bin/gcc",
            "-std=c11",
            "-O3",
            "-ffp-contract=off",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(stage / "source"),
            str(cli),
            "-L",
            str(stage),
            "-l:libleo-native-hotpath.so",
            "-l:libleo-adaptive-detector.so.1",
            "-Wl,-rpath,$ORIGIN",
            "-o",
            str(runner),
        ],
        check=True,
        timeout=20,
    )
    for edge in ("lower", "upper"):
        exact, control = templates(10_000_000, edge)
        refs = differential_pilot.filters(edge)
        for name, array in (
            ("exact.c16", exact),
            ("control.c16", control),
            ("filters.c8", np.stack([r[0] for r in refs], dtype="<c8")),
            ("energy.f64", np.stack([r[1] for r in refs], dtype="<f8")),
        ):
            (stage / f"{edge}-{name}").write_bytes(array.tobytes())
    shutil.copyfile(work / "upper-strong.ci16", stage / "upper-strong.ci16")
    files = sorted(p for p in stage.rglob("*") if p.is_file())
    sums = stage / "SHA256SUMS"
    sums.write_text("".join(f"{_sha(p)}  {p.relative_to(stage)}\n" for p in files))
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as output:
        for path in (*files, sums):
            spec = tarfile.TarInfo(str(path.relative_to(stage)))
            body = path.read_bytes()
            spec.size, spec.mode = len(body), 0o755 if path == runner else 0o644
            output.addfile(spec, io.BytesIO(body))
    artifact = folder / "fractional-detector-linux-x86_64.tar.gz"
    write(artifact, gzip.compress(stream.getvalue(), mtime=0))
    extracted = Path(mkdtemp(dir=work, prefix="extract."))
    with tarfile.open(artifact) as archive:
        archive.extractall(extracted, filter="data")
    subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS"],
        cwd=extracted,
        check=True,
        capture_output=True,
        timeout=10,
    )
    output = {}
    expected = next(
        r["modes"] for r in runs["DS29-0316"]["rows"] if r["fixture"]["kind"] == "strong"
    )
    with ExitStack() as stack:
        native = evaluate.native.NativeCall(stack, extracted / build.typed.LIBRARY, "upper")
        samples = np.fromfile(extracted / "upper-strong.ci16", dtype="<i2").reshape(200000, 2, 2)
        for mode in evaluate.native.MODES:
            cmd = [
                "./fractional-detector",
                mode,
                "upper-strong.ci16",
                "upper-exact.c16",
                "upper-control.c16",
                "upper-filters.c8",
                "upper-energy.f64",
            ]
            row = json.loads(subprocess.check_output(cmd, cwd=extracted, timeout=10))
            typed, hints, _, _ = native.measure(samples, mode)
            digest = sha256(encoded(science(typed))).hexdigest()
            if (
                hints != row["hints"]
                or science(row["rows"]) != science(typed)
                or digest != expected[mode][0]["grouped"]["sha256"]
            ):
                raise ValueError(
                    "fresh capsule result differs from the genuine controlled timing run"
                )
            output[mode] = dict(sha256=digest, hints=hints)
    save_json(
        folder / "capsule-verification.json",
        dict(
            artifact_sha256=_sha(artifact),
            packaged_hashes_sha256=_sha(sums),
            output=output,
            elf=subprocess.check_output(["readelf", "-h", str(runner)], text=True),
        ),
    )


def publish(work):
    folder = build.REPORT
    summary, paired = collect(work, folder)
    plot(folder, summary)
    receipt = work / "build-v2/build.json"
    origin = json.loads(receipt.read_bytes())
    for name, digest in origin["closure"].items():
        check(Path(name), digest)
    shutil.copyfile(receipt, folder / "build.json")
    candidate = check(
        work / "build-v2/detector/build-receipt.json", origin["candidate_receipt_sha256"]
    )
    shutil.copyfile(candidate, folder / "detector-build.json")
    capsule(work, folder, paired)
    files = (
        *json.loads((folder / "whole-feature-gate.json").read_bytes())["files"],
        "whole-feature-gate.json",
        "build.json",
        "detector-build.json",
        "summary.json",
        "measurements.json.gz",
        "stage.csv",
        "stage.png",
        "stage.pdf",
        "fractional-detector-linux-x86_64.tar.gz",
        "capsule-verification.json",
    )
    save_json(
        folder / "result-lock.json",
        dict(files={n: _sha(folder / n) for n in files}, publisher_sha256=_sha(Path(__file__))),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=local_output)
    publish(p.parse_args().work)
