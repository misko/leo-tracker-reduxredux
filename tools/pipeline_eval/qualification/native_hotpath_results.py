"""Authenticate warm detector timings and package the typed offline release."""

import argparse
import csv
import gzip
import io
import json
import shutil
import subprocess
import tarfile
from contextlib import ExitStack
from pathlib import Path
from tempfile import mkdtemp

import matplotlib
import numpy as np

from ..__main__ import encoded, local_output, save_json, write
from ..variants import differential_pilot
from . import native_hotpath_build as build
from . import native_hotpath_eval as evaluate
from .fifth_arm import check, science
from .full_v5_check import _sha
from .wide_regional_eval import templates

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

NAMES = dict(
    legacy="Released ctypes", reference="Same typed API, original kernels", hotpath="Typed hot path"
)


def distribution(values):
    if not values:
        return None
    p50, p95 = np.percentile(values, [50, 95])
    return dict(p50=float(p50), p95=float(p95), n=len(values))


def reduce_data(work, folder):
    lock_path = work / "input-lock.json"
    lock = json.loads(lock_path.read_bytes())
    evidence, timings, checks, memory = {}, [], {}, {}
    for ident, cpu in evaluate.CASES.items():
        result = json.loads((work / f"{ident}-measured.json").read_bytes())
        if result["source_lock_sha256"] != _sha(lock_path) or result["core"] != cpu:
            raise ValueError("measured worker is outside the locked input or affinity")
        genuine = [f for f in lock["roster"][ident] if f["status"] == "valid"]
        expected = genuine + lock["roster"][genuine[0]["edge"]]
        if [row["fixture"] for row in result["rows"]] != expected:
            raise ValueError("measured and prescribed contiguous rosters differ")
        evidence[ident] = result
        memory[ident] = {
            role: dict(initial=entry["memory"], setup=entry["setup"], max=entry["memory"])
            for role, entry in result["start"].items()
        }
        for row in result["rows"]:
            fixture = row["fixture"]
            controls = fixture["kind"] != "genuine"
            cases = checks.setdefault(ident, {})
            for mode, repeats in row["modes"].items():
                if len(repeats) != 3 or not all(evaluate.comparable(r) for r in repeats):
                    raise ValueError("science mismatch or wrong repetition denominator")
                legacy = repeats[0]["legacy"]
                positives = sum(len(a) for a in legacy["positives"])
                if controls:
                    current = cases.setdefault(fixture["kind"], {})
                    if fixture["kind"] in ("noise", "zero") and positives:
                        raise ValueError("negative IQ control produced a gated candidate")
                    if fixture["kind"] == "strong":
                        plant = fixture["target"]
                        for lane in legacy["positives"]:
                            if not any(
                                abs(candidate["fractional_tracking_cfo_hz"] - plant["cfo_hz"]) < 800
                                and abs(candidate["integer_epoch_sample"] - plant["epoch"]) <= 2
                                for candidate in lane
                            ):
                                raise ValueError(
                                    "signed edge control lost the known physical pilot"
                                )
                else:
                    current = cases.setdefault("genuine", {}).setdefault(
                        mode,
                        dict(
                            windows=0,
                            candidates=0,
                            gated=0,
                            paired_runs=0,
                            retained_20ms={},
                        ),
                    )
                if controls:
                    current[mode] = dict(gated=positives, hints=legacy["hints"])
                else:
                    current["windows"] += 1
                    current["candidates"] += sum(legacy["candidate_count"])
                    current["gated"] += positives
                    current["paired_runs"] += len(repeats)
                for rep, measured in enumerate(repeats):
                    for role, record in measured.items():
                        binding = dict(
                            case=ident,
                            fixture=fixture["name"],
                            kind=fixture["kind"],
                            edge=fixture["edge"],
                            mode=mode,
                            rep=rep,
                            role=role,
                        )
                        timings.append(
                            dict(**binding, json_bytes=record["json_bytes"], **record["timings"])
                        )
                        mem = memory[ident][role]
                        mem["max"] = max(mem["max"], record["memory"])
                        if not controls:
                            deadline = current["retained_20ms"]
                            deadline[role] = deadline.get(role, 0) + (
                                record["timings"]["decoded_wall_ms"] <= 20.0
                            )
    domains = {
        ("all", role, mode): [
            row
            for row in timings
            if row["kind"] == "genuine" and row["role"] == role and row["mode"] == mode
        ]
        for role in evaluate.ROLES
        for mode in evaluate.TIMED_MODES
    }
    for ident in evaluate.CASES:
        domains.update(
            {
                (ident, role, mode): [r for r in rows if r["case"] == ident]
                for (_, role, mode), rows in tuple(domains.items())
                if _ == "all"
            }
        )
    timings_summary = {}
    metrics = sorted(
        set().union(*(r.keys() for r in timings))
        - {"case", "fixture", "kind", "edge", "mode", "rep", "role"}
    )
    for (case, role, mode), rows in domains.items():
        timings_summary.setdefault(case, {}).setdefault(mode, {})[role] = {
            metric: stat
            for metric in metrics
            if (stat := distribution([r[metric] for r in rows if metric in r])) is not None
        }
    pairs = {}
    for case in ("all", *evaluate.CASES):
        for mode in evaluate.TIMED_MODES:
            right = domains[(case, "hotpath", mode)]
            entries = pairs.setdefault(case, {}).setdefault(mode, {})
            for prior in ("legacy", "reference"):
                left = domains[(case, prior, mode)]
                entries[prior] = {
                    key: distribution([b[key] - a[key] for a, b in zip(left, right, strict=True)])
                    for key in ("decoded_cpu_ms", "decoded_wall_ms", "proposal_fold_cpu_ms")
                }
    fields = ["case", "fixture", "kind", "edge", "mode", "rep", "role", *metrics]
    with (folder / "stage.csv").open("w", newline="") as stream:
        output = csv.DictWriter(stream, fieldnames=fields)
        output.writeheader()
        output.writerows(timings)
    write(folder / "measurements.json.gz", gzip.compress(encoded(evidence), mtime=0))
    document = dict(checks=checks, timing=timings_summary, paired_delta=pairs, memory_kib=memory)
    save_json(folder / "summary.json", document)
    return document


