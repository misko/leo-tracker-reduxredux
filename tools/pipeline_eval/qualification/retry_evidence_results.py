"""Publish frozen retry decisions and fresh dual-calibration compact positions."""

import argparse
import gzip
from pathlib import Path

import matplotlib
import numpy as np

from ..__main__ import save_json, write
from ..scoring import ARMS, ROLES
from . import retry_evidence_position as position
from . import retry_evidence_trial as trial
from .capture_runtime import checked, read
from .capture_whole_results import MINIMAL, POS, generate, geographic, pack
from .full_held_scores import held_references
from .full_v5_check import _sha
from .prefix_figures import csv_file

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

METHODS = (trial.ALL, trial.SIGNAL, trial.CONTROL)
LABELS = ("Retry on every opportunity", "Signal rule", "Same-count time-spread")
CASES = (trial.CASE1, trial.CASE2)


def stage(output, rows):
    panels = ("development", "held", "transfer")
    labels = ("DS26 early\nDevelopment", "DS26 late\nHeld", "DS29\nTransfer")
    with plt.rc_context({"axes.spines.top": False, "axes.spines.right": False}):
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        fig.subplots_adjust(left=0.08, right=0.98, bottom=0.17, top=0.78, wspace=0.24)
        positions = np.arange(len(panels))
        for ax, metric, ylabel in zip(
            axes,
            ("attempts", "rescues"),
            ("Retry opportunities acted on (%)", "Rescues retained (%)"),
            strict=True,
        ):
            for index, (method, label, color) in enumerate(
                zip(METHODS, LABELS, ("#53648d", "#cc7856", "#39847f"), strict=True)
            ):
                selected = [
                    next(r for r in rows if r["phase"] == p and r["method"] == method)
                    for p in panels
                ]
                heights = [100 * r[metric] / r["all_" + metric] for r in selected]
                x = positions + 0.23 * (index - 1)
                ax.bar(x, heights, color=color, width=0.21, label=label)
                for ix, height, r in zip(x, heights, selected, strict=True):
                    ax.text(ix, height + 1.4, str(r[metric]), ha="center", fontsize=8)
            ax.set_xticks(positions, labels)
            ax.set_ylabel(ylabel)
            ax.set_ylim(0, 117)
            ax.set_axisbelow(True)
            ax.grid(axis="y", alpha=0.24)
        handles, legend_labels = axes[0].get_legend_handles_labels()
        fig.legend(
            handles,
            legend_labels,
            loc="upper center",
            bbox_to_anchor=(0.5, 0.91),
            ncols=3,
            frameon=False,
        )
        fig.suptitle("Using primary pilot evidence to choose 22-anchor retries", y=0.97)
        for suffix in ("png", "pdf"):
            fig.savefig(output / f"stage.{suffix}", dpi=170)
        plt.close(fig)


def audit_selection(group, output, decision_rows):
    selection = read(group / "selection.json")
    ident = selection["case"]
    for file, digest in selection["sources"].items():
        checked(Path(file), digest)
    authority = output / "receipts" / ident / "selection.json"
    files = [authority]
    parent = list(map(Path, selection["sources"]))
    if ident == trial.CASE2:
        primary = next(p for p in parent if p.name == "primary.json")
        conditional = next(p for p in parent if p.name == "measured.json")
        publication = primary.with_name("primary-lock.json")
        upper = read(publication)
        checked(primary, upper["primary_native_sha256"])
        sealed = checked(
            position.field.REPORT / "native.json.gz", upper["conditional_native_sha256"]
        )
        if (
            upper["case"] != ident
            or gzip.decompress(sealed.read_bytes()) != conditional.read_bytes()
        ):
            raise ValueError("prospective replay factors differ from its independent publication")
        destination = output / "receipts" / ident / "upstream-primary-lock.json"
        write(destination, publication.read_bytes())
        files.append(destination)
    for phase, modes in selection["splits"].items():
        baseline = modes[trial.ALL]
        all_rows = [
            r for r in selection["opportunities"] if trial.named(ident, r["visit"]) == phase
        ]
        if tuple(r["visit"] for r in all_rows) != tuple(baseline["ids"]):
            raise ValueError("the every-retry baseline omitted a physical opportunity")
        if modes[trial.SIGNAL]["attempts"] != modes[trial.CONTROL]["attempts"]:
            raise ValueError("frozen choices and independent control have different budgets")
        for method in METHODS:
            data = modes[method]
            flag = "signal" if method == trial.SIGNAL else method
            expected = [r for r in all_rows if method == trial.ALL or r[flag]]
            if ([r["visit"] for r in expected], sum(r["rescue"] for r in expected)) != (
                data["ids"],
                data["rescues"],
            ):
                raise ValueError("decision audit does not reproduce its selected rows")
            decision_rows.append(
                dict(
                    id=ident,
                    phase=phase,
                    method=method,
                    attempts=data["attempts"],
                    rescues=data["rescues"],
                    all_attempts=baseline["attempts"],
                    all_rescues=baseline["rescues"],
                    unsuccessful_attempts=data["attempts"] - data["rescues"],
                )
            )
    write(authority, (group / "selection.json").read_bytes())
    return files


