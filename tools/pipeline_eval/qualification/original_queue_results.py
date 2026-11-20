"""Score and plot the original-detector queue forecasts after the position jobs close."""

import argparse
import csv

from ..__main__ import local_output, save_json
from . import capture_whole, screening_figures
from . import original_queue_trial as trial
from . import scout_stage_figures as stage
from .fresh_replay_results import geographic, sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

LABELS = dict(trial.LABELS, oldest_rf="Least recently started RF")


def stage_plot(out):
    with (out / "timing.csv").open() as stream:
        data = list(csv.DictReader(stream))
    fig, (coverage, age) = stage.plt.subplots(1, 2, figsize=(12, 4.9), constrained_layout=True)
    colors = (stage.BASE, stage.DIAGNOSTIC, stage.CANDIDATE)
    for (name, label), color in zip(LABELS.items(), colors, strict=True):
        cases = [r for r in data if r["policy"] == name]
        workers = [int(r["workers"]) for r in cases]
        coverage.plot(
            workers,
            [100 * int(r["emitted"]) / int(r["valid"]) for r in cases],
            marker="o",
            label=label,
            color=color,
        )
        age.plot(
            workers,
            [float(r["due_to_output_p95_ms"]) / 1000 for r in cases],
            marker="o",
            label=label,
            color=color,
        )
    coverage.set(ylabel="Valid arrivals processed (%)", ylim=(0, 105))
    age.set(ylabel="95th percentile time to output (s)", ylim=(0, None))
    for ax in (coverage, age):
        ax.set(xlabel="Modeled parallel workers", xticks=(1, 2, 4, 8, 12))
        ax.grid(axis="y", alpha=0.22)
        ax.spines[["top", "right"]].set_visible(False)
    coverage.legend(loc="lower right", frameon=False)
    fig.suptitle(
        "Original detector capacity at the recorded DS29-0082 arrival times", fontweight="bold"
    )
    fig.savefig(out / "capacity.png", dpi=150, facecolor="white")
    fig.savefig(out / "capacity.pdf", facecolor="white", metadata={"CreationDate": None})
    stage.plt.close(fig)
    names = ("capacity.png", "capacity.pdf", "timing.csv", "forecast-lock.json")
    save_json(out / "stage-lock.json", dict(files={n: _sha(out / n) for n in names}))
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="original-queue-capacity",
            title="Modeled original detector throughput with one waiting slot",
            sample="4,868 valid of 6,772 original arrivals on DS29-0082",
            boundary="Recorded arrivals with measured per-visit dual-antenna detector CPU",
            note="Each worker sustains the measured host CPU rate. Output ages use processed "
            "windows. Coverage counts every valid arrival.",
            seal="stage-lock.json",
            image="capacity.png",
            pdf="capacity.pdf",
            csv="timing.csv",
        ),
    )


def score(out):
    lock = sealed(out, "prediction-lock.json")
    _, refs = held_references(None, lock["cases"])
    rows = rows_from(out / "positions.jsonl.gz")
    csv_file(out / "scores.csv", geographic(rows, {r["id"]: r for r in refs}))
    names = (
        "positions.jsonl.gz",
        "scores.csv",
        "timing.csv",
        "prediction-lock.json",
        "forecast-lock.json",
    )
    save_json(
        out / "figure-lock.json", dict(cases=lock["cases"], files={n: _sha(out / n) for n in names})
    )
    charts = []
    for workers in (1, 4):
        resource = "one worker" if workers == 1 else "four workers"
        items = [
            ("stock", capture_whole.METHOD, "Full original waveform measurement"),
            ("one", f"original_queue_oldest_rf-{workers}", LABELS["oldest_rf"]),
            ("one_native_factors", f"original_queue_fifo-{workers}", LABELS["fifo"]),
            ("all_visits", f"original_queue_latest-{workers}", LABELS["latest"]),
        ]
        charts.append(
            dict(
                id=f"original-queue-{workers}",
                method=items[1][1],
                scope="roof",
                cases="sealed",
                seal="figure-lock.json",
                title=f"Position from original GLRT admissions modeled on {resource}",
                caption="Measured detector CPU and original arrival clocks set admissions. "
                "The compact solver ran on the retained measured probes.",
                provenance=list(names[1:]),
                series=[
                    dict(
                        key=key,
                        label=label,
                        value=method,
                        file=names[0],
                        native_field="paired_capture_sha256",
                        match=[
                            "paired_capture_sha256",
                            "original_request_sha256",
                            "catalog_sha256",
                            "tile",
                        ],
                    )
                    for key, method, label in items
                ],
            )
        )
    save_json(out / "figures.json", dict(version=2, charts=charts))
    screening_figures.generate(out / "charts", evidence=out)
    stage_plot(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    score(parser.parse_args().out)