def figure(folder, value):
    fig, axs = plt.subplots(1, 2, figsize=(10.3, 4.65), gridspec_kw={"width_ratios": [1.35, 1]})
    times = value["timing"]["all"]
    for i, (role, color) in enumerate(
        zip(evaluate.ROLES, ("#597081", "#a09277", "#087d71"), strict=True)
    ):
        span = (i - 1) * 0.23
        ax = axs[0]
        m = [times[mode][role]["decoded_wall_ms"] for mode in evaluate.TIMED_MODES]
        x = np.arange(len(m)) + span
        ax.bar(x, [a["p50"] for a in m], width=0.21, color=color, label=NAMES[role])
        ax.scatter(
            x,
            [a["p95"] for a in m],
            color=color,
            marker="D",
            zorder=3,
            edgecolor="white",
            linewidth=0.45,
        )
        ax = axs[1]
        stage = ("proposal_fold_cpu_ms", "rank_cpu_ms")
        x = np.arange(len(stage)) + span
        ax.bar(x, [times["fifth"][role][a]["p50"] for a in stage], width=0.21, color=color)
    axs[0].set_xticks((0, 1), ("Stock", "Fifth center"))
    axs[0].set_ylabel("Input through decoded rows (ms wall)")
    axs[0].axhline(20, ls="--", lw=0.8, color="#8a8a8a")
    axs[1].set_xticks((0, 1), ("Ordinary lag fold", "FFTW scout rank"))
    axs[1].set_ylabel("Median CPU (ms), fifth-center runs")
    for ax in axs:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.2)
    handles, labels = axs[0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.015), frameon=False
    )
    fig.text(
        0.06,
        0.96,
        "A typed native detector with faster timing proposals",
        fontsize=16,
        fontweight="bold",
    )
    fig.text(
        0.06,
        0.906,
        "96 contiguous saved-IQ visits. Bars show medians. Diamonds show 95th percentiles.",
        fontsize=10,
    )
    fig.subplots_adjust(left=0.09, right=0.97, bottom=0.19, top=0.85, wspace=0.33)
    fig.savefig(folder / "stage.png", dpi=170)
    fig.savefig(folder / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def capsule(work, folder):
    probe = Path(mkdtemp(prefix="capsule.", dir=work))
    release_path = work / "build-v1"
    for name in (build.LIBRARY, build.DETECTOR):
        shutil.copyfile(release_path / "hotpath" / name, probe / name)
    shutil.copytree(
        release_path / "source", probe / "source", ignore=shutil.ignore_patterns("__pycache__")
    )
    for name in (
        "native_hotpath.c",
        "native_hotpath.h",
        "native_hotpath_rank.h",
        "differential_runtime_fft.c",
    ):
        shutil.copyfile(build.VARIANTS / name, probe / "source" / name)
    replay = Path(__file__).with_name("native_hotpath_replay.c")
    shutil.copyfile(replay, probe / "source" / replay.name)
    shutil.copyfile(release_path / "hotpath.exports", probe / "source/hotpath.exports")
    program = probe / "native-hotpath"
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
            str(probe / "source"),
            str(replay),
            "-L",
            str(probe),
            "-l:libleo-native-hotpath.so",
            "-l:libleo-adaptive-detector.so.1",
            "-Wl,-rpath,$ORIGIN",
            "-o",
            str(program),
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
            (probe / f"{edge}-{name}").write_bytes(array.tobytes())
    shutil.copyfile(work / "upper-strong.ci16", probe / "upper-strong.ci16")
    files = sorted(path for path in probe.rglob("*") if path.is_file())
    checksum = probe / "SHA256SUMS"
    checksum.write_text("".join(f"{_sha(path)}  {path.relative_to(probe)}\n" for path in files))
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w", format=tarfile.USTAR_FORMAT) as output:
        for path in (*files, checksum):
            spec = tarfile.TarInfo(str(path.relative_to(probe)))
            body = path.read_bytes()
            spec.size, spec.mode = len(body), 0o755 if path == program else 0o644
            output.addfile(spec, io.BytesIO(body))
    artifact = folder / "native-hotpath-linux-x86_64.tar.gz"
    write(artifact, gzip.compress(data.getvalue(), mtime=0))
    fresh = Path(mkdtemp(prefix="unpacked.", dir=work))
    with tarfile.open(artifact) as package:
        package.extractall(fresh, filter="data")
    subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS"], check=True, cwd=fresh, capture_output=True, timeout=15
    )
    signed_upper = next(
        r
        for r in json.loads((work / "DS29-0316-measured.json").read_bytes())["rows"]
        if r["fixture"]["kind"] == "strong"
    )
    results = {}
    with ExitStack() as stack:
        native = evaluate.NativeCall(stack, fresh / build.LIBRARY, "upper")
        sample = np.fromfile(fresh / "upper-strong.ci16", dtype="<i2").reshape(200000, 2, 2)
        for mode in evaluate.MODES:
            result = subprocess.run(
                [
                    "./native-hotpath",
                    mode,
                    "upper-strong.ci16",
                    "upper-exact.c16",
                    "upper-control.c16",
                    "upper-filters.c8",
                    "upper-energy.f64",
                ],
                check=True,
                cwd=fresh,
                capture_output=True,
                timeout=10,
            )
            row = json.loads(result.stdout)
            typed, hints, _, _ = native.measure(sample, mode)
            expected = signed_upper["modes"][mode][0]["hotpath"]
            if (
                row["hints"] != hints
                or hints != expected["hints"]
                or science(row["rows"]) != science(typed)
                or _sha_bytes(science(typed)) != expected["payload_sha256"]
            ):
                raise ValueError(
                    "packaged offline executable did not reproduce its paired C receipt"
                )
            results[mode] = dict(hints=hints, payload_sha256=expected["payload_sha256"])
    save_json(
        folder / "capsule-verification.json",
        dict(
            archive_sha256=_sha(artifact),
            modes=results,
            files_sha256=_sha(checksum),
            elf=subprocess.check_output(["readelf", "-h", str(program)], text=True),
            dynamic=subprocess.check_output(["readelf", "-d", str(program)], text=True),
        ),
    )


