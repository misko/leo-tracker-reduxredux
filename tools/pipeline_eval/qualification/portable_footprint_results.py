"""Publish the traced DS26 detector footprint with numeric figure data."""

import argparse
import csv
import gzip
import json
from functools import cache
from pathlib import Path

from .portable_footprint import read, save, sha

ROLES = {"accelerated": "Public accelerated", "portable": "Resident C"}
STAGES = (
    ("python", "numerical", "Python numerical and schedule"),
    ("python", "abi", "Python ABI and local evidence"),
    ("python", "public", "Python validity and projection"),
    ("c", "shared", "C shared source"),
    ("c", "exclusive", "C arm-specific source"),
)


def category(row):
    path, name = Path(row["path"]), row["name"]
    if "/leo/analysis/starlink/" in str(path) or path.stem in {
        "fast_scan_detector",
        "fine_search",
        "fine_batch",
        "conditioned_cfo_bank",
        "refine_bank",
        "prepared_hotpath_peaks",
    }:
        return "numerical"
    if path.stem in {"capture_fft", "portable_field"} or name.split(".")[0] == "production_glrt":
        return "abi"
    return "public"


def python_counts(rows):
    sources, lines, code, functions = set(), set(), set(), set()
    for row in rows:
        p, name, start = row["path"], row["name"], row["definition"]
        sources.add(p)
        lines.update((p, line) for line in row["lines"])
        code.add((p, name, start))
        if not name.split(".")[-1].startswith("<"):
            functions.add((p, name, start))
    return dict(
        files=len(sources), lines=len(lines), code_objects=len(code), functions=len(functions)
    )


@cache
def shared_id(path):
    return Path(path).name, sha(Path(path))


def memory(work):
    record = read(work / "summary.json")
    workers = [row["terminal"]["end"] for row in record["workers"].values()]
    return dict(
        raw_wall_s=record["raw_wall_s"],
        maximum_process_rss_kib=max(x["rss_peak_kib"] for x in workers),
        maximum_service_peak_bytes=max(x["memory.peak"] for x in workers),
        maximum_swap_bytes=max(
            int(row["systemd"]["MemorySwapPeak"]) for row in record["raw_services"].values()
        ),
        named_c_workspace_bytes=max(
            (
                row["terminal"].get("portable_workspace_bytes", 0)
                for row in record["workers"].values()
            ),
            default=0,
        )
        or None,
    )


def summarize(scratch):
    plan = read(scratch / "plan.json")
    coverage = read(scratch / "c-coverage.json")
    verification = read(scratch / "verification.json")
    shared = set.intersection(*({shared_id(p) for p in coverage[r]["sources"]} for r in ROLES))
    summary = dict(
        protocol_sha256=plan["protocol_sha256"],
        verification=verification,
        visits=plan["visits"],
        shared_c_sources=[name for name, _ in sorted(shared)],
        arms={},
    )
    data = {}
    for role in ROLES:
        route = plan["arms"][role]
        c = coverage[role]["sources"]
        release = read(scratch / f"{role}-release.json")
        data[role] = release
        python = [row for visit in release["visits"] for row in visit["trace"]]
        binary = route["libraries"].values()
        c_roles = {}
        for label, subset in [
            ("shared", [p for p in c if shared_id(p) in shared]),
            ("exclusive", [p for p in c if shared_id(p) not in shared]),
            ("all", list(c)),
        ]:
            c_roles[label] = dict(
                files=len(subset),
                active_files=sum(bool(c[p]["lines"]) for p in subset),
                lines=sum(len(c[p]["lines"]) for p in subset),
                executable_lines=sum(len(c[p]["executable"]) for p in subset),
                physical_source_lines=sum(c[p]["physical_lines"] for p in subset),
                functions=sum(
                    sum(calls > 0 for calls in c[p]["functions"].values()) for p in subset
                ),
            )
        summary["arms"][role] = dict(
            python={
                "all": python_counts(python),
                **{
                    label: python_counts(r for r in python if category(r) == label)
                    for lang, label, _ in STAGES
                    if lang == "python"
                },
            },
            cold_decoder_python=python_counts(release["decode"]),
            c=c_roles,
            compiled_translation_units=sum(len(lib["translation_units"]) for lib in binary),
            link_libraries=len(binary),
            binary_bytes=sum(lib["release_bytes"] for lib in binary),
            native_elf_dependencies=sorted({x for lib in binary for x in lib["needed"]}),
            mapped_fft_libraries=release["external_maps"],
            python_external_per_visit=sorted({p for v in release["visits"] for p in v["external"]}),
            external_c_headers=coverage[role]["external_headers"],
            memory=memory(Path(route["work"])),
        )
    identities = {
        r: {
            (shared_id(x["path"]), n)
            for v in data[r]["visits"]
            for x in v["trace"]
            for n in x["lines"]
        }
        for r in ROLES
    }
    summary["shared_per_visit_python_lines"] = len(set.intersection(*identities.values()))
    return summary, data


