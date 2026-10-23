"""Audit exported multi-lane fits and run matched fixed-calibration time controls."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from compare_dsx01_graph_receivers import ROOT, load_tracks, predict, write_csv
from numpy.polynomial import legendre as leg
from prototype_multilane_tracklets import (
    OUTPUT,
    PERIOD,
    group,
    nuisance,
    observation_arrays,
    ratio,
    save_figure,
    stitch,
)


def shift_lanes(tracks, seed):
    rng = np.random.default_rng(seed)
    shifts = {(rx, ch): float(rng.uniform(30, 270)) for rx in (1, 2) for ch in range(1, 9)}
    result = []
    for original in tracks:
        shift = shifts[original["receiver"], original["channel"]]
        for segment, amount in enumerate((shift, shift - 300)):
            times = original["times"] + amount
            keep = (times >= 0) & (times < 300)
            if not keep.any():
                continue
            track = copy.deepcopy(original)
            track["key"] += f"-C{segment}"
            track["times"] = times[keep]
            track["values"] = original["values"][keep]
            track["observation_ids"] = [
                oid for oid, ok in zip(original["observation_ids"], keep, strict=True) if ok
            ]
            track["start_s"] = max(0.0, original["start_s"] + amount)
            track["end_s"] = min(300.0, original["end_s"] + amount)
            pieces = []
            for piece in track["pieces"]:
                piece["start_s"] = max(0.0, piece["start_s"] + amount)
                piece["end_s"] = min(300.0, piece["end_s"] + amount)
                piece["reference_time_s"] += amount
                if piece["end_s"] >= piece["start_s"]:
                    pieces.append(piece)
            track["pieces"] = pieces
            np.testing.assert_allclose(
                track["values"] - predict(track, track["times"]),
                original["values"][keep] - predict(original, original["times"][keep]),
                atol=1e-5,
            )
            result.append(track)
    assert Counter(oid for t in result for oid in t["observation_ids"]) == Counter(
        oid for t in tracks for oid in t["observation_ids"]
    )
    return result


def audit_and_export(tracks, item):
    mapping = {t["key"]: t for t in tracks}
    result, beta, scaled = item["result"], np.array(item["calibration"]["beta"]), item["scaled"]
    owners = result["ownership"]
    assert set(owners) == set(mapping)
    assert len(set(owners.values())) == result["output_tracks"]
    assert result["input_tracks"] - len(result["accepted_edges"]) == result["output_tracks"]
    fits = {owners[next(iter(f["members"]))]: f for f in result["merged_groups"]}
    output, seen = [], set()
    for owner, fit in fits.items():
        assert {owners[k] for k in fit["members"]} == {owner}
        a = observation_arrays(fit["members"], mapping, beta, scaled)
        assert not seen.intersection(a["ids"])
        seen.update(a["ids"])
        expected = leg.legval(
            (a["t"] - fit["reference_time_s"]) / fit["time_scale_s"], fit["coefficients_hz"]
        )
        residual = a["y"] - a["q"] * expected
        assert len(a["t"]) == fit["points"]
        assert max(abs(residual)) < 450 and np.max(np.diff(a["t"])) <= 10
        np.testing.assert_allclose(np.sqrt(np.mean(residual**2)), fit["rms_hz"], atol=1e-7)
        assert 0 <= fit["degree"] <= 4
        assert not any(d["flags"] for d in fit["diagnostics"].values())
        d = leg.legder(fit["coefficients_hz"])
        z = leg.legroots(leg.legder(d)) if fit["degree"] > 1 else np.array([])
        z = np.real(z[np.isreal(z)])
        z = np.r_[-1.0, 1.0, z[(z >= -1) & (z <= 1)]]
        for key, lift in fit["members"].items():
            track = mapping[key]
            assert isinstance(lift, int)
            slopes = ratio(track, scaled) * leg.legval(z, d) / fit["time_scale_s"]
            slopes += beta[group(track) + 4] / 150
            assert max(abs(slopes)) <= 8000
    cal_groups = {g["group"]: g for g in item["calibration"]["groups"]}
    for key, track in mapping.items():
        owner = owners[key]
        fit = fits.get(owner)
        lift = fit["members"][key] if fit else 0
        q = ratio(track, scaled)
        corrected = track["values"] + lift * PERIOD - nuisance(track, track["times"], beta)
        residual = track["values"] - predict(track, track["times"])
        if fit:
            residual = corrected - q * leg.legval(
                (track["times"] - fit["reference_time_s"]) / fit["time_scale_s"],
                fit["coefficients_hz"],
            )
        for i, oid in enumerate(track["observation_ids"]):
            output.append(
                {
                    "source_id": track["source_id"],
                    "observation_id": oid,
                    "receiver": track["receiver"],
                    "channel": track["channel"],
                    "time_s": track["times"][i],
                    "original_track": key,
                    "component": owner,
                    "additional_native_alias_lift": lift,
                    "rf_ratio": q,
                    "reference_cfo_hz": corrected[i] / q,
                    "residual_native_hz": residual[i],
                    "merged": bool(fit),
                    "fully_supported_group": bool(fit and fit["fully_supported"]),
                    "calibration_supported": cal_groups[group(track)]["calibration_supported"],
                }
            )
    assert len(output) == len({r["observation_id"] for r in output})
    return output


def main():
    tracks, _ = load_tracks()
    summary = json.loads((OUTPUT / "summary.json").read_text())
    for name, value in {**summary["input_sha256"], **summary["source_sha256"]}.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value, name
    controls, totals = [], []
    for method in ("direct_cfo", "rf_scaled"):
        all_rows = []
        for source in (f"S{i:02}" for i in range(1, 6)):
            scan = [t for t in tracks if t["source_id"] == source]
            directory = OUTPUT / method / source
            item = json.loads((directory / "results.json").read_text())
            exported = audit_and_export(scan, item)
            all_rows.extend(exported)
            write_csv(directory / "observations.csv", exported)
            for seed in (41, 142, 243):
                shifted = shift_lanes(scan, seed)
                eligible = [t for t in shifted if len(t["times"]) >= 8]
                result = stitch(eligible, item["calibration"], item["scaled"])
                control_dir = OUTPUT / "controls"
                control_dir.mkdir(exist_ok=True)
                (control_dir / f"{method}-{source}-{seed}.json").write_text(
                    json.dumps(result, indent=2) + "\n"
                )
                controls.append(
                    {
                        "method": method,
                        "source_id": source,
                        "seed": seed,
                        "eligible_observations": result["associated_points"],
                        "boundary_observations_excluded": len(exported)
                        - result["associated_points"],
                        "links": len(result["accepted_edges"]),
                        "overlap_links": sum(
                            e["kind"] == "overlap" for e in result["accepted_edges"]
                        ),
                        "sequential_links": sum(
                            e["kind"] == "sequential" for e in result["accepted_edges"]
                        ),
                        "three_lane_groups": sum(
                            len(g["diagnostics"]) >= 4 for g in result["merged_groups"]
                        ),
                        "supported_three_lane_groups": sum(
                            len(g["diagnostics"]) >= 4 and g["fully_supported"]
                            for g in result["merged_groups"]
                        ),
                        "fully_supported_groups": sum(
                            g["fully_supported"] for g in result["merged_groups"]
                        ),
                        "merged_points": sum(g["points"] for g in result["merged_groups"]),
                    }
                )
        assert len(all_rows) == len({r["observation_id"] for r in all_rows}) == 18338
        write_csv(OUTPUT / method / "all-observations.csv", all_rows)
        for seed in (41, 142, 243):
            matched = [c for c in controls if c["method"] == method and c["seed"] == seed]
            totals.append(
                {
                    "method": method,
                    "seed": seed,
                    **{
                        k: sum(c[k] for c in matched)
                        for k in (
                            "eligible_observations",
                            "boundary_observations_excluded",
                            "links",
                            "overlap_links",
                            "sequential_links",
                            "three_lane_groups",
                            "supported_three_lane_groups",
                            "fully_supported_groups",
                            "merged_points",
                        )
                    },
                }
            )
    write_csv(OUTPUT / "temporal-controls.csv", controls)
    write_csv(OUTPUT / "temporal-control-totals.csv", totals)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), constrained_layout=True)
    labels = ["Original Graph", "Same-channel RX", "Any lane: direct CFO", "Any lane: RF scaled"]
    values = [676, 645] + [r["output_tracks"] for r in summary["aggregate"]]
    axes[0].bar(range(4), values, color=["#aaaaaa", "#8ab4bd", "#d2a468", "#3b7fa3"])
    axes[0].set(xticks=range(4), xticklabels=labels, ylabel="Candidate components")
    axes[0].tick_params(axis="x", rotation=25)
    for i, value in enumerate(values):
        axes[0].text(i, value + 4, str(value), ha="center")
    for method, color in (("direct_cfo", "#d2a468"), ("rf_scaled", "#3b7fa3")):
        offset = -0.18 if method == "direct_cfo" else 0.18
        group_rows = [r for r in summary["per_scan"] if r["method"] == method]
        axes[1].bar(
            np.arange(5) + offset,
            [r["output_tracks"] for r in group_rows],
            width=0.36,
            color=color,
            label=method,
        )
    axes[1].set(
        xticks=range(5), xticklabels=[f"S{i:02}" for i in range(1, 6)], ylabel="Components per scan"
    )
    axes[1].legend()
    for i, row in enumerate(summary["aggregate"]):
        axes[2].bar(i, row["mean_points_per_track"], color=["#d2a468", "#3b7fa3"][i])
        axes[2].text(
            i,
            row["mean_points_per_track"] + 0.5,
            f"{row['mean_points_per_track']:.2f}",
            ha="center",
        )
    axes[2].set(
        xticks=(0, 1), xticklabels=("Direct CFO", "RF scaled"), ylabel="Mean GLRT points/component"
    )
    fig.suptitle(
        "DSX01 any-lane prototype · association unchanged at 18,338 / 20,084 (91.31%)\n"
        "Counts include provisional groups; tracklet fusion does not establish unique spacecraft"
    )
    save_figure(fig, OUTPUT, "comparison")
    receipt = {
        "real_result_sets_audited": 10,
        "observations_per_method": 18338,
        "unchanged_unassociated": 1746,
        "fixed_calibration_control_runs": len(controls),
        "control_summary": totals,
        "checks": "Original observation identities, exclusive ownership, native-Hz alias lifts, "
        "RF scaling, point gate, RMS, analytic slope, gaps, degree, "
        "stored residual flags, source/input hashes.",
        "validation_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (OUTPUT / "validation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
