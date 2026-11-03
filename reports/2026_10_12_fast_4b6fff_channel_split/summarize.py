"""Validate matched replay settings and export a compact scientific comparison."""
import csv
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

from leo.analysis.regional_position_score import coordinates
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

ROOT = Path(__file__).resolve().parent
CASES = ("ch1-4", "ch5-8", "ch1-8")


def distance(a, b):
    lat, lon, ref_lat, ref_lon = map(math.radians, (*a, *b))
    h = math.sin((lat-ref_lat)/2)**2 + math.cos(lat)*math.cos(ref_lat)*math.sin((lon-ref_lon)/2)**2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1, max(0, h))))


def main():
    documents = {case: json.loads((ROOT/case/"regional.json").read_text()) for case in CASES}
    published = json.loads((ROOT/"input/published-regional.json").read_text())
    baseline = documents["ch1-8"]
    for doc in documents.values():
        assert doc["configuration_sha256"] == baseline["configuration_sha256"]
        assert doc["diagnostics"]["snapshot_sha256"] == baseline["diagnostics"]["snapshot_sha256"]
        assert doc["diagnostics"]["bank"]["retained_numbers"] == baseline["diagnostics"]["bank"]["retained_numbers"]
        assert doc["known_position_used_for_inference"] is False
        assert doc["position_fix_claimed"] is False
    reference = (baseline["reference_latitude_deg"], baseline["reference_longitude_deg"])
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(baseline["diagnostics"]["snapshot_collected_utc_ns"] + 1)
    assert snapshot.digest == baseline["diagnostics"]["snapshot_sha256"]
    catalogue = parse_element_sets(archive.read(snapshot))
    names = dict(zip(map(int, catalogue.satellite_numbers), catalogue.names))
    rows, ablation = [], []
    selected = {}
    for case, doc in {**documents, "published-ch1-8": published}.items():
        for method in doc["methods"]:
            for arm in method["arms"]:
                fit = arm["selected"]
                if fit is None:
                    rows.append(dict(case=case, arm=arm["name"], state="insufficient", reasons=arm["reasons"]))
                    continue
                row = {k: v for k, v in fit.items() if k != "joint_state"}
                row.update(case=case, arm=arm["name"], windows=doc["windows"], satellite_count=len(fit["satellites"]))
                rows.append(row)
                selected[case, arm["name"]] = row
        # B4W holds the RF-time terms fixed in both arms, isolating static c.
        attempts = doc["diagnostics"].get("b7", {}).get("attempts", {})
        for stage in ("B3", "B4", "B4W"):
            fits = attempts.get(stage, {})
            if all(arm in fits for arm in ("fitted-c", "zero-c")):
                assert len(fits["fitted-c"]["vector"]) == len(fits["zero-c"]["vector"])
                assert fits["zero-c"]["vector"][6] == 0
                for arm, fit in fits.items():
                    latlon = coordinates(RegionalPrior(), fit["vector"][:2])
                    ablation.append(dict(case=case, stage=stage, arm=arm,
                        latitude_deg=latlon[0], longitude_deg=latlon[1],
                        reference_error_m=distance(latlon, reference),
                        posterior_rms_hz=fit["posterior_rms_hz"], objective=fit["objective"],
                        coefficient_hz_per_ghz=fit["vector"][6], converged=fit["converged"]))
    comparisons = []
    for case in ("ch1-4", "ch5-8", "published-ch1-8"):
        for arm in ("fitted-c", "zero-c"):
            a, b = selected.get((case, arm)), selected.get(("ch1-8", arm))
            if a is None or b is None:
                continue
            sa, sb = set(a["satellites"]), set(b["satellites"])
            comparisons.append(dict(case=case, arm=arm,
                displacement_from_full_m=distance((a["latitude_deg"], a["longitude_deg"]),
                                                  (b["latitude_deg"], b["longitude_deg"])),
                shared_satellites=sorted(sa & sb), subset_only_satellites=sorted(sa - sb),
                full_only_satellites=sorted(sb - sa)))
    result = dict(session_id=baseline["session_id"], reference=reference,
        configuration_sha256=baseline["configuration_sha256"],
        tle_sha256=baseline["diagnostics"]["snapshot_sha256"],
        matched_candidate_bank_count=len(baseline["diagnostics"]["bank"]["retained_numbers"]),
        final_estimates=rows, controlled_c_ablation=ablation, comparisons=comparisons,
        interpretation={
            "association": "Satellite sets are candidate associations, not established identities. Associated-window counts describe upstream selection; later timing pruning may remove satellites.",
            "accuracy": "Errors are relative to the pipeline's configured receiver reference, used only for evaluation.",
            "c_control": "B3/B4/B4W share observations, fitted-c upstream calibration and association, priors and search budgets within each channel set. This isolates downstream static c, not the complete calibration pipeline.",
            "final_arms": "B7 fitted-c also enables RF-time terms; use the B4W rows for the static-c controlled comparison.",
            "scores": "Absolute objectives across channel subsets have different observation counts and are not directly comparable."})
    (ROOT/"comparison.json").write_text(json.dumps(result, indent=2)+"\n")
    columns = ["case", "arm", "accepted_stage", "windows", "associated_windows", "satellite_count",
               "latitude_deg", "longitude_deg", "horizontal_error_m", "posterior_rms_hz", "coefficient_hz_per_ghz"]
    with (ROOT/"estimates.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    with (ROOT/"satellite-associations.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=["catalog_number", "name", *CASES, "published-ch1-8"])
        writer.writeheader()
        inventory = sorted({n for row in rows if row["arm"] == "fitted-c" for n in row.get("satellites", [])})
        for number in inventory:
            writer.writerow(dict(catalog_number=number, name=names.get(number, ""),
                **{case: number in selected.get((case, "fitted-c"), {}).get("satellites", [])
                   for case in (*CASES, "published-ch1-8")}))
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.7), layout="constrained")
    colors = ["#2678b8", "#e58b26", "#269b70"]
    for i, case in enumerate(CASES):
        a = selected.get((case, "fitted-c"))
        b = selected.get((case, "zero-c"))
        if a:
            axes[0].scatter(a["longitude_deg"], a["latitude_deg"], c=colors[i], s=65, label=case.upper())
        if b:
            axes[0].scatter(b["longitude_deg"], b["latitude_deg"], edgecolors=colors[i], facecolors="none", s=65)
        for fit, offset, alpha in ((a, -.18, 1), (b, .18, .4)):
            if fit:
                bars = axes[1].bar(i+offset, fit["horizontal_error_m"]/1000, width=.34, color=colors[i], alpha=alpha)
                axes[1].bar_label(bars, fmt="%.2f", padding=3, fontsize=8)
                bars = axes[2].bar(i+offset, fit["posterior_rms_hz"], width=.34, color=colors[i], alpha=alpha)
                axes[2].bar_label(bars, fmt="%.1f", padding=3, fontsize=8)
    axes[0].scatter(reference[1], reference[0], marker="*", s=130, c="black", label="Reference")
    axes[0].set(xlabel="Longitude (deg)", ylabel="Latitude (deg)", title="Regional position estimates")
    axes[0].legend(fontsize=8)
    axes[0].xaxis.set_major_locator(MaxNLocator(4))
    axes[1].set(ylabel="Distance to reference (km)", title="Position accuracy")
    axes[2].set(ylabel="Posterior RMS (Hz)", title="In-sample frequency fit")
    for ax in axes[1:]:
        ax.set_xticks(range(3), [c.upper() for c in CASES])
    for ax in axes:
        ax.grid(alpha=.2)
        ax.set_axisbelow(True)
    fig.suptitle("fast-4b6fff: channel subset comparison\nSolid: fitted-c; open/faded: zero-c. Final selected models; candidate-only.", fontsize=12)
    fig.savefig(ROOT/"comparison.png", dpi=170)
    print(json.dumps({"estimates": [{k:r.get(k) for k in columns} for r in rows],
                      "comparisons": comparisons, "B4W": [a for a in ablation if a["stage"] == "B4W"]}, indent=2))


if __name__ == "__main__":
    main()
