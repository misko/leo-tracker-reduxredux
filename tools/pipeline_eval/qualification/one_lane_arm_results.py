"""Verify paired physical receiver science and publish detector compute costs."""

import argparse
import gzip
from hashlib import sha256
from pathlib import Path
from statistics import median, quantiles

import numpy as np

from leo.analysis.starlink.native_short_window import NativeShortWindow

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants.single_chain import analyze_native
from . import one_lane_arm as run
from .arm_receiver_results import oracle_rows
from .full_v5_check import _sha
from .prefix_figures import csv_file

PHYSICAL = ROOT / (
    "reports/2026_09_30_native_adaptive_deployment/usb/"
    "single-rx-detector-v1/physical-arm/panel.json"
)
ARCH_TITLES = ("Native x86", "Cortex-A53 QEMU")
MODE_TITLES = ("Dual stock", "One RX · packed", "One RX · strided")


def science(row):
    return encoded({k: v for k, v in row.items() if k != "timings_ms"})


def verify_mapping(dual, output, lane):
    if output["native_rows"] != 1 or dual["native_rows"] != 2:
        raise ValueError("unexpected number of genuinely computed receiver rows")
    rows, both = output["rows"], dual["rows"]
    if [r["receiver_id"] for r in rows] != [0, 1]:
        raise ValueError("physical receiver IDs failed to remap")
    blind = rows[1 - lane]
    same_clock = all(blind[key] == both[1 - lane][key] for key in ("probe_index", "probe_start_ms"))
    blank = not blind["candidates"] and all(
        value == 0
        for key, value in blind.items()
        if key not in ("receiver_id", "probe_index", "probe_start_ms", "timings_ms", "candidates")
    )
    return dict(
        active_exact=science(rows[lane]) == science(both[lane]), blank=blank, clock=same_clock
    )


def audit(m, inv, expected):
    rows, outcomes = [], []
    for edge, group in m["results"].items():
        entries = inv["roster"][edge]
        for mode, receipt in group.items():
            seen = {}
            for original, value in zip(group["dual"]["rows"], receipt["rows"], strict=True):
                i, repeat, lane = (value[k] for k in ("index", "repeat", "selected"))
                assert (i, repeat, lane) == tuple(
                    original[k] for k in ("index", "repeat", "selected")
                )
                entry = entries[i]
                item = dict(
                    arch=m["arch"],
                    edge=edge,
                    mode=mode,
                    case=entry.get("case"),
                    fixture=entry["file"],
                    kind=entry["kind"],
                    repeat=repeat,
                    lane=lane,
                )
                fingerprint = sha256(science(value["rows"][lane])).hexdigest()
                seen[repeat, entry["file"]] = fingerprint
                target = expected[edge].get(entry["file"])
                if mode == "dual" and target is not None:
                    archived = [run.receiver.projection(r) for r in value["rows"]] == [
                        p["candidates"] for p in target
                    ]
                else:
                    archived = None
                status = verify_mapping(original, value, lane) if mode != "dual" else None
                outcomes.append(
                    dict(
                        **item,
                        probe_clocks=entry.get("delivery_clock"),
                        sample_counter=entry.get("counter"),
                        selected_sha256=fingerprint,
                        direct_parity=status,
                        archived_exact=archived,
                        same_after_partner_zero=(
                            seen[repeat, entry["parent"]] == fingerprint
                            if "parent" in entry
                            else None
                        ),
                        plants=oracle_rows(entry, value),
                        positive_counts=[
                            sum(
                                run.positive(dict(candidates=[c]))
                                for c in run.receiver.projection(x)
                            )
                            for x in value["rows"]
                        ],
                    )
                )
                rows.append(
                    dict(
                        **item,
                        warm=i > 0 or repeat > 0,
                        native_rows=value["native_rows"],
                        input_bytes=value["input_bytes"],
                        staged_bytes=value["staged_bytes"],
                        **{
                            f"{stage}_{clock}_ms": cost / 1e6
                            for stage in ("read", "stage", "native", "map", "total")
                            for clock, cost in zip(("cpu", "wall"), value[stage], strict=True)
                        },
                    )
                )
    return rows, outcomes


def summarize(measured, rows, checks):
    table = {}
    for m in measured:
        arch = m["arch"]
        table[arch] = {}
        for mode in run.MODES:
            panel = [r for r in rows if (r["arch"], r["mode"], r["kind"]) == (arch, mode, "held")]
            warm = [r for r in panel if r["warm"]]
            process = {
                e: {k: p[mode][k] for k in ("cpu_s", "wall_s", "peak_rss_kib", "setup")}
                for e, p in m["results"].items()
            }
            table[arch][mode] = dict(
                held_count=len(panel),
                warm_count=len(warm),
                deadline_within_20ms=sum(r["total_wall_ms"] <= 20 for r in panel),
                p50={k: median(r[k] for r in warm) for k in warm[0] if k.endswith("_ms")},
                p95_wall_ms=quantiles(
                    [r["total_wall_ms"] for r in warm], n=100, method="inclusive"
                )[94],
                process=process,
            )
    parity = [c["direct_parity"] for c in checks if c["direct_parity"] is not None]
    null = [
        c["same_after_partner_zero"] for c in checks if c["same_after_partner_zero"] is not None
    ]
    return dict(
        timings=table,
        selected_rows=[sum(all(x.values()) for x in parity), len(parity)],
        partner_zero=([sum(null), len(null)]),
        archived_host_rows=[
            sum(c["archived_exact"] is True for c in checks if c["arch"] == "host"),
            sum(c["archived_exact"] is not None for c in checks if c["arch"] == "host"),
        ],
        test_row_counts={
            m: sorted({r["native_rows"] for r in rows if r["mode"] == m}) for m in run.MODES
        },
    )


