"""Score the frozen physical-antenna retry schedules and render their paired roof trials."""

import argparse
import csv

from ..__main__ import local_output, save_json
from . import retry_cadence_trial as trial
from .bracketed_position_results import scientific
from .complete_detector_roster import BINDINGS, SCREEN
from .fresh_replay_results import geographic, sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .screening_figures import generate
from .whole_pressure_trial import rows_from

PRIMARY = {
    trial.LOWER: (trial.PARENTS[trial.LOWER][3], "original_capture_primary12_complete_factors"),
    trial.UPPER: (
        "ac5093de7de6317a595431049f698c244bfbfd5c9c3f92514d6e02d9a9ab0f3f",
        "upper_original_primary12_complete_factors",
    ),
}
LABELS = {
    "miss": "Wait after a failed retry",
    "hit": "Wait after a successful retry",
    "oracle": "Known successful retries only",
    "full": "Run every eligible retry",
    "primary": "Skip all retries",
    "miss_control": "Same count per antenna and RF",
    "hit_control": "Same count per antenna and RF",
}
POS = "decisions.jsonl.gz"


def assembled(out):
    sealed(out, "prediction-lock.json")
    rows = rows_from(out / "positions.jsonl.gz")
    for ident, (pin, method) in PRIMARY.items():
        path = SCREEN / trial.PARENTS[ident][2]
        sealed(path, "prediction-lock.json", pin)
        (primary,) = [r for r in rows_from(path / "positions.jsonl.gz") if r["method"] == method]
        (full,) = [r for r in rows if r["id"] == ident and r["policy"] == "full"]
        if primary["id"] != ident or any(primary[k] != full[k] for k in BINDINGS):
            raise ValueError("the primary-only reference uses a different physical recording")
        rows.append(
            dict(primary, cohort="primary only", policy="primary", method="cadence_primary")
        )
    expected = {(ident, policy) for ident in PRIMARY for policy in LABELS}
    if len(rows) != len(expected) or {(r["id"], r["policy"]) for r in rows} != expected:
        raise ValueError("incomplete retry policy by recording comparison")
    return sorted(rows, key=lambda r: (r["id"], r["policy"]))


def stage(out):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    with (out / "support.csv").open(newline="") as f:
        support = list(csv.DictReader(f))
    policies = ("miss", "miss_control", "hit", "hit_control", "oracle")
    colors = ("#087664", "#83909c", "#a45b23", "#83909c", "#4b5080")
    labels = (
        "Wait after failure",
        "Matched count",
        "Wait after success",
        "Matched count",
        "Oracle",
    )
    with plt.rc_context({"axes.spines.right": False, "axes.spines.top": False}):
        fig, axes = plt.subplots(1, 2, figsize=(10, 4.1), sharey=True)
        for ax, ident in zip(axes, PRIMARY, strict=True):
            rows = {r["policy"]: r for r in support if r["id"] == ident}
            for i, (policy, color) in enumerate(zip(policies, colors, strict=True)):
                r = rows[policy]
                attempted = int(r["executed"]) / int(r["opportunities"])
                retained = int(r["retained_rescues"]) / int(r["original_rescues"])
                ax.barh(i + 0.16, 100 * attempted, height=0.28, color=color, alpha=0.30)
                ax.barh(i - 0.16, 100 * retained, height=0.28, color=color)
            first = rows["miss"]
            ax.set_title(
                f"{ident}\n{first['opportunities']} eligible retries, "
                f"{first['original_rescues']} successful"
            )
            ax.set_xlim(0, 102)
            ax.set_yticks(range(len(labels)), labels)
            ax.set_xlabel("Fraction of the original count (%)")
            ax.grid(axis="x", alpha=0.16)
            ax.set_axisbelow(True)
        axes[0].invert_yaxis()
        fig.suptitle("Two seconds between wider antenna searches")
        fig.text(
            0.5,
            0.02,
            "Light bars show retries executed. Dark bars show successes retained.",
            ha="center",
        )
        fig.tight_layout(rect=(0.01, 0.07, 0.99, 0.93))
        fig.savefig(out / "stage.png", dpi=160)
        fig.savefig(out / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
        plt.close(fig)
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="peer-retry-cadence-support",
            title="Two seconds between wider antenna searches",
            boundary="Original primary packets to per-antenna retry opportunities",
            sample="Two complete same-roof recordings",
            note="Controls match counts per antenna and RF. The oracle knows future outcomes.",
            image="stage.png",
            pdf="stage.pdf",
            csv="support.csv",
            seal="stage-lock.json",
        ),
    )
    names = ("stage-figure.json", "stage.png", "stage.pdf", "support.csv", "schedule-lock.json")
    save_json(out / "stage-lock.json", dict(files={name: _sha(out / name) for name in names}))


def publish(out):
    rows = assembled(out)
    pack(out / POS, rows)
    names = (POS, "schedule-lock.json", "prediction-lock.json", "support.csv", "PROTOCOL.md")
    save_json(
        out / "figure-lock.json",
        dict(cases=list(PRIMARY), primary_parents=PRIMARY, files={n: _sha(out / n) for n in names}),
    )
    _, authority = held_references(None, tuple(PRIMARY))
    scores = geographic(rows, {r["id"]: r for r in authority})
    csv_file(out / "scores.csv", scores)
    times = []
    for r in rows:
        receipt = r.get("position_resources")
        if receipt:
            times.append(
                dict(
                    id=r["id"],
                    policy=r["policy"],
                    **{k: receipt[k] for k in ("wall_s", "cpu_s", "peak_bytes")},
                )
            )
    csv_file(out / "position-time.csv", times)
    by_id = {(r["id"], r["policy"]): scientific(r["result"]) for r in rows}
    save_json(
        out / "oracle-audit.json",
        {ident: by_id[ident, "oracle"] == by_id[ident, "full"] for ident in PRIMARY},
    )
    charts = []
    for policy in ("miss", "hit", "oracle"):
        methods = [("one", policy), ("stock", "full"), ("one_native_factors", "primary")]
        if policy != "oracle":
            methods.append(("all_visits", policy + "_control"))
        charts.append(
            dict(
                id="peer-retry-cadence-" + policy,
                method="cadence_" + policy,
                scope="roof",
                cases="sealed",
                seal="figure-lock.json",
                title=LABELS[policy],
                caption="Same original measurements, 25 km offer and causal orbital catalogue. "
                + (
                    "The oracle knows which retries will succeed."
                    if policy == "oracle"
                    else "Each antenna and RF has a two-second interval and equal-budget control."
                ),
                provenance=["schedule-lock.json", "prediction-lock.json", "support.csv"],
                series=[
                    dict(
                        key=k,
                        value="cadence_" + v,
                        label=LABELS[v],
                        file=POS,
                        native_field=BINDINGS[0],
                        match=BINDINGS,
                    )
                    for k, v in methods
                ],
            )
        )
    save_json(out / "figures.json", dict(version=2, charts=charts))
    stage(out)
    generate(out / "charts", evidence=out)
    names = (
        "figure-lock.json",
        "figures.json",
        "scores.csv",
        "position-time.csv",
        "oracle-audit.json",
    )
    save_json(out / "score-lock.json", dict(files={name: _sha(out / name) for name in names}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    publish(parser.parse_args().out)