def _sha_bytes(value):
    from hashlib import sha256

    return sha256(encoded(value)).hexdigest()


def publish(work, folder):
    release = check(
        work / "build-v1/build.json",
        json.loads((work / "input-lock.json").read_bytes())["build_sha256"],
    )
    receipt = json.loads(release.read_bytes())
    for name, digest in receipt["sources"].items():
        check(Path(name), digest)
    value = reduce_data(work, folder)
    figure(folder, value)
    for origin, name in (
        (work / "input-lock.json", "source-lock.json"),
        (release, "build.json"),
        (
            check(
                work / "build-v1/detector/build-receipt.json", receipt["candidate_receipt_sha256"]
            ),
            "detector-build.json",
        ),
    ):
        shutil.copyfile(origin, folder / name)
    capsule(work, folder)
    artifacts = (
        "source-lock.json",
        "build.json",
        "detector-build.json",
        "stage.png",
        "stage.pdf",
        "stage.csv",
        "summary.json",
        "measurements.json.gz",
        "capsule-verification.json",
        "native-hotpath-linux-x86_64.tar.gz",
    )
    save_json(
        folder / "result-lock.json",
        dict(
            files={name: _sha(folder / name) for name in artifacts},
            source_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    args = parser.parse_args()
    publish(args.work, build.REPORT)
