"""Package the relocated application and measured stage-only parity figure."""

import argparse
import gzip
import io
import json
import tarfile

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import portable_mode_build as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file

ARCHIVE = "portable-receiver-staggered.tar.gz"
FOOTPRINT = "footprint.json"
PNG = "mode-resources.png"
PDF = "mode-resources.pdf"
TABLE = "mode-resources.csv"


def package(folder, report):
    locked = whole_iq.read(folder / "files.json")
    with tarfile.open(trial.BASE / "portable-receiver.tar.gz", "r:gz") as original:
        old = json.load(original.extractfile("portable-receiver/files.json"))["files"]
        sizes = {
            leaf.removeprefix("portable-receiver/"): original.getmember(leaf).size
            for leaf in original.getnames()
        }
    new = locked["files"]
    if {n for n, h in old.items() if new.get(n) != h} != {"receive.py"}:
        raise ValueError("the portable stock detector, reader and solver assets must be unchanged")
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as dest:
        for name in sorted(
            [*new, "files.json", "README.md", "example-input.json", "requirements.txt"]
        ):
            if name == "README.md":
                body = (report / "USAGE.md").read_bytes()
            else:
                src = folder / name
                if name in new:
                    whole_iq.checked(src, new[name])
                body = src.read_bytes()
            info = tarfile.TarInfo("portable-receiver/" + name)
            info.size = len(body)
            info.mode = 0o644
            dest.addfile(info, io.BytesIO(body))
    write(report / ARCHIVE, gzip.compress(output.getvalue(), mtime=0))
    installed = sum((folder / name).stat().st_size for name in new)
    source_delta = sum(
        (folder / name).stat().st_size - sizes.get(name, 0) for name in new if name.endswith(".py")
    )
    save_json(
        report / FOOTPRINT,
        dict(
            base_asset_count=len(old),
            new_asset_count=len(new),
            unchanged_asset_count=len(old) - 1,
            base_app_bytes=sum(sizes[name] for name in old),
            new_app_bytes=installed,
            added_app_bytes=installed - sum(sizes[name] for name in old),
            added_python_bytes=source_delta,
            new_native_bytes=sum(
                (folder / "capture/mode_assets" / name).stat().st_size
                for name in (trial.NATIVE, trial.CORE)
            ),
            base_archive_bytes=(trial.BASE / "portable-receiver.tar.gz").stat().st_size,
            new_archive_bytes=(report / ARCHIVE).stat().st_size,
            python_dep_list_identical=(
                (folder / "requirements.txt").read_bytes()
                == (trial.BASE / "requirements.txt").read_bytes()
            ),
            runtime_new_os_libraries=[],
            scope="Native libraries reuse the original Linux C and system FFTW dependencies.",
        ),
    )


def plot(report, legs):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig, (wall, rss) = plt.subplots(1, 2, figsize=(10.3, 4.9), layout="constrained")
    roles = ("reference", "relocated")
    color = ("#25547f", "#127b6e")
    ticks = sorted({r["id"] for r in legs})
    for index, role in enumerate(roles):
        label = "Hard source" if role == "reference" else "Relocated bundle"
        rows = [r for r in legs if r["role"] == role]
        where = [ticks.index(r["id"]) + (index - 0.5) * 0.32 for r in rows]
        wall.bar(where, [r["wall_s"] for r in rows], width=0.30, color=color[index], label=label)
        rss.bar(where, [r["peak_rss_kib"] / 1024 for r in rows], width=0.30, color=color[index])
    for ax, title, label in (
        (wall, "Elapsed host time", "Seconds"),
        (rss, "Peak process RSS", "MiB"),
    ):
        ax.set(xticks=range(len(ticks)), xticklabels=ticks, title=title, ylabel=label)
        ax.grid(axis="y", color="0.9", linewidth=0.7)
        ax.set_axisbelow(True)
    wall.legend(frameon=False)
    fig.suptitle("Staggered detector parity on 96 genuine saved visits")
    fig.savefig(report / PNG, dpi=155)
    fig.savefig(report / PDF, metadata={"CreationDate": None})
    plt.close(fig)


def publish(folder):
    report = trial.REPORT
    plan = whole_iq.read(report / "source-lock.json")
    whole_iq.checked(folder / "files.json", plan["package_sha256"])
    measured = whole_iq.read(report / "parity.json")
    if measured["identical_packets"] is not True or len(measured["cases"]) != 2:
        raise ValueError("the stage resource plot needs both measured parity witnesses")
    legs = [
        dict(id=r["id"], role=role, **value, **r["counts"])
        for r in measured["cases"]
        for role, value in r["timings"].items()
    ]
    package(folder, report)
    csv_file(report / TABLE, legs)
    plot(report, legs)
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="portable-staggered-mode-stage",
            title="Relocated staggered detector packet parity",
            sample="96 authenticated real visits across two paired recording subsets",
            boundary="Saved CI16 → packaged application detector or hard source → native packets",
            note=(
                "The relocated application and hard source return identical packet and RF selector "
                "digests. Each role measures one bounded replay including startup and decoding."
            ),
            seal="result-lock.json",
            image=PNG,
            pdf=PDF,
            csv=TABLE,
        ),
    )
    names = (
        ARCHIVE,
        FOOTPRINT,
        PNG,
        PDF,
        TABLE,
        "stage-figure.json",
        "parity.json",
        "source-lock.json",
        "PROTOCOL.md",
        "preflight.log",
        "preflight-source-lock.json",
        "native-build.json",
        "release-files.json",
        "USAGE.md",
        "preflight-resource-accounting.csv",
        "preflight-resource-source-lock.json",
    )
    save_json(
        report / "result-lock.json",
        dict(
            cases=[row["id"] for row in measured["cases"]],
            files={name: _sha(report / name) for name in names},
            scope="Detector parity and stage resources only",
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=local_output)
    publish(parser.parse_args().folder)