def plot(folder, summary):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(9, 4.2))
    fig.subplots_adjust(top=0.77, bottom=0.16, left=0.08, right=0.98, wspace=0.30)
    for arch, title, ax in zip(run.ARCHES, ARCH_TITLES, axes, strict=True):
        group = summary["timings"][arch]
        cpu = [group[m]["p50"]["total_cpu_ms"] for m in run.MODES]
        wall = [group[m]["p50"]["total_wall_ms"] for m in run.MODES]
        ax.bar(range(3), cpu, color=("#58768d", "#067c79", "#0d585f"), width=0.62, label="CPU")
        ax.scatter(range(3), wall, marker="_", s=200, color="#102331", label="Wall")
        ax.axhline(20, linestyle="--", color="#ad394c", label="20 ms visit")
        ax.set(title=title, ylabel="Warm saved visit (ms)", ylim=(0, max(20, *cpu, *wall) * 1.2))
        ax.set_xticks(range(3), MODE_TITLES)
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=0.23)
    fig.suptitle("One physical receiver per visit", y=0.98)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels, frameon=False, ncols=3, loc="upper center", bbox_to_anchor=(0.5, 0.90)
    )
    fig.savefig(folder / "stage.png", dpi=180)
    fig.savefig(folder / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    save_json(
        folder / "stage-figure.json",
        dict(
            version=1,
            id="one-lane-arm",
            title="Physical single-receiver compute",
            boundary="Resident dual CI16 through stock detector and native physical-lane remap",
            sample="Recorded visits 12–17 on both RF edges, two passes per method",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="qualification-lock.json",
            note="Cortex-A53 times are host process clocks during QEMU emulation.",
        ),
    )


def installed_host(work, fixture, measured):
    """Audit the exact shared file and producer adapter used for whole IQ runs."""
    library = run.checked(run.WIDE_RUNTIME, run.WIDE_PIN)
    options = dict(sample_rate_hz=10_000_000, fractional_epoch=True)
    rows = []
    for edge, entries in fixture["roster"].items():
        root = work / "fixtures" / edge
        templates = [
            np.fromfile(root / f"{edge}-{k}.c16", dtype="<c16") for k in ("exact", "control")
        ]
        with NativeShortWindow(str(library), *templates, receiver_count=1, **options) as single:
            for j, entry in enumerate(entries):
                lane, name = entry["lane"], entry["file"]
                data = np.fromfile(work / "fixtures" / name, dtype="<i2").reshape(-1, 2, 2)
                output = analyze_native(single, data, lane)["rows"][0]
                witness = measured["results"][edge]["packed"]["rows"][j]["rows"][lane]
                rows.append(
                    dict(
                        edge=edge,
                        file=name,
                        lane=lane,
                        factors_exact=run.receiver.projection(output)
                        == run.receiver.projection(witness),
                        native_row_exact=output
                        == {k: v for k, v in witness.items() if k != "timings_ms"},
                        json_representation_exact=science(output) == science(witness),
                    )
                )
    return dict(library_sha256=run.WIDE_PIN, rows=rows)


def publish(work):
    folder = run.REPORT
    inv = run.read(work / "input-lock.json")
    expected = run.read(run.checked(work / "expected.json", inv["expected_sha256"]))
    measured = []
    for a in run.ARCHES:
        receipt = run.read(work / f"measurement-{a}.json")
        run.checked(work / "input-lock.json", receipt["input_sha256"])
        release = run.checked(work / f"build-{a}.json", receipt["build_sha256"])
        for k, h in run.read(release)["sources"].items():
            run.checked(ROOT / k, h)
        write(folder / release.name, release.read_bytes())
        measured.append(receipt)
    rows, checks = [], []
    for data in measured:
        a, b = audit(data, inv, expected)
        rows.extend(a)
        checks.extend(b)
    summary = summarize(measured, rows, checks)
    live = installed_host(work, inv, measured[0])
    summary["installed_host"] = [
        sum(r["native_row_exact"] for r in live["rows"]),
        len(live["rows"]),
    ]
    save_json(folder / "installed-host.json", live)
    save_json(folder / "summary.json", summary)
    csv_file(folder / "stage.csv", rows)
    write(folder / "input-lock.json", (work / "input-lock.json").read_bytes())
    for file, value in (("expected", expected), ("measurements", measured), ("parity", checks)):
        write(folder / (file + ".json.gz"), gzip.compress(encoded(value), mtime=0))
    save_json(
        folder / "historical-board.json",
        dict(
            access=dict(path=str(run.BOARD.relative_to(ROOT)), sha256=_sha(run.BOARD)),
            historical=dict(
                path=str(PHYSICAL.relative_to(ROOT)),
                sha256=_sha(PHYSICAL),
                receipt=run.read(PHYSICAL),
            ),
            physical_measurement_this_study=False,
        ),
    )
    plot(folder, summary)
    files = (
        "PROTOCOL.md",
        "input-lock.json",
        "expected.json.gz",
        "measurements.json.gz",
        "parity.json.gz",
        "summary.json",
        "stage.csv",
        "stage.png",
        "stage.pdf",
        "stage-figure.json",
        "historical-board.json",
        "installed-host.json",
        "build-host.json",
        "build-arm64.json",
    )
    if (folder / "README.md").is_file():
        files += ("README.md",)
    save_json(
        folder / "qualification-lock.json",
        dict(
            cases=["DS26-0197", "DS29-0316"],
            files={f: _sha(folder / f) for f in files},
            scope="one scheduled physical receiver and an empty companion",
            sources={str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__))},
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=local_output, default=run.WORK)
    publish(p.parse_args().work)
