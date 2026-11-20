"""Publish fixed-input installed capture versus wide detector timing and science."""

import argparse
from pathlib import Path
from statistics import median

from ..__main__ import ROOT, local_output, save_json, write
from . import capture_runtime as run
from .full_v5_check import _sha, compare_probes
from .prefix_figures import csv_file

LABELS = ("Capture-era dual", "Current dual", "Current one RX")


def audit(archive, windows, rows):
    timings, evidence = [], []
    for item in windows:
        v, lane = item["source"]["visit"], item["selected_lane"]
        by_key = {(r["repeat"], r["mode"]): r for r in rows if r["visit"] == v}
        if len(by_key) != 6:
            raise ValueError("paired bench missed a repeat or detector")
        for repeat in range(2):
            original, dual, single = [by_key[repeat, m]["probes"] for m in run.MODES]
            if original != item["previous_capture"]:
                raise ValueError("original capture outputs changed from the sealed measured rows")
            if single[lane] != dual[lane] or single[1 - lane] != dict(
                dual[1 - lane], candidates=[]
            ):
                raise ValueError(
                    "one physical receiver remap changed the active row or probe clock"
                )
            target_lane = item["source"]["receiver"]
            target = dict(original[target_lane], candidates=[item["source"]["target"]])
            known = {
                mode: any(
                    abs(hit["raw_cfo_delta_hz"]) <= 1000
                    for hit in compare_probes(target, probes[target_lane], 10_000_000)[
                        "positive_matches"
                    ]
                )
                for mode, probes in zip(run.MODES, (original, dual, single), strict=True)
            }
            common = dict(
                case=archive,
                visit=v,
                edge=item["source"]["archive_probe"]["edge"],
                label=item["source"]["kind"],
                selected_rx=lane,
                repeat=repeat,
                iq_sha256=item["source"]["iq_sha256"],
                sample_counter=item["source"]["counter"],
            )
            for m in run.MODES:
                timings.append(
                    dict(
                        **common,
                        mode=m,
                        cpu_ms=by_key[repeat, m]["cpu_ns"] / 1e6,
                        wall_ms=by_key[repeat, m]["wall_ns"] / 1e6,
                    )
                )
            evidence.append(
                dict(
                    **common,
                    capture_exact=True,
                    active_and_clock_exact=True,
                    target_receiver=target_lane,
                    selected_target_lane=target_lane == lane,
                    target_recovery=known,
                    capture_to_dual=[
                        compare_probes(a, b, 10_000_000)
                        for a, b in zip(original, dual, strict=True)
                    ],
                    capture_to_one=[
                        compare_probes(a, b, 10_000_000)
                        for a, b in zip(original, single, strict=True)
                    ],
                )
            )
    return timings, evidence


def summary(timings, evidence):
    by_visit = {}
    for case in run.CASES:
        by_visit[case] = {}
        for v in sorted({r["visit"] for r in timings if r["case"] == case}):
            by_visit[case][v] = {
                m: {
                    clock: median(
                        r[clock]
                        for r in timings
                        if (r["case"], r["visit"], r["mode"]) == (case, v, m)
                    )
                    for clock in ("cpu_ms", "wall_ms")
                }
                for m in run.MODES
            }
    data = {m: [r for r in timings if r["mode"] == m] for m in run.MODES}
    scientific = [r for r in evidence if r["repeat"] == 0]
    science = {}
    for k in ("capture_to_dual", "capture_to_one"):
        matches = [x for r in scientific for x in r[k]]
        science[k] = dict(
            capture_positive=sum(p["production_positive"] for p in matches),
            current_positive=sum(p["native_positive"] for p in matches),
            alias_family_matches=sum(len(p["positive_matches"]) for p in matches),
            unwrapped_cfo_matches=sum(
                abs(m["raw_cfo_delta_hz"]) <= 1000 for p in matches for m in p["positive_matches"]
            ),
        )
    return dict(
        counts=dict(timed_calls=len(timings), windows=len(scientific)),
        by_visit=by_visit,
        science=science,
        target_recovery={
            label: dict(
                cases=sum(r["label"] == label for r in scientific),
                scheduled=sum(
                    r["label"] == label and r["selected_target_lane"] for r in scientific
                ),
                **{
                    m: sum(r["label"] == label and r["target_recovery"][m] for r in scientific)
                    for m in run.MODES
                },
            )
            for label in ("matched", "miss")
        },
        timings={
            m: dict(
                median_cpu_ms=median(r["cpu_ms"] for r in rows),
                median_wall_ms=median(r["wall_ms"] for r in rows),
                within_20ms=sum(r["wall_ms"] <= 20 for r in rows),
                total=len(rows),
            )
            for m, rows in data.items()
        },
        median_paired_cpu_ratio={
            m: median(
                v["capture"]["cpu_ms"] / v[m]["cpu_ms"]
                for ss in by_visit.values()
                for v in ss.values()
            )
            for m in ("dual", "one")
        },
    )


