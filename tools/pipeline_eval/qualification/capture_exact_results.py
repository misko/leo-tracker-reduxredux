"""Quantify exact public parity and numerical coarse-grid drift separately."""

import argparse
from itertools import product
from pathlib import Path
from statistics import median

from ..__main__ import ROOT, local_output, save_json, write
from . import capture_exact_trial as trial
from . import capture_runtime as auth
from .full_v5_check import _sha, compare_probes
from .prefix_figures import csv_file

LABELS = ("Installed", "FP64 FFT", "Batched FP32", "+ refinement")


def fields(a, b, prefix=""):
    if a == b:
        return []
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        return [d for k in a for d in fields(a[k], b[k], prefix + "/" + k)]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [
            d
            for i, (x, y) in enumerate(zip(a, b, strict=True))
            for d in fields(x, y, f"{prefix}/{i}")
        ]
    absolute = abs(a - b) if type(a) in (float, int) and type(b) in (float, int) else None
    return [dict(field=prefix, absolute=absolute)]


def timing(ident, received, source):
    labels = [str(x["visit"]) for x in source["rows"]]
    if source["controls"]:
        labels.extend(("zero", "weak-signed"))
    keyed = {(r["label"], r["repeat"], r["mode"]): r for r in received["rows"]}
    expected = set(product(labels, range(2), trial.MODES))
    if expected != set(keyed) or len(expected) != len(received["rows"]):
        raise ValueError(f"detector attempts incomplete for {ident}")
    times, outcomes = [], []
    for (label, repeat, mode), item in keyed.items():
        baseline = keyed[label, repeat, "installed"]
        result, original = item["result"], baseline["result"]
        if item["iq_sha256"] != baseline["iq_sha256"]:
            raise ValueError("paired complete detector waveform digest differs")
        common = dict(
            id=ident,
            label=label,
            repeat=repeat,
            mode=mode,
            kind=item["kind"],
            cpu=received["cpu"],
            screened=received["screen_available"],
            iq_sha256=item["iq_sha256"],
        )
        times.append(
            dict(
                **common,
                call_order=item["order"],
                cpu_ms=result["cpu_ns"] / 1e6,
                wall_ms=result["wall_ns"] / 1e6,
                peak_rss_kib=result["rss_after"]["hwm_kib"],
                **{k + "_cpu_ms": s / 1e6 for k, s in result["stages_cpu_ns"].items()},
            )
        )
        outcomes.append(
            dict(
                **common,
                exact_public=original["public"] == result["public"],
                exact_factors=original["probes"] == result["probes"],
                exact_attempts=original["attempts"] == result["attempts"],
                changes=fields(original["public"], result["public"]),
                gates=[
                    compare_probes(a, b, 10_000_000)
                    for a, b in zip(original["probes"], result["probes"], strict=True)
                ],
                cells_seen_in_fft=sum(
                    g["epochs"] * g["cfo_lanes"] for g in result["grid_receipts"] if g["applied"]
                ),
            )
        )
    return times, outcomes


def stats(times, outcomes):
    results = {}
    for ident in trial.CASES:
        results[ident] = {}
        for mode in trial.MODES:
            rows = [r for r in times if (r["id"], r["mode"], r["kind"]) == (ident, mode, "held")]
            results[ident][mode] = dict(
                **{k: median(r[k] for r in rows) for k in rows[0] if k.endswith("_ms")},
                peak_rss_kib=max(r["peak_rss_kib"] for r in rows),
                n=len(rows),
            )
    science = {}
    for mode in trial.MODES:
        rows = [r for r in outcomes if r["mode"] == mode]
        science[mode] = dict(
            held_exact_public=sum(r["kind"] == "held" and r["exact_public"] for r in rows),
            held_attempts=sum(r["kind"] == "held" for r in rows),
            control_exact_public=sum(r["kind"] == "control" and r["exact_public"] for r in rows),
            control_attempts=sum(r["kind"] == "control" for r in rows),
            exact_factors=sum(r["exact_factors"] for r in rows),
            exact_attempts=sum(r["exact_attempts"] for r in rows),
            original_positive_candidates=sum(
                g["production_positive"] for r in rows for g in r["gates"]
            ),
            positive_candidates=sum(g["native_positive"] for r in rows for g in r["gates"]),
            missed_positive_candidates=sum(g["production_only"] for r in rows for g in r["gates"]),
        )
    return dict(cases=results, science=science)


