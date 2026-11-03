"""Independent membership replay and direct nominal-SGP4 sky verification.

Report only: supplied coordinates, station pose, and beam sensitivities never
enter RF fitting. This script does not nominate, optimize, or relabel a point.
"""

import csv
import argparse
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from algo02_scan import pair_passes
from analyze_dsx01_fixed_site import ecef_states
from audit_ds23_algo01_coverage import coverage, retained_metrics
from audit_ds23_0268_sky_visibility import angular_separation
from debug_ds23_0268_visibility_reentry import OUT, replay
from ds23_frequency_events import extend_event_associations
from probe_algo03_frame_peak_recovery import SOURCE, context
from probe_ds23_frequency_events import summary
from prototype_dsx01_continuous_position import latlon
from report_algo02_ds23 import REFERENCE
from run_algo01_ds23_sample import ROOT, read, sha, write
from leo.sky.frames import geodetic_to_ecef_km, ecef_to_enu_matrix, look_angles
from leo.sky.propagation import parse_element_sets


def main(proposal=None):
    case = "DS23-0268"
    source = SOURCE / case
    fit_path = OUT / (proposal + ".json") if proposal else OUT / "trials/interior_add_66797.json"
    prefix = proposal + "_" if proposal else ""
    record = read(fit_path)
    if not pair_passes(record["arms"], include_linear=True):
        raise ValueError("saved paired fit no longer qualifies")
    observations = read(source / "observations.json")
    original_ids = {o["observation_id"] for o in observations}
    if len(original_ids) != len(observations):
        raise ValueError("duplicate original measurement IDs")
    expected = (dict(arms=read(OUT / "accepted_identity_split_coverage.json")[proposal]) if proposal else
        next(r for r in read(OUT / "trial_coverage.json")["rows"] if r["name"] == "interior_add_66797"))
    old = read(ROOT / "reports/2026_10_20_ds23_frequency_events_v3" /
               case / "receiver_reentry_coverage.json")
    station_path = ROOT / "deploy/station/gauss-r20-lt3d-004b-20261001-v1.json"
    station = read(station_path)
    radio_id = read(source / "tracking.json")["source"]["radio_id"]
    if radio_id not in (station["radio_id"], station["radio_serial"]):
        raise ValueError("recording radio does not match station geometry authority")
    axes = {r["receiver_id"] + 1: (r["azimuth_deg"],
            r["elevation_deg"] if r["elevation_deg"] is not None else
            90. - station["nominal_outward_tilt_deg"])
            for r in station["receivers"]}
    elements = read(source / "nominal_elements.json")
    point_rows, arms = [], {}
    figure, panels = plt.subplots(2, 2, figsize=(15, 9), sharex=True)
    for col, arm in enumerate(("c0", "fitted_c")):
        if proposal:
            from probe_ds23_0268_selected_identity_split import replay_proposal
            problem, endpoint = replay_proposal(record, arm)
        else:
            problem, endpoint = replay(record, arm)
        origin = problem.scan.receipt["origin_utc_ns"]
        cutoff = problem.scan.receipt["cutoff_utc_ns"]
        if not station["valid_from_utc_ns"] <= origin < station["valid_until_utc_ns"]:
            raise ValueError("station pose record is outside its validity interval")
        for item in elements.values():
            provenance = item["provenance"]
            if max(provenance["element_epoch_utc_ns"], provenance["collected_utc_ns"]) > cutoff:
                raise ValueError("future element in nominal catalogue")
        fresh = summary(problem, endpoint, record.get("predictive_entries", context(case)[4]["linear_entries"]))
        metrics = fresh["gates"]
        if not all(t["compatible"] for t in metrics["tracks"]):
            raise ValueError("retained curved gate replay failed")
        if not all(t["compatible"] for t in fresh["linear_gates"]):
            raise ValueError("predictive linear gate replay failed")
        extension = extend_event_associations(problem, endpoint, metrics)
        accepted = {r["component"]: r for r in extension["tracks"] if r["compatible"]}
        for row in fresh["linear_gates"] + metrics["tracks"]:
            if row["compatible"]:
                accepted[row["component"]] = row
        result = coverage(list(accepted.values()), problem.scan.tracks, original_ids)
        if result["associated_observation_ids"] != expected["arms"][arm]["associated_observation_ids"]:
            raise ValueError("recomputed accepted observations differ")
        expected_count = expected["arms"][arm]["associated_original_winners"]
        if result["associated_additional_peaks"] or result["associated_original_winners"] != expected_count or expected_count < 2216:
            raise ValueError("unexpected numerator or non-original measurements")
        old_ids = set(old["arms"][arm]["associated_observation_ids"])
        if not old_ids <= set(result["associated_observation_ids"]):
            raise ValueError("earlier associated observations were lost")
        tracks = {t["key"]: t for t in problem.scan.tracks}
        satellites = sorted({r["norad"] for r in accepted.values()})
        for row in accepted.values():
            track = tracks[row["component"]]
            owned = set(row.get("observation_ids", track["observation_ids"]))
            selected = np.array([o in owned for o in track["observation_ids"]])
            times = track["times"][selected]
            catalogue = parse_element_sets("\n".join(elements[str(row["norad"])]["lines"]))
            positions, velocities, usable = ecef_states(catalogue, origin, times)
            if not usable.all():
                raise ValueError("direct SGP4 propagation failed")
            for geometry, location in (("RF_estimate", latlon(endpoint)),
                                       ("evaluation_only", REFERENCE)):
                azimuth, elevation, _, _ = look_angles(positions[0], velocities[0],
                    geodetic_to_ecef_km(*location, 0.), ecef_to_enu_matrix(*location))
                off_axis = angular_separation(azimuth, elevation, *axes[track["receiver"]])
                for oid, time, az, el, off in zip(np.array(track["observation_ids"])[selected],
                        times, azimuth, elevation, off_axis, strict=True):
                    point_rows.append(dict(arm=arm, geometry=geometry, observation_id=oid,
                        component=row["component"], norad=row["norad"], receiver=track["receiver"],
                        channel=track["channel"], time_s=float(time), azimuth_deg=float(az),
                        elevation_deg=float(el), nominal_off_axis_deg=float(off)))
                if geometry == "RF_estimate":
                    color = plt.get_cmap("tab20")(satellites.index(row["norad"]) % 20)
                    panels[0, col].plot(times, elevation, ".", ms=2, color=color)
                    panels[1, col].plot(times, off_axis, ".", ms=2, color=color,
                                       label=str(row["norad"]))
        selected_rows = [r for r in point_rows if r["arm"] == arm]
        geometry_summary = {}
        for geometry in ("RF_estimate", "evaluation_only"):
            subset = [r for r in selected_rows if r["geometry"] == geometry]
            if len(subset) != expected_count or len({r["observation_id"] for r in subset}) != expected_count:
                raise ValueError("sky audit does not cover every associated measurement exactly once")
            geometry_summary[geometry] = dict(points=len(subset),
                minimum_elevation_deg=min(r["elevation_deg"] for r in subset),
                maximum_nominal_off_axis_deg=max(r["nominal_off_axis_deg"] for r in subset),
                below_horizon=sum(r["elevation_deg"] < 0 for r in subset),
                outside_45deg=sum(r["nominal_off_axis_deg"] > 45 for r in subset),
                behind_nominal_axis=sum(r["nominal_off_axis_deg"] > 90 for r in subset))
        arms[arm] = dict(associated_points=result["associated_original_winners"],
            associated_percent=result["associated_original_percent"], tracks=len(accepted),
            satellites=len(satellites), added_points=len(set(result["associated_observation_ids"])-old_ids),
            curved_gates_replayed=True, extension_membership_replayed=True,
            predictive_linear_gates_replayed=True,
            joint_objective_replayed=True, direct_nominal_SGP4=geometry_summary,
            single_piece_53923_tracks=all(len(tracks[r["component"]]["pieces"]) == 1
                for r in accepted.values() if r["norad"] == 53923))
        panels[0, col].set_title(f"{arm}: all {expected_count:,} associated points · nominal causal TLE")
    for col in range(2):
        panels[0, col].set_ylabel("Elevation (degrees)")
        panels[1, col].set_ylabel("Separation from nominal feed axis (degrees)")
        panels[1, col].set_xlabel("Time from scan start (s)")
        panels[0, col].axhline(0, color="black", lw=.8)
        panels[1, col].axhline(45, color="gray", ls="--", lw=.8)
        handles, labels = panels[1, col].get_legend_handles_labels()
        unique = dict(zip(labels, handles))
        panels[1, col].legend(unique.values(), unique.keys(), ncol=4, fontsize=7)
        for ax in panels[:, col]:
            ax.grid(alpha=.15)
            ax.set_xlim(0, 300)
    figure.suptitle("DS23-0268 · direct SGP4 audit at the RF-estimated positions\n"
        "No fitted phase or orbit corrections · 45° is a sensitivity line, not a measured antenna beam")
    figure.tight_layout(rect=(0, 0, 1, .93))
    figure.savefig(OUT / (prefix + "direct_nominal_sky_time_audit.png"), dpi=170)
    plt.close(figure)
    with (OUT / (prefix + "direct_nominal_sky_points.csv")).open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(point_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(point_rows)
    write(OUT / (prefix + "independent_replay_audit.json"), dict(case=case,
        audited_at_UTC=datetime.now(timezone.utc).isoformat(), arms=arms,
        selected_fit_sha256=sha(fit_path), observations_sha256=sha(source / "observations.json"),
        nominal_elements_sha256=sha(source / "nominal_elements.json"),
        station_authority_sha256=sha(station_path),
        audit_source_sha256=sha(ROOT / "tools/verify_ds23_0268_selected_result.py"),
        recording_radio_matches_station_authority=True,
        all_catalogue_epochs_and_collection_times_causal=True,
        no_association_or_position_refit=True, evaluation_coordinate_used_only_in_reporting=True,
        axis_mapping_provisional=True, installed_boresight_and_beam_width_unmeasured=True))
    print(arms, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", choices=("selected_split_all_RX1_constrained",
                                               "selected_split_all_RX1_with_CH2_constrained"))
    main(parser.parse_args().proposal)
