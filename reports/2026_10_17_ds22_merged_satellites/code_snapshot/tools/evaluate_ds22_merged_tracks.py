"""Transfer the frozen Graph/trimmed track policy to every sealed DS22 member.

Only existing local tracking exports are read. The full 137-member denominator
is preserved even when a recording lacks an available observation adapter.
No orbit identity or station coordinate enters track construction or merging.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from numpy.polynomial.legendre import legval

from leo.analysis.glrt_frequency_input import frequency_evidence
from leo.analysis.graph_tracklets import fit_lane
from leo.analysis.polynomial_tracklets import TrackConfig

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "reports/2026_10_14_ds22_post_ds21/local"
CONFIG = ROOT / "reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json"
OUTPUT = ROOT / "reports/2026_10_17_ds22_merged_satellites"


def digest(payload):
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def write(path, document):
    path.write_text(json.dumps(document, indent=2, allow_nan=False, default=json_default) + "\n")


def json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def winners(document):
    """One gated maximum-margin mark per original probe; no orbital filtering."""
    evidence, _, metadata = frequency_evidence(document)
    probes = document["source"]["probes"]
    receivers = sorted({p["receiver_id"] for p in probes})
    rows = []
    for index, probe in enumerate(probes):
        eligible = [c for c in probe["candidates"] if c["passed_fractional_margin_gate"] is True]
        if not eligible:
            continue
        candidate = max(eligible, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]))
        cfo = float(candidate["fractional_tracking_cfo_hz"])
        if not np.isfinite(cfo):
            raise ValueError("nonfinite winning CFO")
        rows.append(
            dict(
                observation_id=digest(evidence.ids[index].encode()),
                receiver=receivers.index(probe["receiver_id"]) + 1,
                native_receiver_id=probe["receiver_id"],
                channel=int(probe["channel"]),
                time_s=float(evidence.time_s[index]),
                measured_cfo_hz=cfo,
                actual_rf_hz=float(probe["actual_rf_hz"]),
                fractional_margin=float(candidate["fractional_margin"]),
            )
        )
    if len({r["observation_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate winning observation identity")
    rows.sort(key=lambda r: (r["receiver"], r["channel"], r["time_s"], r["observation_id"]))
    return rows, metadata


def graph_tracks(rows, source_id, config):
    """Public Graph fitter to the already-used multi-lane research port."""
    tracks, assigned = [], set()
    for receiver, channel in sorted({(r["receiver"], r["channel"]) for r in rows}):
        lane = [r for r in rows if (r["receiver"], r["channel"]) == (receiver, channel)]
        if len({r["actual_rf_hz"] for r in lane}) != 1:
            raise ValueError("a receiver/channel changes RF within the recording")
        t = np.array([r["time_s"] for r in lane])
        y = np.array([r["measured_cfo_hz"] for r in lane])
        result = fit_lane(t, y, config)
        for tid, original in enumerate(result["tracks"]):
            indexes = np.asarray(original["indices"], int)
            indexes = indexes[np.argsort(t[indexes], kind="stable")]
            pieces = []
            for raw in original["pieces"]:
                piece = dict(raw)
                ix = np.asarray(piece["indices"], int)
                piece.update(start_s=float(t[ix].min()), end_s=float(t[ix].max()))
                residual = (
                    y[ix]
                    + config.alias_spacing_hz * result["alias_lifts"][ix]
                    - legval(
                        (t[ix] - piece["reference_time_s"]) / piece["time_scale_s"],
                        piece["coefficients_hz"],
                    )
                )
                if (
                    np.max(np.abs(residual))
                    >= config.association_sigma * config.noise_sigma_hz + 1e-6
                ):
                    raise ValueError("Graph output violates its native residual gate")
                pieces.append(piece)
            ids = [lane[i]["observation_id"] for i in indexes]
            if assigned.intersection(ids):
                raise ValueError("duplicate Graph ownership")
            assigned.update(ids)
            tracks.append(
                dict(
                    original,
                    key=f"{source_id}-RX{receiver}-CH{channel}-T{tid:03}",
                    source_id=source_id,
                    receiver=receiver,
                    channel=channel,
                    bank="CH1-4" if channel <= 4 else "CH5-8",
                    rf_hz=lane[0]["actual_rf_hz"],
                    observation_ids=ids,
                    quality_status=original["diagnostics"]["quality_status"],
                    times=t[indexes],
                    values=y[indexes] + config.alias_spacing_hz * result["alias_lifts"][indexes],
                    pieces=pieces,
                    start_s=float(t[indexes].min()),
                    end_s=float(t[indexes].max()),
                )
            )
    return tracks, len(assigned)


def merge_tracks(tracks):
    import evaluate_dsx01_consensus_calibration as consensus

    # Fixed small-drift hypothesis: 5 Hz/s, in kHz per 150 seconds.
    consensus.BOUND[4:] = 0.75
    eligible = [t for t in tracks if t["quality_status"] == "no_structure_detected"]
    pool = [p for p in consensus.candidate_pool(eligible) if p["active_curvature"]]
    if len(pool) < 6:
        return dict(status="insufficient_curved_pairs", beta=[0.0] * 8, pairs=len(pool)), dict(
            ownership={t["key"]: t["key"] for t in tracks},
            input_tracks=len(tracks),
            output_tracks=len(tracks),
            accepted_edges=[],
            merged_groups=[],
        )
    packed = consensus.pack(pool)
    starts = consensus.initial_hypotheses(pool, packed, seed=731, budget=72)
    calibration = consensus.fit_method(tracks, pool, packed, starts, "trimmed")
    result = consensus.fuse(tracks, calibration)
    calibration["status"] = "fitted_curved_only"
    return calibration, result


def run(dataset, output, limit, merge):
    output.mkdir(parents=True, exist_ok=False)
    payload = (dataset / "manifest.json").read_bytes()
    seal = json.loads((dataset / "seal.json").read_bytes())
    if digest(payload) != seal["files"]["manifest.json"]:
        raise ValueError("DS22 manifest seal mismatch")
    manifest = json.loads(payload)
    config_payload = CONFIG.read_bytes()
    config = TrackConfig(**json.loads(config_payload)["config"])
    source_paths = [
        Path(__file__),
        ROOT / "src/leo/analysis/graph_tracklets.py",
        ROOT / "src/leo/analysis/polynomial_tracklets.py",
        ROOT / "src/leo/analysis/tracklet_fitting.py",
        ROOT / "tools/evaluate_dsx01_consensus_calibration.py",
    ]
    binding = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in source_paths}
    write(
        output / "protocol.json",
        dict(
            dataset="DS22",
            manifest_sha256=digest(payload),
            config_sha256=digest(config_payload),
            config=asdict(config),
            source_sha256=binding,
            mark_policy="one max-margin gate-passing peak per probe",
            merge=merge,
            merge_calibration="only active-curvature pairs; native drift bounded at 5 Hz/s",
            positions_used_in_track_construction=False,
            observations_withheld=0,
            position_target_km=0.5,
            position_target_achieved=False,
        ),
    )
    inventory, processed = [], 0
    for member in manifest["members"]:
        sid = member["dataset_label"]
        record = dict(
            source_id=sid,
            recording_id=member["recording_id"],
            capture_utc_ns=member["captured_utc_ns"],
            status="not_evaluated",
            winning_points=0,
            graph_points=0,
            graph_tracks=0,
            merged_tracks=0,
            satellite_association="not_evaluated",
            position_error_km=None,
        )
        inputs = member["tracking_inputs"]
        if not inputs:
            record["status"] = (
                "adaptive_observation_adapter_unavailable"
                if member.get("recording_format") == "starlink_adaptive_hop_iq"
                else "no_pinned_tracking_input"
            )
        elif limit is None or processed < limit:
            started = time.monotonic()
            if len(inputs) != 1:
                raise ValueError("declare a policy before choosing among multiple tracking inputs")
            entry = inputs[0]
            source = dataset / entry["snapshot"]
            raw = source.read_bytes()
            if digest(raw) != entry["sha256"] or seal["files"][entry["snapshot"]] != digest(raw):
                raise ValueError("sealed tracking export digest mismatch")
            document = json.loads(raw)
            rows, metadata = winners(document)
            tracks, count = graph_tracks(rows, sid, config)
            folder = output / sid
            folder.mkdir()
            write(folder / "observations.json", rows)
            write(folder / "tracks.json", tracks)
            if merge and tracks:
                calibration, result = merge_tracks(tracks)
                write(folder / "merged.json", dict(calibration=calibration, result=result))
            else:
                result = dict(output_tracks=len(tracks), accepted_edges=[])
            record.update(
                status="tracks_evaluated",
                winning_points=len(rows),
                graph_points=count,
                graph_tracks=len(tracks),
                merged_tracks=result["output_tracks"],
                graph_fraction=count / len(rows) if rows else 0.0,
                merge_edges=len(result["accepted_edges"]),
                elapsed_s=time.monotonic() - started,
            )
            write(
                folder / "receipt.json",
                dict(
                    **record,
                    metadata=metadata,
                    radio_id=document["source"]["radio_id"],
                    source_sha256=entry["sha256"],
                    source_snapshot=entry["snapshot"],
                    tracking_session_id=document["source"]["session_id"],
                ),
            )
            processed += 1
            print(json.dumps(record), flush=True)
        inventory.append(record)
        # Preserve a complete ledger even if a later bounded run is interrupted.
        pending = [
            dict(source_id=r["dataset_label"], status="pending")
            for r in manifest["members"][len(inventory) :]
        ]
        write(output / "coverage.json", inventory + pending)
    fields = sorted(set().union(*(r.keys() for r in inventory)))
    with (output / "coverage.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(inventory)
    write(
        output / "summary.json",
        dict(
            members=len(inventory),
            processed=processed,
            winning_points=sum(r["winning_points"] for r in inventory),
            graph_points=sum(r["graph_points"] for r in inventory),
            graph_tracks=sum(r["graph_tracks"] for r in inventory),
            merged_tracks=sum(r["merged_tracks"] for r in inventory),
            satellite_associations_evaluated=0,
            position_estimates_evaluated=0,
            sub_0_5km_position_target_verified=False,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()
    resolved = args.output.resolve()
    if resolved == Path("/mnt/qnap01") or Path("/mnt/qnap01") in resolved.parents:
        parser.error("QNAP is read-only")
    if args.limit is not None and args.limit < 1:
        parser.error("positive limit required")
    run(args.dataset, args.output, args.limit, args.merge)
