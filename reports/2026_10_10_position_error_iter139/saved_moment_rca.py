"""Posthoc arithmetic on sealed summary only; no model or recording calls."""

import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    source = HERE / "summary.json"
    data = json.loads(source.read_text())
    result = dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), arms={})
    for arm in ("fitted-c", "zero-c"):
        rows, availability = [], {0: 0, 1: 0, 2: 0}
        groups = set()
        for member in data["members"]:
            for record in member["arms"][arm]["group_satellite_records"]:
                blocks = record["blocks"]
                availability[sum(b["mass"] > 0 for b in blocks)] += 1
                groups.add((member["label"], tuple(record["group"])))
                for i, target in enumerate(blocks):
                    if target["crossprediction_status"] != "available":
                        continue
                    train = blocks[1 - i]
                    mass = target["mass"]
                    within = (
                        target["weighted_product_sum"] - mass * target["mean_x"] * target["mean_y"]
                    )
                    shift = (
                        mass
                        * (target["mean_x"] - train["mean_x"])
                        * (target["mean_y"] - train["mean_y"])
                    )
                    centered = target["opposite_block_centered_product_sum"]
                    if not math.isclose(centered, within + shift, rel_tol=1e-10, abs_tol=1e-9):
                        raise ValueError("saved-moment identity failed")
                    rows.append(
                        dict(
                            label=member["label"],
                            group=record["group"],
                            satellite=record["satellite"],
                            block=i,
                            target_mass=mass,
                            training_mass=train["mass"],
                            log10_target_training_ratio=math.log10(mass)
                            - math.log10(train["mass"]),
                            target_means=[target["mean_x"], target["mean_y"]],
                            training_means=[train["mean_x"], train["mean_y"]],
                            raw=target["weighted_product_sum"],
                            centered=centered,
                            within=within,
                            mean_disagreement=shift,
                        )
                    )
        totals = {
            key: sum(r[key] for r in rows)
            for key in ("target_mass", "raw", "centered", "within", "mean_disagreement")
        }
        tiny = [r for r in rows if r["training_mass"] < 1e-12]
        ranked = sorted(rows, key=lambda r: r["centered"], reverse=True)
        result["arms"][arm] = dict(
            totals=totals,
            per_eligible_mass={
                k: totals[k] / totals["target_mass"]
                for k in ("raw", "centered", "within", "mean_disagreement")
            },
            groups=len(groups),
            group_satellite_records=sum(availability.values()),
            records_by_positive_block_count=availability,
            eligible_blocks=len(rows),
            posthoc_training_mass_below_1e_12=dict(
                blocks=len(tiny),
                target_mass=sum(r["target_mass"] for r in tiny),
                centered=sum(r["centered"] for r in tiny),
            ),
            top_positive_centered=ranked[:10],
            positive_top_sums={
                str(k): sum(r["centered"] for r in ranked[:k]) for k in (1, 5, 10, 20)
            },
            caution="Posthoc diagnostic only; no primary filtering or covariance claim",
        )
    (HERE / "RCA.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), constrained_layout=True)
    for ax, (arm, value) in zip(axes, result["arms"].items(), strict=True):
        top = value["top_positive_centered"]
        ax.bar(range(len(top)), [r["centered"] for r in top], label="Cross-block centered")
        ax.scatter(
            range(len(top)), [r["raw"] for r in top], color="black", label="Original raw product"
        )
        ax.set_xticks(
            range(len(top)),
            [f"{r['label']}\n{r['satellite']} b{r['block']}" for r in top],
            rotation=30,
            ha="right",
        )
        ax.set_ylabel("Signed product sum")
        ax.set_title(arm + ": ten largest positive contributions (posthoc)")
        ax.legend()
    fig.suptitle(
        "Tiny training mass can produce large mean-prediction errors; no covariance estimate"
    )
    fig.savefig(HERE / "saved-moment-rca.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
