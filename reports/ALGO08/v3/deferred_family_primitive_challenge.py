"""Stage a primitive holdout and report whether it measures the planned family."""

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

from deferred_family_held_support import (CAMPAIGN, CASE, HERE, NOMINATION, PINS, RELEASE,
                                         deny_raw_and_orbital, document, signature, time_separated)


OPPORTUNITY_FIELDS = ("visit_index", "receiver_id", "channel", "actual_rf_hz", "valid_start_counter")
SUPPORT_PIN = "c15b7e1d92ff236386f4bdf7bd3fdafcce65edc4b200d82f70b953a325c4b915"
STAGED = Path("/dev/shm/leo-v3-three-quarter-0220-stage01")


def partition(native, held_receiver, held_rf, window, guard, aperture):
    """Pick schedule from physical acquisition metadata, omitting all held outcomes."""
    origin = native["clock_anchor"]["sample_counter"]
    last = origin + window
    source = native["source"]
    held, train, embargo = [], [], []
    for row in source["probes"]:
        start = row["valid_start_counter"]
        if row["receiver_id"] == held_receiver and row["actual_rf_hz"] == held_rf and origin <= start < last - aperture:
            held.append({key: row[key] for key in OPPORTUNITY_FIELDS})
        elif time_separated(start, aperture, ((origin, last - 1),), guard):
            train.append(row)
        else:
            embargo.append({key: row[key] for key in OPPORTUNITY_FIELDS})
    return held, train, embargo


def observation_id(row, session):
    return "sha256:" + sha256(f'{session}:{row["receiver_id"]}:{row["valid_start_counter"]}'.encode()).hexdigest()


def causal_archive(authority):
    """Check signed filename authority and mincore residency without parsing a TLE body."""
    from leo.operations.tle_archive import TleArchiveReader

    archive = STAGED / "tle"
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (not refs or not archive.is_relative_to("/dev/shm") or
            any(ref.path.resolve() != ref.path or not ref.path.is_relative_to(archive)
                or ref.collected_utc_ns >= authority["causal_cutoff_utc_ns"] for ref in refs)):
        raise ValueError("Pending held test requires its already staged causal filename roster")
    digest = signature({ref.path.name: ref.sha256 for ref in refs})
    if digest != authority["archive_sha256"]:
        raise ValueError("Staged filename roster differs from the signed causal authority")
    names = [str(ref.path) for ref in refs]
    rows = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE", *names]))["fincore"]
    if len(rows) != len(refs):
        raise ValueError("The mincore roster is incomplete")
    return dict(archive=str(archive), signed_roster_sha256=digest, members=len(rows),
                resident_members=sum(row["res"] >= row["size"] for row in rows),
                apparent_bytes=sum(row["size"] for row in rows), orbital_bytes_read=0)