def publish(work):
    output = trial.REPORT
    files, rows, decision_rows = [], [], []
    clocks = {}
    for ident in CASES:
        group = work / ident
        results, clocks[ident] = position.evidence(work, ident)
        rows.extend(results)
        files.extend(audit_selection(group, output, decision_rows))
        for mode in position.MODES:
            native = group / f"{mode}.json"
            destination = output / "factors" / f"{ident}-{mode}.json.gz"
            write(destination, gzip.compress(native.read_bytes(), compresslevel=5, mtime=0))
            files.append(destination)
        paths = [group / "source-lock.json"]
        paths.extend(p for p in sorted(group.glob("position-*/*")) if p.is_file())
        paths.extend(sorted(group.glob("position-*/recording/request.json")))
        for path in paths:
            dest = output / "receipts" / ident / path.relative_to(group)
            write(dest, path.read_bytes())
            files.append(dest)
    csv_file(output / "retry-outcomes.csv", decision_rows)
    save_json(output / "position-timings.json", clocks)
    pack(output / POS, rows)
    files.extend(
        output / name
        for name in (
            "policy-lock.json",
            "development-ladder.json",
            "PROTOCOL.md",
            "retry-outcomes.csv",
            "position-timings.json",
            POS,
        )
    )
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=list(CASES),
            files={str(p.relative_to(output)): _sha(p) for p in files},
            publication_source_sha256=_sha(Path(__file__)),
        ),
    )
    _, authority = held_references(None, CASES)
    refs = {row["id"]: row for row in authority}
    scores = geographic(rows, refs)
    csv_file(output / "scores.csv", scores)
    csv_file(
        output / "v5-controls.csv",
        [
            dict(
                id=ident,
                role=role,
                arm=arm,
                status=r["status"],
                error_km=r.get("error_km"),
                rf_rms_hz=r.get("rf_rms_hz"),
            )
            for ident in CASES
            for role in ROLES
            for arm in ARMS
            for r in [refs[ident]["reference"][role][arm]]
        ],
    )
    stage(output, decision_rows)
    save_json(
        output / "stage-figure.json",
        dict(
            id="pre-retry-pilot-evidence",
            title="Using primary pilot evidence to choose 22-anchor retries",
            image="stage.png",
            pdf="stage.pdf",
            csv="retry-outcomes.csv",
            version=1,
            seal="stage-lock.json",
            boundary="From two primary outputs to conditional retry decisions",
            sample="Two chronological DS26 blocks and one prospective DS29 transfer recording",
            note="Every attempt counts. The independent control matches the signal-rule budget.",
        ),
    )
    save_json(
        output / "stage-lock.json",
        dict(
            files={
                name: _sha(output / name)
                for name in ("stage.png", "stage.pdf", "stage-figure.json", "retry-outcomes.csv")
            }
        ),
    )
    save_json(
        output / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="pre-retry-pilot-evidence-position",
                    method=trial.SIGNAL,
                    scope="roof",
                    cases="sealed",
                    seal="prediction-lock.json",
                    title="Whole-recording position under selected anchor retries",
                    caption="Both calibration arms used the same original request, catalogue, "
                    "and search budget. "
                    "The every-opportunity comparator uses preexisting compact fits.",
                    provenance=["policy-lock.json", "retry-outcomes.csv", "position-timings.json"],
                    series=[
                        dict(
                            key=key,
                            file=POS,
                            value=method,
                            label=label,
                            native_field="paired_capture_sha256",
                            match=MINIMAL,
                        )
                        for key, method, label in zip(
                            ("stock", "one", "all_visits"), METHODS, LABELS, strict=True
                        )
                    ],
                )
            ],
        ),
    )
    generate(output / "charts", evidence=output)
    save_json(
        output / "score-lock.json",
        dict(
            prediction_lock_sha256=_sha(output / "prediction-lock.json"),
            files={
                name: _sha(output / name)
                for name in ("scores.csv", "v5-controls.csv", "figures.json")
            },
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    publish(parser.parse_args().work)
