"""Decompose the sealed oracle diagnostic; never feed it to blind fitting."""

import json

from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT


def contribution(row):
    return min(row["points"], 50) * (
        min(row["cost"] / row["points"], 36) if row["compatible"] else 36
    )


def run():
    source = ROOT / "reports/2026_10_18_s01_local_loss/warm_restart"
    output = ROOT / "reports/2026_10_18_dsx01_mill_valley_continuous"
    output.mkdir(exist_ok=True)
    results = {}
    for method in METHODS:
        for arm in ("c0", "fitted_c"):
            key = f"{arm}/{method}"
            before = json.loads((source / f"{method}_truth_all_tracks.json").read_text())[key]
            after = json.loads((source / f"{method}_endpoints.json").read_text())[key]
            a = {r["component"]: r for r in before["rows"] if r["active_curvature"]}
            b = {r["component"]: r for r in after["rows"] if r["active_curvature"]}
            categories = {
                k: 0.0
                for k in ("same_accepted", "newly_accepted", "newly_rejected", "both_rejected")
            }
            tracks = []
            for component, r in a.items():
                s = b[component]
                if s["compatible"]:
                    category = "same_accepted" if r["compatible"] else "newly_accepted"
                else:
                    category = "newly_rejected" if r["compatible"] else "both_rejected"
                delta = contribution(s) - contribution(r)
                categories[category] += delta
                tracks.append(
                    dict(
                        component=component,
                        category=category,
                        loss_delta=delta,
                        points=r["points"],
                        before_rms_hz=r["rms_hz"],
                        after_rms_hz=s["rms_hz"],
                        before_bias_hz=r["bias_hz"],
                        after_bias_hz=s["bias_hz"],
                        before_norad=r["candidate_norad"],
                        after_norad=s["candidate_norad"],
                    )
                )
            delta = after["score"] - before["score"]
            results[key] = dict(
                loss_delta=delta,
                categories=categories,
                prior_complexity_delta=delta - sum(categories.values()),
                tracks=sorted(tracks, key=lambda r: r["loss_delta"]),
                oracle_diagnostic_only=True,
                truth_used_to_select_neither_blind_labels_nor_blind_positions=True,
            )
    write(output / "oracle_gate_attribution.json", results)
    return results


if __name__ == "__main__":
    for key, value in run().items():
        print(key, value["loss_delta"], value["categories"])