def ready():
    sys.path.insert(0, str(RELEASE / "src"))
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig

    measured = document(HERE / "measurements/deferred-family-held-support-0220.json", SUPPORT_PIN)
    raw = CAMPAIGN / CASE / "successor/attempt-000001"
    pair = document(CAMPAIGN / CASE / "pair.json", "d307ff5f4a02fe144eb1547574728a46bf19b4365d971687c471adea65aa4755")
    result = document(raw / "result.json", pair["attempt_result_sha256"]["successor"])
    authority = document(STAGED / "authority.json", pair["authority_sha256"])
    if authority != result["raw_identity"] or result["native_sha256"] != measured["exact_packet_sha256"]:
        raise ValueError("Held split changed original signed source")
    offered = document(STAGED / "offer.json", authority["region_sha256"])
    native_file, = (raw / "publication/fast-scan-automatic-work").glob("*/detections.json")
    native = document(native_file, result["native_sha256"])
    source = native["source"]
    receipt = document(NOMINATION, PINS["nomination"])["rows"][CASE]["outcome"]["deferred"]
    nominated = [*receipt["survivors"], receipt["peer"]]
    training_ids = {oid for row in nominated for oid in row["observation_ids"]}
    session = source["session_id"]
    original = {observation_id(row, session): row for row in source["probes"]}
    earlier = min((original[oid] for oid in training_ids), key=lambda row: row["valid_start_counter"])
    held_receiver, = {row["receiver_id"] for row in source["probes"]} - {earlier["receiver_id"]}
    held_rf = earlier["actual_rf_hz"]
    config = document(RELEASE / "assets/tracks.json", "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a")["config"]
    rate = source["sample_rate_hz"]
    window = round(max(config["window_lengths_s"]) * rate)
    guard = round(config["max_gap_s"] * rate)
    aperture = measured["max_aperture_counter"]
    held, train, embargo = partition(native, held_receiver, held_rf, window, guard, aperture)
    held_ids, train_ids = ({observation_id(row, session) for row in rows} for rows in (held, train))
    if held_ids.intersection(train_ids) or len(held_ids) != len(held) or not training_ids <= train_ids:
        raise ValueError("Primitive fold must exclude held observations while retaining the nominated training intervals")
    # Train-only detached view. Preserve the original physical IDs and clocks.
    train_doc = dict(native, source=dict(source, probes=train))
    graph = prepare_tracks(train_doc, TrackConfig(**config))
    curves = [graph["tracks"][i] for i in graph["curved_indices"]]
    structural = Counter((track["receiver"], int(track["channel"] > 4)) for track in curves)
    graph_owner = {oid: row["key"] for row in graph["tracks"] for oid in row["observation_ids"]}
    training_curve_rebuild = {}
    for row in nominated:
        intersections = Counter(graph_owner[oid] for oid in row["observation_ids"] if oid in graph_owner)
        training_curve_rebuild[row["component"]] = dict(graph_intersections=dict(intersections),
                                                       untracked=len(row["observation_ids"])-sum(intersections.values()))
    # Only inspect diagnostic block overlap after the primitive schedule is determined.
    candidate, = [row for row in measured["other_radio"]["rows"] if row["target_coarse_salvage"]
                  and row["contiguous_candidate_scope"]]
    overlap = sum(candidate["first_counter"] <= row["valid_start_counter"] <= candidate["last_counter"] for row in held)
    return dict(case=CASE, resident_archive=causal_archive(authority), fixed_offer=offered,
                exact_input_sha256=result["native_sha256"], training_only_graph_source=signature(config),
                schedule_anchor_counter=native["clock_anchor"]["sample_counter"], rate_hz=rate,
                held_receiver_native_id=held_receiver, held_frequency_hz=held_rf,
                window_counter=window, guard_counter=guard, aperture_counter=aperture,
                held_opportunities=len(held), wholly_excluded_other_opportunities=len(embargo),
                held_schedule_sha256=signature(held), train_probes_sha256=signature(train),
                training_opportunities=len(train), training_positive=len(graph["observations"]),
                training_graph_components=len(graph["tracks"]), training_graph_curved=len(curves),
                structural_training_curves_by_radio_bank={f"{rx}/{bank}": count for (rx,bank),count in sorted(structural.items())},
                nominated_training_members_retained=len(training_ids), old_prospective_block_overlap_opportunities=overlap,
                training_curve_rebuild=training_curve_rebuild,
                old_prospective_block_counters=[candidate["first_counter"], candidate["last_counter"]],
                independent_train_rival_nomination_available=False, transferable_offset_estimated=False,
                fit_or_forecast_invoked=False, orbit_body_reads=0, raw_waveform_reads=0,
                calibration_scores={"c0": None, "fitted_c": None},
                disposition="no_evidence_for_proposed_block" if overlap == 0 else "forecast_not_available")


if __name__ == "__main__":
    sys.addaudithook(deny_raw_and_orbital)
    print(json.dumps(ready(), sort_keys=True, indent=2, allow_nan=False))
