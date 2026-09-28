"""Join saved decoding evidence with acquisition, pose and conditional track metadata."""

import hashlib
import importlib.util
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from cluster_signals import BASE, JOINT, OUT, canonical, csv_write, qualifies_word

ROOT = BASE.parents[1]
ANNOTATIONS = ROOT / "reports/2026_09_27_ds7_satellite_annotations"


def utc(ns):
    return datetime.fromtimestamp(ns / 1e9, UTC).isoformat() if ns is not None else None


def summarize(values):
    values = [v for v in values if v is not None and np.isfinite(v)]
    return float(np.median(values)) if values else None


def compatible_track(track, probe):
    """Visit/RX/RF membership is a candidate association, not decoder identity proof."""
    return (
        track["receiver_id"] == probe["receiver_id"]
        and track["channel"] == probe["channel"]
        and abs(track["rf_hz"] - probe["actual_rf_hz"]) < 1
        and probe["visit_index"] in track["visits"]
    )


def main():
    sources = {}

    def read(path):
        path = Path(path)
        data = path.read_bytes()
        sources[str(path)] = hashlib.sha256(data).hexdigest()
        return json.loads(data)

    inventory = read(OUT / "inventory.json")
    inputs = read(ANNOTATIONS / "local/inputs.json")
    ds7_records = {r["session_id"]: r for r in inputs["recordings"]}
    annotations = {
        (r["session_id"], r["track_id"]): r
        for r in read(ANNOTATIONS / "local/track-annotations.json")
    }
    groups = read(JOINT / "local/joint-results.json")["groups"]
    captures, poses, datasets = {}, {}, {}
    for dataset, folder in [("DS7", "2026_09_27_ds7_post_ds6"), ("DS8", "2026_09_28_ds8_post_ds7")]:
        for capture in read(ROOT / "reports" / folder / "manifest.json")["captures"]:
            sid = capture["session_id"]
            captures[sid] = capture
            datasets[sid] = dataset
            poses[sid] = ROOT / "reports" / folder / "pose" / f"{sid}.json"
    spec = importlib.util.spec_from_file_location("saved_geometry", ANNOTATIONS / "annotate.py")
    geom = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geom)
    documents, bank_metadata, banks, pose_cache = {}, {}, {}, {}
    signal_rows, receiver_rows, track_rows, details = [], [], [], []
    for visit in inventory:
        sid, signal = visit["session"], visit["signal"]
        capture = captures[sid]
        if sid not in pose_cache:
            pose_cache[sid] = read(poses[sid])
        pose = pose_cache[sid]["pose_authority"]
        result = read(OUT / f"{signal}.json")
        accepted = [r for r in result["results"] if qualifies_word(r)]
        labels = {}
        for group in groups:
            if (group["session_id"], group["visit"]) == (sid, visit["visit"]):
                for label in group.get("labels", []):
                    if label.get("track_id"):
                        labels[(label["receiver_id"], label["track_id"])] = label
        if sid in ds7_records and sid not in documents:
            record = ds7_records[sid]
            documents[sid] = read(record["tracks"])
            assert "sha256:" + sources[record["tracks"]] == record["tracks_sha256"]
            bankdir = Path(record["bank"])
            bank_metadata[sid] = read(bankdir / "manifest.json")
            bankpath = bankdir / "banks.npz"
            sources[str(bankpath)] = hashlib.sha256(bankpath.read_bytes()).hexdigest()
            assert "sha256:" + sources[str(bankpath)] == record["bank_sha256"]
            banks[sid] = np.load(bankpath, allow_pickle=False)
        local_rx, associated = [], []
        for stream in visit["streams"]:
            row = stream["row"]
            p, c, event = row["probe"], row["candidate"], row["visit"]["event"]
            if row.get("manifest_sha256"):
                assert row["manifest_sha256"] == capture["manifest_sha256"]
            rx = p["receiver_id"]
            diag = next((r for r in result.get("receivers", []) if r["name"] == row["name"]), {})
            rxrow = dict(
                signal=signal,
                dataset=datasets[sid],
                session=sid,
                visit=visit["visit"],
                receiver=rx,
                channel=p["channel"],
                edge=p["edge"],
                rate_hz=row["sample_rate_hz"],
                bandwidth_hz=capture.get("bandwidth_hz"),
                actual_rf_hz=p["actual_rf_hz"],
                target_rf_hz=event["target"]["rf_center_hz"],
                actual_if_lo_hz=event.get("actual_lo_frequency_hz"),
                configured_if_offset_hz=event.get("actual_if_offset_hz"),
                acquisition_cfo_hz=c["fractional_tracking_cfo_hz"],
                acquisition_epoch_samples=c["integer_epoch_sample"]
                + c["fractional_epoch_offset_samples"],
                acquisition_score=c["fractional_exact_score"],
                acquisition_margin=c["fractional_margin"],
                sample_clock_ppm=diag.get("sample_clock_ppm"),
                pilot_coherence_median=summarize(
                    [d["held_pilot_coherence"] for d in diag.get("diagnostics", [])]
                ),
                nonpilot_bins=";".join(map(str, diag.get("bins", []))),
                pilot_bins=";".join(map(str, diag.get("pilot_bins", []))),
                excerpt_ms=1000 * stream["samples"] / row["sample_rate_hz"],
                valid_dwell_ms=1000
                * (row["visit"]["valid_end_counter_exclusive"] - event["valid_start_counter"])
                / row["sample_rate_hz"],
                source_counter=event["valid_start_counter"],
                capture_start_utc=utc(capture["capture_start_utc_ns"]),
                latitude_deg=pose["latitude_deg"],
                longitude_deg=pose["longitude_deg"],
                altitude_m=pose.get("altitude_m"),
                pose_revision=pose["revision"],
                provisional_rx_azimuth_deg=270 if rx == 0 else 90,
            )
            local_rx.append(rxrow)
            receiver_rows.append(rxrow)
            tracks = [t for t in documents.get(sid, {}).get("tracks", []) if compatible_track(t, p)]
            for track in tracks:
                tid = track["track_id"]
                label = annotations.get((sid, tid), {})
                t = np.asarray(track["times_s"])
                y = np.asarray(track["measured_hz"])
                indices = [k for k, v in enumerate(track["visits"]) if v == visit["visit"]]
                k = indices[0]
                tr = dict(
                    signal=signal,
                    receiver=rx,
                    track_id=tid,
                    binding="prior_label_link" if (rx, tid) in labels else "visit_rx_rf_only",
                    status=label.get("status"),
                    candidate_norad=label.get("norad_id"),
                    candidate_name=label.get("satellite_name"),
                    observation_utc=utc(documents[sid]["start_utc_ns"] + int(t[k] * 1e9)),
                    measured_cfo_canonical_hz=float(y[k]),
                    canonical_rf_hz=11.2e9,
                    track_cfo_slope_hz_s=float(np.polyfit(t - t.mean(), y, 1)[0]),
                    fitted_constant_offset_hz=label.get("offset_hz"),
                    validation_rms_hz=label.get("validation_rms_hz"),
                    predicted_doppler_canonical_hz=None,
                    predicted_doppler_tuned_rf_hz=None,
                    azimuth_at_observation_deg=None,
                    elevation_at_observation_deg=None,
                    range_at_observation_km=None,
                )
                bs = next((b for b in bank_metadata[sid]["tracks"] if b["track_id"] == tid), None)
                if bs and label.get("norad_id"):
                    bank = banks[sid]
                    zero = int(np.flatnonzero(bank["timing_grid_s"] == 0)[0])
                    n = bs["index"]
                    catalog = inputs["catalogues"][ds7_records[sid]["catalogue_digest"]]
                    ids = bank[f"candidate_ids_{n}"]
                    candidates = [
                        i
                        for i, index in enumerate(ids)
                        if catalog["norad_ids"][int(index)] == label["norad_id"]
                    ]
                    assert len(candidates) == 1
                    ci = candidates[0]
                    rec, basis = geom.geometry(pose["latitude_deg"], pose["longitude_deg"])
                    predicted, az, el, ranges = geom.predict(
                        bank[f"position_km_{n}"][ci, zero],
                        bank[f"velocity_km_s_{n}"][ci, zero],
                        rec,
                        basis,
                    )
                    tr.update(
                        predicted_doppler_canonical_hz=float(predicted[k]),
                        predicted_doppler_tuned_rf_hz=float(
                            predicted[k] * p["actual_rf_hz"] / 11.2e9
                        ),
                        azimuth_at_observation_deg=float(az[k]),
                        elevation_at_observation_deg=float(el[k]),
                        range_at_observation_km=float(ranges[k]),
                    )
                associated.append(dict(**tr, annotation=label, source_track=track))
                track_rows.append(tr)
        fam = Counter(canonical(r["word"]) for r in accepted)
        weights = np.array(list(fam.values()), float)
        entropy = (
            float(-np.sum(weights / weights.sum() * np.log2(weights / weights.sum())))
            if fam
            else None
        )
        known_labels = [
            x
            for x in labels.values()
            if x.get("norad_id") == visit["norad_id"] and visit["norad_id"] is not None
        ]
        prior_tracks = [
            t
            for t in associated
            if t["binding"] == "prior_label_link"
            and t["candidate_norad"] == visit["norad_id"]
            and visit["norad_id"]
        ]
        first = local_rx[0]
        s = dict(
            signal=signal,
            dataset=datasets[sid],
            session=sid,
            visit=visit["visit"],
            channel=first["channel"],
            edge=visit["edge"],
            rate_hz=first["rate_hz"],
            bandwidth_hz=first["bandwidth_hz"],
            actual_rf_hz=first["actual_rf_hz"],
            if_lo_hz=first["actual_if_lo_hz"],
            configured_if_offset_hz=first["configured_if_offset_hz"],
            excerpt_ms=first["excerpt_ms"],
            valid_dwell_ms=first["valid_dwell_ms"],
            capture_start_utc=first["capture_start_utc"],
            capture_start_unix_s=capture["capture_start_utc_ns"] / 1e9,
            capture_utc_bracket_ms=(
                capture["capture_start_latest_utc_ns"] - capture["capture_start_earliest_utc_ns"]
            )
            / 1e6,
            receivers=len(local_rx),
            accepted=len(accepted),
            strict_accepted=sum(r["accepted"] for r in result["results"]),
            attempted=len(result["results"]),
            recovery_fraction=len(accepted) / len(result["results"]) if result["results"] else None,
            unique_words=len({r["word"] for r in accepted}),
            unique_families=len(fam),
            family_entropy_bits=entropy,
            known_conditional_norad=visit["norad_id"],
            known_conditional_name=next(
                (x.get("satellite_name", x.get("candidate_name")) for x in known_labels), None
            ),
            additional_track_candidates=";".join(
                sorted(
                    {
                        f"RX{x['receiver']}:{x['candidate_name']}:{x['status']}"
                        for x in associated
                        if x["binding"] != "prior_label_link"
                    }
                )
            ),
            known_label_validation_rms_hz=summarize(
                [x.get("validation_rms_hz") for x in known_labels]
            ),
            known_label_offset_canonical_hz=summarize([x.get("offset_hz") for x in known_labels]),
            known_label_azimuth_mid_deg=summarize([x.get("azimuth_mid_deg") for x in known_labels]),
            known_label_elevation_mid_deg=summarize(
                [x.get("elevation_mid_deg") for x in known_labels]
            ),
            predicted_doppler_canonical_hz=summarize(
                [x["predicted_doppler_canonical_hz"] for x in prior_tracks]
            ),
            predicted_range_km=summarize([x["range_at_observation_km"] for x in prior_tracks]),
            latitude_deg=first["latitude_deg"],
            longitude_deg=first["longitude_deg"],
            altitude_m=first["altitude_m"],
            pose_revision=first["pose_revision"],
        )
        for rx in [0, 1]:
            rr = next((r for r in local_rx if r["receiver"] == rx), {})
            for key in [
                "acquisition_cfo_hz",
                "sample_clock_ppm",
                "pilot_coherence_median",
                "acquisition_margin",
            ]:
                s[f"rx{rx}_{key}"] = rr.get(key)
        s["rx1_minus_rx0_cfo_hz"] = (
            s["rx1_acquisition_cfo_hz"] - s["rx0_acquisition_cfo_hz"]
            if all(s[f"rx{rx}_acquisition_cfo_hz"] is not None for rx in [0, 1])
            else None
        )
        signal_rows.append(s)
        details.append(
            dict(
                summary=s,
                receivers=local_rx,
                associated_tracks=associated,
                prior_labels=list(labels.values()),
                original_inventory=visit,
                capture=capture,
                pose=pose_cache[sid],
            )
        )
    for bank in banks.values():
        bank.close()
    csv_write(OUT / "metadata_signals.csv", signal_rows)
    csv_write(OUT / "metadata_receivers.csv", receiver_rows)
    csv_write(OUT / "metadata_tracks.csv", track_rows)
    (OUT / "metadata_details.json").write_text(json.dumps(details, indent=2) + "\n")
    (OUT / "metadata_sources.json").write_text(json.dumps(sources, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                visits=len(signal_rows),
                receivers=len(receiver_rows),
                track_links=len(track_rows),
                sources=len(sources),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