def plot(folder, result):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.5, 4.9))
    fig.subplots_adjust(top=0.81, bottom=0.23, left=0.10, right=0.98)
    visits = [
        (f"{case}\nv{v}", row)
        for case, rows in result["by_visit"].items()
        for v, row in rows.items()
    ]
    for mode, label, color in zip(
        run.MODES, LABELS, ("#495f74", "#057b79", "#ba6841"), strict=True
    ):
        ax.plot([r[mode]["cpu_ms"] for _, r in visits], label=label, color=color, marker="o")
    ax.axhline(20, color="#b84650", alpha=0.65, linestyle="--", label="20 ms reference")
    ax.set_yscale("log")
    ax.set_ylabel("Median process CPU per visit (ms)")
    ax.set_xticks(range(len(visits)), [name for name, _ in visits], fontsize=9)
    ax.grid(axis="y", alpha=0.30)
    fig.suptitle("Installed capture and current GLRT on the same IQ", y=0.98)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(
        handles, labels, frameon=False, loc="upper center", ncols=4, bbox_to_anchor=(0.5, 0.91)
    )
    fig.savefig(folder / "stage.png", dpi=180)
    fig.savefig(folder / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    save_json(
        folder / "stage-figure.json",
        dict(
            version=1,
            id="capture-runtime",
            title="Installed capture and current native runtime",
            boundary="Resident dual CI16 to projected physical receiver probes on x86 CPU 7",
            sample="Eight authenticated capture-starts visits, two measured passes per detector",
            note="Selected enriched known-time panel. The CPU axis is logarithmic.",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="qualification-lock.json",
        ),
    )


def publish(work):
    folder = run.REPORT
    ip = work / "input-lock.json"
    inp = run.read(ip)
    names = [f"{i}.json.gz" for i in run.CASES]
    timings, results = [], []
    for ident, filename in zip(run.CASES, names, strict=True):
        receipt = run.decompress(work / filename)
        run.checked(ip, receipt["input_lock_sha256"])
        rows, comparisons = audit(ident, inp["cases"][ident]["entries"], receipt["measurements"])
        timings.extend(rows)
        results.extend(comparisons)
        write(folder / filename, (work / filename).read_bytes())
    write(folder / ip.name, ip.read_bytes())
    stats = summary(timings, results)
    save_json(folder / "summary.json", stats)
    save_json(folder / "parity.json", results)
    csv_file(folder / "stage.csv", timings)
    plot(folder, stats)
    names += [
        "PROTOCOL.md",
        ip.name,
        "summary.json",
        "parity.json",
        "stage.csv",
        "stage.png",
        "stage.pdf",
        "stage-figure.json",
    ]
    if (folder / "README.md").is_file():
        names.append("README.md")
    save_json(
        folder / "qualification-lock.json",
        dict(
            cases=list(run.CASES),
            files={n: _sha(folder / n) for n in names},
            scope="original and current detector-only runtime, matched resident x86 IQ",
            sources={str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__))},
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", nargs="?", default=run.WORK, type=local_output)
    publish(p.parse_args().work)