def selector(work, folder, result):
    path = work / "selector-sources.json"
    seal = auth.read(path)
    auth.checked(work / "source-lock.json", seal["base_sha256"])
    for p, h in seal["sources"].items():
        auth.checked(Path(p), h)
    rows, scores, names = [], {}, [path.name]
    write(folder / path.name, path.read_bytes())
    for ident in trial.CASES:
        filename = f"{ident}-selector.json.gz"
        receipt = auth.decompress(work / filename)
        auth.checked(path, receipt["source_sha256"])
        baselines = auth.decompress(work / f"{ident}.json.gz")["rows"]
        old = {
            (r["label"], r["repeat"]): r
            for r in baselines
            if r["kind"] == "held" and r["mode"] == "installed"
        }
        fresh = {(r["visit"], r["repeat"], r["mode"]): r for r in receipt["traces"]}
        expected = {(int(label), repeat, mode) for label, repeat in old for mode in seal["methods"]}
        if expected != set(fresh) or len(receipt["traces"]) != len(fresh):
            raise ValueError("vector selector comparison has incomplete visits")
        for (v, repeat, mode), current in fresh.items():
            a = old[str(v), repeat]
            b = fresh[v, repeat, "heap"]
            c = current["result"]
            if not current["iq_sha256"] == a["iq_sha256"] == b["iq_sha256"]:
                raise ValueError("paired selector trial changed input bytes")
            marks = ("public", "probes", "attempts")
            rows.append(
                dict(
                    id=ident,
                    visit=v,
                    repeat=repeat,
                    mode=mode,
                    cpu=receipt["cpu"],
                    exact_installed=all(c[k] == a["result"][k] for k in marks),
                    exact_fresh_heap=all(c[k] == b["result"][k] for k in marks),
                    cpu_ms=c["cpu_ns"] / 1e6,
                    wall_ms=c["wall_ns"] / 1e6,
                    coarse_inclusive_cpu_ms=c["stages_cpu_ns"]["coarse_inclusive"] / 1e6,
                    selection_cpu_ms=c["stages_cpu_ns"]["peak_selection"] / 1e6,
                )
            )
        medians = {
            mode: {
                k: median(r[k] for r in rows if (r["id"], r["mode"]) == (ident, mode))
                for k in ("cpu_ms", "wall_ms", "coarse_inclusive_cpu_ms", "selection_cpu_ms")
            }
            for mode in seal["methods"]
        }
        result["cases"][ident]["vector"] = medians["vector"]
        scores[ident] = medians
        names.append(filename)
        write(folder / filename, (work / filename).read_bytes())
    result["selector"] = dict(
        medians=scores,
        exact_installed=sum(r["exact_installed"] for r in rows),
        exact_fresh_heap=sum(r["exact_fresh_heap"] for r in rows),
        attempts=len(rows),
    )
    csv_file(folder / "selector.csv", rows)
    return [*names, "selector.csv"]


def plot(folder, result):
    import matplotlib.pyplot as plt

    fig, panels = plt.subplots(1, 2, figsize=(9.8, 4.8))
    fig.subplots_adjust(top=0.76, bottom=0.18, left=0.10, right=0.98, wspace=0.32)
    colors = ("#4e6376", "#628fa8", "#138180", "#ad643d")
    for ax, (field, title) in zip(
        panels,
        (("cpu_ms", "Full detector"), ("coarse_inclusive_cpu_ms", "Coarse acquisition")),
        strict=True,
    ):
        for n, (mode, label, color) in enumerate(zip(trial.MODES, LABELS, colors, strict=True)):
            ax.bar(
                [i + (n - 1.5) * 0.19 for i in range(4)],
                [result["cases"][c][mode][field] for c in trial.CASES],
                label=label,
                color=color,
                width=0.18,
            )
        ax.set_xticks(range(4), trial.CASES, rotation=28, ha="right", fontsize=8)
        ax.set(title=title, ylabel="Median CPU per visit (ms)")
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Batched carrier FFTs in the capture-era detector", y=0.98)
    handles, labels = panels[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncols=4,
        frameon=False,
        bbox_to_anchor=(0.5, 0.91),
    )
    fig.savefig(folder / "stage.png", dpi=180)
    fig.savefig(folder / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    save_json(
        folder / "stage-figure.json",
        dict(
            version=1,
            id="capture-batched-exact",
            title="Batched capture-era correlation",
            boundary="Resident saved dual CI16 through the installed detector and probe projection",
            sample="Eight held windows on four recordings with two rotations per method",
            note="CPU from x86. Public parity and coarse-grid rounding are audited separately.",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="qualification-lock.json",
        ),
    )


def publish(work):
    folder = trial.REPORT
    source = work / "source-lock.json"
    config = auth.read(source)
    for path, value in config["sources"].items():
        auth.checked(Path(path), value)
    times, outcomes, grid = [], [], {}
    names = [source.name]
    for ident in trial.CASES:
        p = work / f"{ident}.json.gz"
        data = auth.decompress(p)
        auth.checked(source, data["source_lock_sha256"])
        measured, checked = timing(ident, data, config["cases"][ident])
        times.extend(measured)
        outcomes.extend(checked)
        grid[ident] = data["grid_audit"]
        names.append(p.name)
        write(folder / p.name, p.read_bytes())
    write(folder / source.name, source.read_bytes())
    result = stats(times, outcomes)
    if (work / "selector-sources.json").is_file():
        names.extend(selector(work, folder, result))
    save_json(folder / "summary.json", result)
    save_json(folder / "parity.json", outcomes)
    save_json(folder / "grid-audit.json", grid)
    csv_file(folder / "stage.csv", times)
    plot(folder, result)
    names.extend(
        (
            "PROTOCOL.md",
            "summary.json",
            "parity.json",
            "grid-audit.json",
            "stage.csv",
            "stage.png",
            "stage.pdf",
            "stage-figure.json",
        )
    )
    if (folder / "README.md").is_file():
        names.append("README.md")
    save_json(
        folder / "qualification-lock.json",
        dict(
            files={f: _sha(folder / f) for f in names},
            cases=list(trial.CASES),
            sources={str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__))},
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", nargs="?", default=trial.WORK, type=local_output)
    publish(p.parse_args().work)
