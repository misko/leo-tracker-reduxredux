"""Publish complete held detector parity and the prepared workspace savings."""

import argparse
from itertools import product
from pathlib import Path
from statistics import median

from ..__main__ import ROOT, local_output, save_json, write
from . import capture_runtime as auth
from . import original_kernel_trial as run
from .capture_exact_results import fields
from .full_v5_check import _sha
from .prefix_figures import csv_file

LABELS = ("Installed", "Prior compiled", "Prepared")


def audit(ident, received, cfg):
    wanted = [(str(r["visit"]), r["kind"]) for r in cfg["rows"]]
    if ident in ("DS26-0237", "DS29-0082"):
        wanted += [("flat", "control"), ("signed", "control")]
    indexed = {(r["label"], r["kind"], r["repeat"], r["mode"]): r for r in received["rows"]}
    expected = {(*a, b, c) for a, b, c in product(wanted, range(2), run.MODES)}
    if set(indexed) != expected or len(indexed) != len(received["rows"]):
        raise ValueError(f"missing paired installed detector output for {ident}")
    rows, scores, caches = [], [], []
    for (label, kind, repeat, mode), rec in indexed.items():
        a = indexed[label, kind, repeat, "installed"]
        b = indexed[label, kind, repeat, "combined"]
        if not rec["iq_sha256"] == a["iq_sha256"] == b["iq_sha256"]:
            raise ValueError("raw waveform bytes differed across timed detector choices")
        orig, joint, data = (v["data"] for v in (a, b, rec))
        key = dict(
            id=ident,
            kind=kind,
            visit=label,
            repeat=repeat,
            mode=mode,
            cpu=received["cpu"],
            edge=cfg["edge"],
            iq_sha256=rec["iq_sha256"],
        )
        scores.append(
            dict(
                **key,
                exact_full=all(data[k] == orig[k] for k in ("public", "probes", "attempts")),
                exact_compiled=all(data[k] == joint[k] for k in ("public", "probes", "attempts")),
                differences=fields(orig["public"], data["public"]),
                gated_count=sum(
                    c["passed_fractional_margin_gate"]
                    for p in data["probes"]
                    for c in p["candidates"]
                ),
            )
        )
        grids = data["grid_receipts"]
        rows.append(
            dict(
                **key,
                cpu_ms=data["cpu_ns"] / 1e6,
                wall_ms=data["wall_ns"] / 1e6,
                peak_rss_kib=data["rss_after"]["hwm_kib"],
                filter_ffts=sum(g["filter_ffts"] for g in grids),
                inverse_ffts=sum(g["inverse_ffts"] for g in grids),
                **{k + "_cpu_ms": y / 1e6 for k, y in data["stages_cpu_ns"].items()},
            )
        )
        caches.extend(dict(**key, **g) for g in grids)
    return rows, scores, caches


def summarize(clock, cache, science, grids):
    panel, parity = {}, {}
    for ident in run.CASES:
        panel[ident] = {}
        for mode in run.MODES:
            t = [r for r in clock if (r["id"], r["mode"], r["kind"]) == (ident, mode, "new")]
            panel[ident][mode] = dict(
                medians={k: median(r[k] for r in t) for k in t[0] if k.endswith("_ms")},
                n=len(t),
                rss_kib=max(r["peak_rss_kib"] for r in t),
                filter_ffts=sum(r["filter_ffts"] for r in t),
                inverse_ffts=sum(r["inverse_ffts"] for r in t),
            )
    for mode in run.MODES:
        parity[mode] = {
            kind: dict(
                matches=sum(
                    r["exact_full"] for r in science if (r["mode"], r["kind"]) == (mode, kind)
                ),
                total=sum((r["mode"], r["kind"]) == (mode, kind) for r in science),
            )
            for kind in ("new", "stress", "control")
        }
    resource = {}
    for mode in ("combined", "prepared"):
        data = [r for r in cache if r["mode"] == mode and r["kind"] != "control"]
        resource[mode] = dict(
            grids=len(data),
            cached_grids=sum(r["filter_ffts"] == 0 for r in data),
            input_ffts=sum(r["input_ffts"] for r in data),
            reference_ffts=sum(r["filter_ffts"] for r in data),
            inverse_ffts=sum(r["inverse_ffts"] for r in data),
            bounds={
                str(n): {
                    k: dict(
                        count=len(x),
                        median_grid_ms=median(r["native_cpu_ns"] / 1e6 for r in x) if x else None,
                    )
                    for k in ("first_key", "reused_key")
                    if (
                        x := [
                            r
                            for r in data
                            if r["anchors"] == n and (r["filter_ffts"] > 0) == (k == "first_key")
                        ]
                    )
                }
                for n in sorted({r["anchors"] for r in data})
            },
        )
    all_grids = [g for r in grids.values() for g in r]
    return dict(
        panel=panel,
        parity=parity,
        resources=resource,
        numerical=dict(
            cells=sum(g["cells"] for g in all_grids),
            drift_direct=max(g["delta_from_direct"] for g in all_grids),
            drift_prior=max(g["delta_from_combined"] for g in all_grids),
            ordered_match=sum(g["retained_keys_exact"] for g in all_grids),
            compared_grids=len(all_grids),
            min_original_gap=min(
                g["minimum_direct_gap"] for g in all_grids if g["minimum_direct_gap"] is not None
            ),
            near_tie_steps=sum(g["close_steps"] for g in all_grids),
        ),
    )


