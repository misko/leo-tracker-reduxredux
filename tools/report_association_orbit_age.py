"""Describe orbit epoch ages and a controlled reassociation example; no new fitting."""

import argparse
import json
from pathlib import Path

import numpy as np
from replay_regional_doppler import digest, load_observations, state_arrays, write_json

from leo.analysis.research.regional_doppler import Region, ScoreConfig, score_states
from leo.sky.propagation import parse_element_sets


def bin_age(hours):
    if hours < 0:
        return "After capture"
    for limit, label in [
        (3, "0–3 h"),
        (6, "3–6 h"),
        (12, "6–12 h"),
        (24, "12–24 h"),
        (48, "24–48 h"),
        (72, "48–72 h"),
    ]:
        if hours < limit:
            return label
    return "≥72 h"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["reranking", "orbit-audit", "inference", "evidence", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    a.output.mkdir(exist_ok=False)
    rerank = json.loads(a.reranking.read_text())
    audit = json.loads(a.orbit_audit.read_text())
    inference = json.loads(a.inference.read_text())
    if (
        rerank["parent_digest"] != audit["assignments_digest"]
        or rerank["parent_digest"] != inference["parent_digest"]
    ):
        raise ValueError("parent mismatch")
    lookup = {(r["session_id"], r["episode_id"]): r for r in audit["rows"]}
    rows = []
    for r in rerank["rows"]:
        orbit = lookup[(r["session_id"], r["episode_id"])]
        if r["norad"] != orbit["norad"]:
            raise ValueError("original identity mismatch")
        final = parse_element_sets(r["winning_tle_text"])
        if final.satellite_numbers != (r["best_norad"],):
            raise ValueError("winning identity mismatch")
        t = orbit["measurement_utc_ns"]
        rows.append(
            dict(
                session_id=r["session_id"],
                episode_id=r["episode_id"],
                original_norad=r["norad"],
                final_norad=r["best_norad"],
                changed=r["norad"] != r["best_norad"],
                observations=r["observations"],
                capture_utc_ns=t,
                original_age_h=(t - orbit["nominal_epoch_utc_ns"]) / 3.6e12,
                updated_original_age_h=(t - orbit["selected"]["epoch_utc_ns"]) / 3.6e12,
                final_age_h=(t - final.element_epoch_utc_ns()[0]) / 3.6e12,
            )
        )
    labels = ["After capture", "0–3 h", "3–6 h", "6–12 h", "12–24 h", "24–48 h", "48–72 h", "≥72 h"]
    bins = []
    for label in labels:
        bins.append(
            dict(
                age=label,
                original=sum(bin_age(r["original_age_h"]) == label for r in rows),
                updated_same_identity=sum(
                    bin_age(r["updated_original_age_h"]) == label for r in rows
                ),
                final=sum(bin_age(r["final_age_h"]) == label for r in rows),
                changed_original=sum(
                    r["changed"] and bin_age(r["original_age_h"]) == label for r in rows
                ),
            )
        )
    # Controlled example: same position, samples and partitions for all three hypotheses.
    example = rerank["rows"][0]
    orbit = lookup[(example["session_id"], example["episode_id"])]
    doc = json.loads((a.evidence / "evidence" / (example["session_id"] + ".json")).read_text())
    arc = dict(load_observations(doc, 0))[example["episode_id"]]
    meta = doc["inventory"]
    original_path = a.evidence / "evidence" / meta["tle_file"]
    if digest(original_path) != meta["tle_digest"]:
        raise ValueError("original catalogue mismatch")
    original = parse_element_sets(original_path.read_text())
    model = next(
        m for m in inference["models"] if m["selection"] == "all" and not m["clock_fitted"]
    )
    region = Region(model["latitude_deg"], model["longitude_deg"], 1, 1)
    grid = region.points([0], [0])
    comparisons = []
    for label, cat, norad in [
        ("Original orbit / original identity", original, example["norad"]),
        (
            "Updated orbit / original identity",
            parse_element_sets(orbit["selected"]["text"]),
            example["norad"],
        ),
        (
            "Updated orbit / reassociated identity",
            parse_element_sets(example["winning_tle_text"]),
            example["best_norad"],
        ),
    ]:
        index = cat.satellite_numbers.index(norad)
        pp, vv, ids = state_arrays(cat, [index], meta["reference_utc_ns"], arc.time_s)
        if len(ids) != 1:
            raise ValueError("invalid example propagation")
        score = score_states(arc, pp, vv, grid, 1, ScoreConfig())
        comparisons.append(
            dict(
                stage=label,
                norad=norad,
                age_h=(meta["reference_utc_ns"] - cat.element_epoch_utc_ns()[index]) / 3.6e12,
                train_rms_hz=float(score["best_train_rms_hz"][0]),
                heldout_rms_hz=float(score["best_test_rms_hz"][0]),
            )
        )
    output = dict(
        reranking_digest=digest(a.reranking),
        audit_digest=digest(a.orbit_audit),
        inference_digest=digest(a.inference),
        association_count=len(rows),
        changed=sum(r["changed"] for r in rows),
        observations=sum(r["observations"] for r in rows),
        bins=bins,
        rows=rows,
        median_original_age_h=float(np.median([r["original_age_h"] for r in rows])),
        median_final_absolute_age_h=float(np.median([abs(r["final_age_h"]) for r in rows])),
        example_session=example["session_id"],
        example_observations=example["observations"],
        example=comparisons,
    )
    write_json(a.output / "distribution.json", output)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(15, 5), layout="constrained")
    x = np.arange(len(labels))
    for offset, key, title, color in [
        (-0.2, "original", "Original identities / original elements", "tab:blue"),
        (0.2, "final", "Final identities / nearest-epoch elements", "tab:orange"),
    ]:
        bars = axes[0].bar(x + offset, [r[key] for r in bins], 0.4, label=title, color=color)
        axes[0].bar_label(bars, fontsize=8)
    axes[0].set(
        xticks=x,
        xticklabels=labels,
        ylabel="Track associations (622 in each series)",
        title="TLE epoch age at capture",
    )
    axes[0].tick_params(axis="x", rotation=35)
    axes[0].legend(fontsize=8)
    base = [r["original"] for r in bins][1:]
    changed = [r["changed_original"] for r in bins][1:]
    axes[1].bar(np.arange(7), np.array(base) - changed, label="Identity unchanged")
    axes[1].bar(np.arange(7), changed, bottom=np.array(base) - changed, label="Identity changed")
    axes[1].set(
        xticks=np.arange(7),
        xticklabels=labels[1:],
        ylabel="Track associations",
        title="Which original age groups changed identity?",
    )
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
    fig.suptitle(
        "Association-weighted orbit age; no tracks removed or age-weighted\n"
        "Negative age means epoch after capture, not necessarily publication time"
    )
    fig.savefig(a.output / "orbit-age.png", dpi=160)
    plt.close(fig)
    print(json.dumps({k: v for k, v in output.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