def figure(folder, summary):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    columns = ("panel", "stage", "run", "measure", "value")
    plotted = [
        dict(
            panel=lang,
            stage=title,
            run=role,
            measure="lines",
            value=summary["arms"][role][lang][name]["lines"],
        )
        for lang, name, title in STAGES
        for role in ROLES
    ]
    with (folder / "stage.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(plotted)

    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.5), layout="constrained")
    colors = ("#576f8c", "#007b75")
    for ax, lang, xlabel in zip(
        axes, ("python", "c"), ("Traced Python lines", "Covered C executable lines"), strict=True
    ):
        keys = [title for domain, _, title in STAGES if domain == lang]
        for i, role in enumerate(ROLES):
            values = [p["value"] for p in plotted if p["panel"] == lang and p["run"] == role]
            locations = [j + 0.19 * (2 * i - 1) for j in range(len(keys))]
            bars = ax.barh(locations, values, height=0.32, color=colors[i], label=ROLES[role])
            ax.bar_label(bars, padding=3, fontsize=9)
        ax.set(yticks=range(len(keys)), yticklabels=keys, xlabel=xlabel)
        ax.set_xlim(0, max(p["value"] for p in plotted if p["panel"] == lang) * 1.15)
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=0.18)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, ncols=2, loc="outside lower center", frameon=False)
    fig.suptitle("Detector source reached on three fixed DS26-0020 visits", fontsize=13)
    fig.savefig(folder / "stage.png", dpi=180)
    fig.savefig(folder / "stage.pdf")
    plt.close(fig)
    save(
        folder / "stage-figure.json",
        dict(
            boundary="Signed CI16 already decoded through published fractional detector candidates",
            csv="stage.csv",
            id="detector-footprint-ds26-0020",
            image="stage.png",
            pdf="stage.pdf",
            note=(
                "Python counts use release line tracing. C counts include initialization "
                "and cleanup in separate gcov builds. Position unmeasured."
            ),
            sample="Visits 0, 2 and 4 from one signed 64-visit chunk",
            seal="evidence-lock.json",
            title="Detector source reached on three fixed DS26-0020 visits",
            version=1,
        ),
    )


def publish(scratch, folder):
    summary, traces = summarize(scratch)
    save(folder / "summary.json", summary)
    evidence = {
        "plan": read(scratch / "plan.json"),
        "c_coverage": read(scratch / "c-coverage.json"),
        "traces": {
            role: {key: v for key, v in record.items() if key != "rows"}
            for role, record in traces.items()
        },
    }
    (folder / "trace.json.gz").write_bytes(
        gzip.compress(json.dumps(evidence, sort_keys=True).encode(), mtime=0)
    )
    figure(folder, summary)
    names = (
        "PROTOCOL.md",
        "summary.json",
        "trace.json.gz",
        "stage.csv",
        "stage.png",
        "stage.pdf",
        "stage-figure.json",
    )
    if (folder / "README.md").is_file():
        names += ("README.md",)
    save(
        folder / "evidence-lock.json",
        dict(
            files={name: sha(folder / name) for name in names},
            sources={
                path.name: sha(path)
                for path in (Path(__file__), Path(__file__).with_name("portable_footprint.py"))
            },
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    publish(args.scratch, args.output)
