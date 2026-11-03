"""Check RF, time and native alias bindings back to frozen published inputs."""

import hashlib
import json
from pathlib import Path

from associate_merged_track_catalogue import load_tracks, write
from evaluate_ds22_merged_tracks import winners
from evaluate_dsx01_cohort_tracklets import load_cohort
from inventory_clipped_phase_cohort import PRIOR, ROOT


def audit_tracks(tracks, rows):
    byid = {r["observation_id"]: r for r in rows}
    seen, error = set(), 0.0
    for t in tracks:
        for oid, time, value in zip(t["observation_ids"], t["times"], t["values"], strict=True):
            if oid in seen:
                raise ValueError("Graph duplicates original observation identity")
            seen.add(oid)
            raw = byid[oid]
            if raw["actual_rf_hz"] != t["rf_hz"] or raw["time_s"] != time:
                raise ValueError("Graph changed original RF or counter-derived time")
            if (raw["receiver"], raw["channel"]) != (t["receiver"], t["channel"]):
                raise ValueError("Graph changed receiver/channel identity")
            alias = (value - raw["measured_cfo_hz"]) / (1 / 4.4e-6)
            error = max(error, abs(alias - round(alias)))
    if error > 1e-8:
        raise ValueError("Graph CFO is not an integer native alias of the original mark")
    return dict(
        raw_points=len(rows),
        graph_points=len(seen),
        exact_actual_rf_and_time_binding=True,
        maximum_alias_integer_error=error,
    )


def run():
    output = ROOT / "reports/2026_10_17_cohort_phase_repair/input_audit"
    output.mkdir(exist_ok=False)
    rows, sources, _, binding = load_cohort()
    results = []
    lineage = {}
    for i, source in enumerate(sources, start=1):
        case = f"DSX01-S{i:02d}"
        recording = ROOT / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter" / case
        original = load_tracks(recording)
        original_rows = [r for r in rows if r["source_id"] == source["source_id"]]
        result = audit_tracks(original, original_rows)
        bank = (
            ROOT / "reports/2026_10_17_dsx01_polynomial_satellite_dive/frozen_inputs" / case
            if i == 1
            else PRIOR / "frozen_inputs" / case
        )
        receipt = json.loads((bank / "receipt.json").read_text())
        metadata = json.loads((recording / "receipt.json").read_text())["metadata"]
        if not (
            source["first_sample_estimate_utc_ns"]
            == metadata["anchor_utc_ns"]
            == receipt["origin_utc_ns"]
        ):
            raise ValueError("orbit-bank UTC origin differs from frozen timing authority")
        edge = source["recording_id"].rsplit("-", 1)[-1]
        for t in original:
            expected = (
                10700000000.0
                + 250000000.0 * (t["channel"] - 1)
                + (9687500 if edge == "lower" else 240312500)
            )
            if expected != t["rf_hz"]:
                raise ValueError("RF differs from recorded edge/channel lattice")
        public_source = Path(source["tracking_input_path"])
        try:
            with public_source.open("rb") as f:
                f.read(1)
            public_readable = True
        except (OSError, PermissionError):
            public_readable = False
        result.update(
            case=case,
            edge=edge,
            origin_utc_ns=receipt["origin_utc_ns"],
            cutoff_utc_ns=receipt["cutoff_utc_ns"],
            anchor_minus_cutoff_s=(receipt["origin_utc_ns"] - receipt["cutoff_utc_ns"]) / 1e9,
            rf_grid_consistent_with_recorded_edge=True,
            public_source_locally_readable=public_readable,
            original_public_input_sha256=source["tracking_input_sha256"],
            scope="frozen source/context exports; original live input not required",
            rf_physical_calibration_verified=False,
        )
        results.append(result)
        lineage[str((recording / "tracks.json").relative_to(ROOT))] = hashlib.sha256(
            (recording / "tracks.json").read_bytes()
        ).hexdigest()
    case = "DS22-001"
    recording = ROOT / "reports/2026_10_17_ds22_merged_satellites/cohort" / case
    receipt = json.loads((recording / "receipt.json").read_text())
    snapshot = ROOT / "reports/2026_10_14_ds22_post_ds21/local" / receipt["source_snapshot"]
    payload = snapshot.read_bytes()
    if "sha256:" + hashlib.sha256(payload).hexdigest() != receipt["source_sha256"]:
        raise ValueError("DS22 public source snapshot changed")
    document = json.loads(payload)
    original_rows, metadata = winners(document)
    stored = json.loads((recording / "observations.json").read_text())
    # The published observation list must be exactly reproducible, not only RF.
    if original_rows != stored:
        raise ValueError("DS22 public marks do not reproduce frozen observations")
    result = audit_tracks(load_tracks(recording), original_rows)
    bank_receipt = json.loads((PRIOR / "frozen_inputs/DS22-001/receipt.json").read_text())
    if metadata["anchor_utc_ns"] != bank_receipt["origin_utc_ns"]:
        raise ValueError("DS22 orbit clock origin changed")
    result.update(
        case=case,
        edge="upper",
        public_source_snapshot_sha256=receipt["source_sha256"],
        counter_time_definition="(valid_start_counter-anchor_counter)/sample_rate + probe_ms/2000",
        all_published_marks_reproduced=True,
        sample_rate_hz=document["source"]["sample_rate_hz"],
        probe_ms=document["source"]["probe_ms"],
        utc_half_width_s=metadata["utc_half_width_s"],
        rf_mapping_authorities=metadata["rf_mapping_authorities"],
        physical_rf_or_utc_latency_calibration_verified=False,
    )
    results.append(result)
    lineage[str(snapshot.relative_to(ROOT))] = hashlib.sha256(payload).hexdigest()
    write(output / "results.json", results)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            dsx_input_binding=binding,
            source_sha256_inputs=lineage,
            measurement_values_not_modified=True,
            no_position_or_satellite_fit_used_for_validation=True,
            adapter_integrity_is_not_absolute_rf_or_utc_calibration=True,
        ),
    )
    print(json.dumps(results), flush=True)


if __name__ == "__main__":
    run()
