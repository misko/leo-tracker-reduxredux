"""Compare frozen standard results with the new track pipeline, without refits.

The point populations match. Decision rules, orbit banks and fixed/blind position
conditions differ, so association counts are not an identity-accuracy benchmark.
"""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from localize_merged_track_catalogue import distance_km

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports/2026_10_16_dsx01_fast_association_losses"
NEW = ROOT / "reports/2026_10_17_ds22_merged_satellites"
PHASE = ROOT / "reports/2026_10_17_shared_satellite_phase"
OUTPUT = ROOT / "reports/2026_10_17_dsx01_pipeline_progress"
REFERENCE = (37.849061591561885, -122.48574968092912)


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def table(headers, rows):
    return "\n".join(
        ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        + ["| " + " | ".join(map(str, row)) + " |" for row in rows]
    )


def run():
    OUTPUT.mkdir(exist_ok=False)
    manifest = {r["path"]: r for r in read(BASE / "manifest.json")["files"]}
    checked = {}

    def verified(path):
        if path.is_relative_to(BASE):
            expected = manifest[str(path.relative_to(BASE))]
            assert digest(path) == expected["sha256"] and path.stat().st_size == expected["bytes"]
        checked[str(path.relative_to(ROOT))] = digest(path)
        return read(path)

    sources = verified(BASE / "sources.json")
    context_path = BASE / "context-observations.jsonl"
    assert digest(context_path) == manifest[context_path.name]["sha256"]
    checked[str(context_path.relative_to(ROOT))] = digest(context_path)
    context = [json.loads(line) for line in context_path.read_text().splitlines()]
    rows = []
    for source in sources:
        sid, case = source["source_id"], "DSX01-" + source["source_id"]
        raw = [r for r in context if r["source_id"] == sid]
        by_id = {r["observation_id"]: r for r in raw}
        assert len(raw) == len(by_id) == source["observation_count"]
        assert sum(r["original_associated"] for r in raw) == source["original_associated_count"]
        terminal_path = BASE / "evidence" / f"{sid}-terminal.json"
        terminal = verified(terminal_path)
        assert digest(terminal_path) == source["terminal_sha256"]
        assert terminal["position"] == source["original_position"]
        tracks = verified(NEW / "dsx01_adapter" / case / "tracks.json")
        merged = verified(NEW / "dsx01_adapter" / case / "merged.json")
        ids = [oid for t in tracks for oid in t["observation_ids"]]
        assert len(set(ids)) == len(ids) and set(ids) <= by_id.keys()
        for track in tracks:
            for oid, time_s, value in zip(
                track["observation_ids"], track["times"], track["values"], strict=True
            ):
                point = by_id[oid]
                assert (point["receiver"], point["channel"]) == (
                    track["receiver"],
                    track["channel"],
                )
                assert abs(time_s - point["time_s"]) < 1e-8
                difference = (value - point["measured_cfo_hz"] + 0.5 / 4.4e-6) % (1 / 4.4e-6)
                assert abs(difference - 0.5 / 4.4e-6) < 1e-5
        summary = verified(NEW / "dsx01_catalogue" / case / "bias_1000/summary.json")
        c0, fc = [
            next(r for r in summary if not r["grouped"] and r["fitted_c"] == c)
            for c in (False, True)
        ]
        assert c0["graph_points"] == fc["graph_points"] == len(ids)
        assert c0["position_error_km"] is None and fc["position_error_km"] is None
        consolidated = [
            verified(NEW / "dsx01_consolidated" / case / f"{variant}.json")
            for variant in ("c0", "fitted_c")
        ]
        assert [r["points"] for r in consolidated] == [
            c0["compatible_points"],
            fc["compatible_points"],
        ]
        position = terminal["position"]
        rows.append(
            dict(
                scan=sid,
                glrt_points=len(raw),
                standard_model=source["baseline_model_version"],
                standard_associated=source["original_associated_count"],
                standard_associated_percent=100 * source["original_associated_count"] / len(raw),
                standard_position_error_km=distance_km(
                    (position["latitude_deg"], position["longitude_deg"]), REFERENCE
                ),
                graph_points=len(ids),
                graph_percent=100 * len(ids) / len(raw),
                graph_fragments=len(tracks),
                polynomial_merged_tracks=merged["result"]["output_tracks"],
                new_fixed_gps_c0_points=c0["compatible_points"],
                new_fixed_gps_fitted_c_points=fc["compatible_points"],
                new_fixed_gps_fitted_c_percent=100 * fc["compatible_points"] / len(raw),
                new_fixed_gps_c0_tracks=consolidated[0]["output_tracks"],
                new_fixed_gps_fitted_c_tracks=consolidated[1]["output_tracks"],
                new_fixed_gps_fitted_c_points_per_track=fc["compatible_points"]
                / consolidated[1]["output_tracks"],
            )
        )
    assert sum(r["glrt_points"] for r in rows) == 20084
    assert sum(r["graph_points"] for r in rows) == 18338
    with (OUTPUT / "per-scan.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    pilots = []
    for directory in ("search", "search_resumed"):
        for path in sorted((PHASE / directory / "DSX01-S01").glob("*/evaluation.json")):
            evaluation = verified(path)
            assert digest(path.with_name("fit.json"))[7:] == evaluation["fit_sha256"]
            assoc = verified(path.with_name("association.json"))
            pilots.append(
                dict(
                    scan="S01",
                    variant=path.parent.name,
                    associated_points=assoc["compatible_points"],
                    all_glrt_percent=100 * assoc["compatible_points"] / rows[0]["glrt_points"],
                    position_error_km=evaluation["position_error_km"],
                )
            )
    totals = {
        key: sum(r[key] for r in rows)
        for key in (
            "glrt_points",
            "standard_associated",
            "graph_points",
            "graph_fragments",
            "polynomial_merged_tracks",
            "new_fixed_gps_c0_points",
            "new_fixed_gps_fitted_c_points",
        )
    }
    (OUTPUT / "results.json").write_text(
        json.dumps(
            dict(
                reference_latitude_longitude=REFERENCE,
                standard="frozen recorded shared-scan-q-v2",
                same_point_denominator=True,
                matched_algorithm_benchmark=False,
                new_all_scan_position_available=False,
                goal_complete=False,
                per_scan=rows,
                totals=totals,
                new_s01_blind_pilots=pilots,
                source_sha256=digest(Path(__file__)),
                verified_inputs=checked,
            ),
            indent=2,
        )
        + "\n"
    )
    summary = table(
        [
            "Scan",
            "GLRT points",
            "Graph tracked",
            "Standard satellite assoc.",
            "New fixed-GPS satellite compat. (fitted c)",
            "Standard position error km",
        ],
        [
            [
                r["scan"],
                r["glrt_points"],
                f"{r['graph_points']} ({r['graph_percent']:.1f}%)",
                f"{r['standard_associated']} ({r['standard_associated_percent']:.1f}%)",
                f"{r['new_fixed_gps_fitted_c_points']} "
                f"({r['new_fixed_gps_fitted_c_percent']:.1f}%)",
                f"{r['standard_position_error_km']:.3f}",
            ]
            for r in rows
        ],
    )
    pilot_table = table(
        ["S01 model", "Points / all GLRT (%)", "Blind position error km"],
        [
            [
                r["variant"],
                f"{r['associated_points']} ({r['all_glrt_percent']:.1f}%)",
                f"{r['position_error_km']:.3f}",
            ]
            for r in pilots
        ],
    )
    (OUTPUT / "README.md").write_text(f"""# DSX01 progress versus frozen standard analysis

The track builder covers91.3% of all20,084 GLRT winners; satellite association and
position accuracy remain unresolved. Standard results below are the recorded
shared-scan-q-v2 outputs frozen with DSX01, not a rerun of today's production code.
Every percentage uses the full original winning-GLRT population for that scan.
Standard terminal positions/hashes and original association flags were checked.
Every Graph observation ID, time, receiver/channel and native alias was checked
against that same frozen population. Ground truth is {REFERENCE}, assumed0m height.
Errors are horizontal great-circle distances, Earth radius6371.0088km.

{summary}

Graph tracked means assigned to a polynomial, not to an identified satellite.
The new all-five satellite column is the completed fragment-matching plus
lossless consolidation arm, with1000Hz Gaussian component constants and a
separate offset/drift for each scan/RX/band, using latest causal Space-Track TLEs.
Its position is FIXED at ground truth, with residual-structure gates. Standard
associations are posterior classifications at each standard estimated position.
The criteria, candidate ephemerides and fixed/blind conditions differ: this is
a progress inventory, not a controlled identity-accuracy or algorithm ranking.
Independent true satellite labels are unavailable.

The paired c0 arm admits3610 points versus3621 for fitted c:393/793/902/402/1120
versus393/793/913/402/1120 on S01–S05. Lossless candidate consolidation gives
21/36/41/19/49 fitted-c groups, averaging18.7/22.0/22.3/21.2/22.9points/group.
Polynomial pre-merging reduces676Graph fragments to456components and retains
their18338points, but hard pre-merging before satellite selection loses coverage.
The safer current path matches fragments, then joins compatible same-ID results.

## Newer S01 orbital-phase pilots

{pilot_table}

These are independent geographic searches with matched c arms. S02–S05 have
not yet received the newer phase model's blind searches; no missing error is zero.
The zero-phase control gives5.734/5.616km versus shared phase13.434/13.434km.
At the FIXED ground-truth location shared phase gives2181points(45.5% of4797),
or1975points(41.2%) with the tighter ±1Hz/s drift model. Fixed-site fit is not a
position estimate. Several drift limits remain active, flagging weak calibration.
No DSX01 scan has demonstrated the0.5km target in these new blind results.

## Active measurement investigation

Continuous known-pilot CFO was qualified on14/16DS22 and15/16DSX response-selected
points. Complete-track DS22 now evaluates602points, with515passing unchanged
estimator controls. These measurements have not entered the position results.
The complete-track DSX extension exposed11source-time joins outside the small
panel's0.51ms tolerance (rangeup to0.5205ms); it stopped before producing fits.
That provenance issue is being resolved rather than silently discarding points.
No source recording, production product, detection or original population changed.

![Stage coverage and standard position error](comparison.png)

The figure separates track coverage from satellite classification. CSV andJSON
provide all counts, consolidated-track statistics, source bindings and errors.
Full137-member DS22 fixed-site coverage is complete in the physical-model report;
blind accuracy remains evaluated on pilots, not the whole DS22 population.
""")
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2), constrained_layout=True)
    names, y = [r["scan"] for r in rows], np.arange(5)
    axes[0].barh(y, [r["graph_percent"] for r in rows], color="#2688b8")
    axes[0].set(title="Assigned to polynomial tracks", xlim=(0, 100), xlabel="% of all GLRT points")
    axes[1].barh(
        y - 0.17,
        [r["standard_associated_percent"] for r in rows],
        height=0.32,
        label="Standard · estimated site",
        color="#888888",
    )
    axes[1].barh(
        y + 0.17,
        [r["new_fixed_gps_fitted_c_percent"] for r in rows],
        height=0.32,
        label="New · fixed true site",
        color="#d97d26",
    )
    axes[1].set(title="Satellite criteria differ", xlim=(0, 100), xlabel="% of all GLRT points")
    axes[1].legend(fontsize=8)
    axes[2].barh(y, [r["standard_position_error_km"] for r in rows], color="#888888")
    axes[2].set(title="Standard blind position error", xlabel="Distance to supplied GPS (km)")
    for ax in axes:
        ax.set_yticks(y, names)
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=0.2)
    fig.savefig(OUTPUT / "comparison.png", dpi=150)
    plt.close(fig)
    files = {p.name: digest(p) for p in OUTPUT.iterdir() if p.is_file()}
    (OUTPUT / "seal.json").write_text(json.dumps(files, indent=2) + "\n")
    print(json.dumps(dict(totals=totals, verified_inputs=len(checked), blind_pilots=pilots)))


if __name__ == "__main__":
    run()
