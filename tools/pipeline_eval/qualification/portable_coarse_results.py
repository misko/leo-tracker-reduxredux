"""Seal and chart standalone original raw-to-fractional detector evidence."""

import argparse
import gzip
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

from ..__main__ import local_output, save_json, write
from . import portable_coarse_trial as trial
from .capture_runtime import checked, read
from .fine_search_results import spread
from .full_v5_check import _sha
from .prefix_figures import csv_file

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


def held_rows(target, case, record):
    for rep, timing in enumerate(record["timing"]):
        res = timing["resources"]
        prefix = dict(target=target, case=case, repetition=rep)
        yield dict(
            prefix,
            stage="initialize",
            visit="",
            lane="",
            anchors="",
            retry="",
            cpu_ms=res["setup_cpu_ns"] / 1e6,
            wall_ms=res["setup_wall_ns"] / 1e6,
        )
        visits = defaultdict(list)
        for group in timing["clocks"]:
            visits[group["visit"]].append(group)
            for stage in ("coarse", "verify"):
                yield dict(
                    prefix,
                    stage=stage,
                    visit=group["visit"],
                    lane=group["lane"],
                    anchors=group["anchors"],
                    retry=int(group["anchors"] == 22),
                    cpu_ms=group[f"{stage}_cpu_ns"] / 1e6,
                    wall_ms=group[f"{stage}_wall_ns"] / 1e6,
                )
        for visit, groups in visits.items():
            yield dict(
                prefix,
                stage="raw_to_fractional",
                visit=visit,
                lane="both",
                anchors="",
                retry=int(len(groups) > 2),
                cpu_ms=sum(g["coarse_cpu_ns"] + g["verify_cpu_ns"] for g in groups) / 1e6,
                wall_ms=sum(g["coarse_wall_ns"] + g["verify_wall_ns"] for g in groups) / 1e6,
            )


def rows_summary(rows, stage, target, anchors=None, retry=None):
    return {
        clock: spread(
            [
                r[clock]
                for r in rows
                if r["target"] == target
                and r["stage"] == stage
                and (anchors is None or r["anchors"] == anchors)
                and (retry is None or r["retry"] == retry)
            ]
        )
        for clock in ("cpu_ms", "wall_ms")
    }


def figure(folder, stats):
    fig, axes = plt.subplots(1, 2, figsize=(9.7, 4.0), layout="constrained")
    labels = (
        (
            "Setup and per-lane scoring",
            (
                ("Cold setup", "setup"),
                ("12-anchor coarse", "primary"),
                ("22-anchor coarse", "retry"),
                ("Fine CFO and GLRT", "verify"),
            ),
        ),
        (
            "Dual raw visit to fractional gates",
            (
                ("Primary only", "complete_primary"),
                ("With partner retry", "complete_retry"),
            ),
        ),
    )
    for ax, (title, panel) in zip(axes, labels, strict=True):
        for idx, (_, role) in enumerate(panel):
            r = stats[role]["cpu_ms"]
            mid = r["median"]
            ax.errorbar(
                mid,
                idx,
                xerr=[[mid - r["min"]], [r["max"] - mid]],
                fmt="o",
                capsize=4,
                color="#087a70",
            )
        ax.set_yticks(range(len(panel)), [label for label, _ in panel])
        ax.invert_yaxis()
        ax.set(xlabel="Native x86 process CPU (ms)", title=title)
        ax.grid(axis="x", color="#dee4ea")
        ax.set_axisbelow(True)
    fig.suptitle("Standalone original detector on saved dual CI16", fontsize=14)
    fig.savefig(folder / "stage.png", dpi=160)
    fig.savefig(folder / "stage.pdf", metadata={"CreationDate": None})
    plt.close(fig)