def plot(folder, evidence):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.5))
    fig.subplots_adjust(top=0.76, bottom=0.19, left=0.10, right=0.98, wspace=0.28)
    for ax, key, title in zip(
        axes,
        ("cpu_ms", "coarse_inclusive_cpu_ms"),
        ("Complete detector", "Coarse acquisition"),
        strict=True,
    ):
        for j, (mode, label, color) in enumerate(
            zip(run.MODES, LABELS, ("#5d758b", "#748e9a", "#0c7772"), strict=True)
        ):
            ax.bar(
                [i + (j - 1) * 0.22 for i in range(4)],
                [evidence["panel"][name][mode]["medians"][key] for name in run.CASES],
                width=0.21,
                label=label,
                color=color,
            )
        ax.set_xticks(range(4), run.CASES, rotation=28, ha="right", fontsize=8)
        ax.set(title=title, ylabel="Median CPU per dual visit (ms)")
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=0.23)
    fig.suptitle("Prepared FFT reference and shared IQ normalization", y=0.98)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.90), ncols=3, frameon=False
    )
    fig.savefig(folder / "stage.png", dpi=180)
    fig.savefig(folder / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    save_json(
        folder / "stage-figure.json",
        dict(
            version=1,
            id="original-kernel",
            title="Prepared original detector kernel",
            boundary="Resident dual saved IQ to capture-era native probe rows, measured host CPU",
            sample="Eight new matched valid windows, two repeats per detector",
            note="Saved IQ on host x86 with both legacy and screened capture releases.",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="qualification-lock.json",
        ),
    )


def publish(work):
    folder = run.REPORT
    lock = work / "source-lock.json"
    roster = auth.read(lock)
    for file, digest in roster["sources"].items():
        auth.checked(Path(file), digest)
    timings, scientific, cache, grid = [], [], [], {}
    names = [
        "PROTOCOL.md",
        lock.name,
        "stage.png",
        "stage.pdf",
        "stage.csv",
        "stage-figure.json",
        "summary.json",
        "cache.csv",
        "parity.json",
        "grid-audit.json",
    ]
    prepared = roster["libs"]["prepared"]
    binary = auth.checked(Path(prepared["path"]), prepared["sha256"])
    write(folder / binary.name, binary.read_bytes())
    names.append(binary.name)
    write(folder / lock.name, lock.read_bytes())
    for case, cfg in roster["cases"].items():
        p = work / f"{case}.json.gz"
        d = auth.decompress(p)
        auth.checked(lock, d["lock_sha256"])
        t, s, c = audit(case, d, cfg)
        timings.extend(t)
        scientific.extend(s)
        cache.extend(c)
        grid[case] = d["grid"]
        names.append(p.name)
        write(folder / p.name, p.read_bytes())
    summary = summarize(timings, cache, scientific, grid)
    csv_file(folder / "stage.csv", timings)
    csv_file(folder / "cache.csv", cache)
    save_json(folder / "summary.json", summary)
    save_json(folder / "grid-audit.json", grid)
    save_json(folder / "parity.json", scientific)
    plot(folder, summary)
    if (folder / "README.md").is_file():
        names.append("README.md")
    save_json(
        folder / "qualification-lock.json",
        dict(
            cases=list(run.CASES),
            files={f: _sha(folder / f) for f in names},
            sources={str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__))},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output, nargs="?", default=run.WORK)
    publish(parser.parse_args().work)