def report(work, folder=trial.REPORT):
    lock_path = work / "input-lock.json"
    lock = read(lock_path)
    for path, digest in lock["sources"].items():
        checked(Path(path), digest)
    files = ["PROTOCOL.md"]

    def copy(path, name=None):
        relative = name or path.name
        write(folder / relative, path.read_bytes())
        files.append(relative)

    copy(lock_path)
    compiled, rows, ledger, counts = {}, [], {}, {}
    deltas = {}
    for target in trial.TARGETS:
        binary = checked(work / target / "portable-coarse", lock["builds"][target]["sha256"])
        report_name = f"{target}-portable-coarse.gz"
        write(folder / report_name, gzip.compress(binary.read_bytes(), mtime=0))
        files.append(report_name)
        sections = subprocess.check_output(["size", binary], text=True).splitlines()[1].split()
        compiled[target] = dict(
            lock["builds"][target],
            text_bytes=int(sections[0]),
            data_bytes=int(sections[1]),
            bss_bytes=int(sections[2]),
            archive=report_name,
        )
        source = work / f"{target}.json"
        copy(source)
        evidence = read(source)
        counts[target] = Counter()
        ledger[target] = {}
        deltas[target] = {}
        for case, item in evidence.items():
            verify = item["verification"]
            ledger[target][case] = dict(seeds=item["seeds"], retries=item["retries"], **verify)
            counts[target].update(verify["counts"])
            counts[target].update(seeds=item["seeds"], retries=item["retries"])
            for field, delta in verify["maximum_errors"].items():
                deltas[target][field] = max(deltas[target].get(field, 0), delta)
            rows.extend(held_rows(target, case, item))
    development = {}
    for case in lock["cases"]:
        source = work / f"{case}-development.json"
        copy(source)
        development[case] = read(source)
    direct_resources = work / "native-direct-resources.json"
    copy(direct_resources)
    stats = dict(
        setup=rows_summary(rows, "initialize", "x86"),
        primary=rows_summary(rows, "coarse", "x86", anchors=12),
        retry=rows_summary(rows, "coarse", "x86", anchors=22),
        verify=rows_summary(rows, "verify", "x86"),
        complete_primary=rows_summary(rows, "raw_to_fractional", "x86", retry=0),
        complete_retry=rows_summary(rows, "raw_to_fractional", "x86", retry=1),
    )
    save_json(
        folder / "summary.json",
        dict(
            native_timing=stats,
            native_direct_resources=read(direct_resources),
            native_source_payload={
                path.name: dict(lines=len(path.read_text().splitlines()), bytes=path.stat().st_size)
                for path in (
                    trial.CLI,
                    trial.portable_coarse.SOURCE,
                    trial.portable_coarse.HEADER,
                    trial.portable_coarse.QIN,
                )
            },
            cross_diagnostic_only={
                target: rows_summary(rows, "raw_to_fractional", target)
                for target in trial.TARGETS[1:]
            },
            outputs=ledger,
            counts={k: dict(v) for k, v in counts.items()},
            numeric_maximums=deltas,
            binary=compiled,
            development={
                case: dict(
                    visit=item["visit"],
                    template_errors=item["template_max_errors"],
                    grid_error=max(row["comparison"]["max_abs"] for row in item["rows"]),
                    grids=len(item["rows"]),
                    ordered=all(r["comparison"]["ordered"] for r in item["rows"]),
                )
                for case, item in development.items()
            },
        ),
    )
    csv_file(folder / "stage.csv", rows)
    figure(folder, stats)
    save_json(
        folder / "stage-figure.json",
        dict(
            version=1,
            id="portable-coarse-original",
            title="Standalone raw CI16 through original fractional detector",
            sample="Six native dual held visits and four short ARM-emulated dual visits",
            boundary="Raw saved IQ and capture geometry through gate-driven acquisition and GLRT",
            note="Chart timings are native x86. The timing CSV includes ARM emulation diagnostics.",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="qualification-lock.json",
        ),
    )
    files += ["summary.json", "stage.csv", "stage.png", "stage.pdf", "stage-figure.json"]
    save_json(
        folder / "qualification-lock.json",
        dict(
            files={name: _sha(folder / name) for name in files},
            report_generator_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=local_output)
    report(p.parse_args().work)
