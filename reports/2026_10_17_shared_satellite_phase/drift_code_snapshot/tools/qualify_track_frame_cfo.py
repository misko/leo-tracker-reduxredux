"""Bounded existing-IQ panel for a continuous, independently qualified frame CFO.

Original Graph points, detector decisions and published products are unchanged.
Selection uses raw curved-track support only, never satellite IDs or GPS error.
"""

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from localize_merged_track_catalogue import raw_curvature

from leo.analysis.qam import estimate_edge_pilot_frame_cfo
from leo.analysis.starlink.fast_scan_fractional import fractional_take
from leo.analysis.starlink.templates import (
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    edge_frequencies_hz,
)


def select_points(tracks):
    chosen = []
    for group in range(4):
        curves = [
            t
            for t in tracks
            if raw_curvature(t) and 2 * (t["receiver"] - 1) + int(t["channel"] > 4) == group
        ]
        curves.sort(key=lambda t: (-len(t["times"]), t["key"]))
        for track in curves[:2]:
            for index in np.unique(
                np.rint(np.array([0.2, 0.8]) * (len(track["times"]) - 1)).astype(int)
            ):
                chosen.append(
                    dict(
                        component=track["key"],
                        observation_id=track["observation_ids"][index],
                        receiver=track["receiver"],
                        channel=track["channel"],
                        time_s=float(track["times"][index]),
                        graph_cfo_hz=float(track["values"][index]),
                    )
                )
    return chosen


def match_probe(point, probes, receivers, origin, rate, probe_ms):
    """Require unique physical support and a reproduced gated frequency peak.

    Legacy DSX01 point times differ by up to half a millisecond from the device
    counter times. Retain that discrepancy explicitly; never alter point times.
    """
    nearby = []
    for probe in probes:
        if (receivers.index(probe["receiver_id"]) + 1, probe["channel"]) != (
            point["receiver"],
            point["channel"],
        ):
            continue
        time_s = (probe["valid_start_counter"] - origin) / rate + probe_ms / 2000
        if abs(time_s - point["time_s"]) <= 0.00051:
            nearby.append((probe, time_s))
    if len(nearby) != 1:
        raise ValueError("selected Graph point lacks unique nearby physical probe support")
    probe, time_s = nearby[0]
    eligible = [c for c in probe["candidates"] if c["passed_fractional_margin_gate"]]

    def difference(candidate):
        d = candidate["fractional_tracking_cfo_hz"] - point["graph_cfo_hz"]
        return abs((d + 0.5 / 4.4e-6) % (1 / 4.4e-6) - 0.5 / 4.4e-6)

    if not eligible:
        raise ValueError("selected Graph point has no gated original peak")
    winner = min(
        eligible, key=lambda c: (difference(c), -c["fractional_margin"], c["candidate_rank"])
    )
    if difference(winner) > 1e-3:
        raise ValueError("selected Graph point cannot be reproduced from a gated original peak")
    return probe, winner, time_s - point["time_s"]


def run(case, output):
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource

    root = Path(__file__).resolve().parents[1]
    original = root / "reports/2026_10_17_ds22_merged_satellites"
    recording = original / ("cohort" if case.startswith("DS22") else "dsx01_adapter") / case
    receipt = json.loads((recording / "receipt.json").read_text())
    if case.startswith("DS22"):
        source_path = root / "reports/2026_10_14_ds22_post_ds21/local" / receipt["source_snapshot"]
        expected = receipt["source_sha256"]
    else:
        sources = json.loads(
            (root / "reports/2026_10_16_dsx01_fast_association_losses/sources.json").read_text()
        )
        entry = next(r for r in sources if "DSX01-" + r["source_id"] == case)
        source_path, expected = Path(entry["tracking_input_path"]), entry["tracking_input_sha256"]
    raw = source_path.read_bytes()
    if "sha256:" + hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("original GLRT source changed")
    document = json.loads(raw)
    source = document["source"]
    rate, probe_ms = source["sample_rate_hz"], source["probe_ms"]
    if rate != 2500000 or probe_ms != 20:
        raise ValueError("this bounded panel is qualified for existing fast 2.5-MS/s probes only")
    receivers = sorted({p["receiver_id"] for p in source["probes"]})
    chosen = select_points(load_tracks(recording))
    origin = document["clock_anchor"]["sample_counter"]
    for point in chosen:
        probe, winner, time_difference = match_probe(
            point, source["probes"], receivers, origin, rate, probe_ms
        )
        point.update(probe=probe, candidate=winner, source_minus_graph_time_s=time_difference)
    store = FastScanStore("/srv/bulk/leo")
    inventory = store.source(source["session_id"], source["input_manifest_sha256"])
    output.mkdir(parents=True, exist_ok=False)
    write(
        output / "protocol.json",
        dict(
            case=case,
            original_source_sha256=expected,
            original_tracks_sha256=hashlib.sha256(
                (recording / "tracks.json").read_bytes()
            ).hexdigest(),
            selected_points=len(chosen),
            selection="two longest measured-curved tracks per RX/band, points at20/80 percent",
            reference_position_used=False,
            satellite_identity_used=False,
            maximum_probe_time_match_difference_s=0.00051,
            original_graph_times_unchanged=True,
            new_acquisition=False,
            original_detector_decisions_unchanged=True,
            frame_estimator="estimate_edge_pilot_frame_cfo default reviewed gates",
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            estimator_source_sha256=hashlib.sha256(
                root.joinpath("src/leo/analysis/qam/pilot.py").read_bytes()
            ).hexdigest(),
        ),
    )
    needed = {p["probe"]["visit_index"] for p in chosen}
    results = []
    started = time.monotonic()
    for segment in inventory["segments"]:
        adapter = FastSegmentSource(segment)
        for window in adapter.windows():
            visit = window.acquisition["global_visit"]
            if visit not in needed:
                continue
            own = [p for p in chosen if p["probe"]["visit_index"] == visit]
            for point in own:
                probe, candidate = point["probe"], point["candidate"]
                if window.acquisition["sample_start"] != probe["valid_start_counter"]:
                    raise ValueError("selected IQ support differs from original probe counter")
                rx = adapter.receiver_ids.index(probe["receiver_id"])
                raw_iq = window.samples[:, rx, :]
                iq = raw_iq[:, 0].astype(float) + 1j * raw_iq[:, 1].astype(float)
                epoch = (
                    candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]
                )
                reference_offset = np.mean((np.arange(300) + 2.5) * OFDM_SYMBOL_DURATION_S) * rate
                frame = max(
                    0, int(round((len(iq) / 2 - epoch - reference_offset) / (rate / FRAME_RATE_HZ)))
                )
                start = epoch + frame * rate / FRAME_RATE_HZ
                count = round(302 * rate * OFDM_SYMBOL_DURATION_S)
                positions = start + np.arange(-1, count + 1)
                compact = fractional_take(iq, positions)
                old = candidate["fractional_tracking_cfo_hz"]
                half_width = rate / 2 - np.max(np.abs(edge_frequencies_hz(probe["edge"])))
                lower = int(np.ceil((-half_width - old) * 4.4e-6))
                upper = int(np.floor((half_width - old) * 4.4e-6))
                aliases = sorted(set(range(lower, upper + 1)) | {0})
                estimates = []
                for alias in aliases:
                    anchor = old + alias / 4.4e-6
                    value = estimate_edge_pilot_frame_cfo(
                        compact,
                        rate,
                        frame_start_sample=probe["valid_start_counter"] + round(start),
                        acquisition_absolute_cfo_hz=anchor,
                        edge=probe["edge"],
                    )
                    estimates.append(dict(alias=alias, **asdict(value)))
                supported = [v for v in estimates if v["measurement_supported"]]
                winner = max(
                    supported or estimates,
                    key=lambda v: (
                        v["coherence_margin"] if v["coherence_margin"] is not None else -np.inf
                    ),
                )
                row = dict(
                    **{k: v for k, v in point.items() if k not in ("probe", "candidate")},
                    original_glrt_cfo_hz=old,
                    original_margin=candidate["fractional_margin"],
                    visit_index=visit,
                    epoch_samples=epoch,
                    frame_index=frame,
                    iq_sha256=window.iq_sha256,
                    source_segment_manifest_sha256=segment["manifest_digest"],
                    branches=estimates,
                    supported_branches=len(supported),
                    best_alias=winner["alias"],
                    best_supported=winner["measurement_supported"],
                    refined_native_cfo_hz=None
                    if winner["absolute_cfo_hz"] is None
                    else winner["absolute_cfo_hz"] - winner["alias"] / 4.4e-6,
                    elapsed_seconds=time.monotonic() - started,
                )
                results.append(row)
                write(output / "results.json", results)
            needed.remove(visit)
            if not needed:
                break
        if not needed:
            break
    if needed or len(results) != len(chosen):
        raise ValueError("bounded panel did not recover every selected original point")
    write(
        output / "summary.json",
        dict(
            selected=len(chosen),
            evaluated=len(results),
            supported=sum(r["best_supported"] for r in results),
            new_acquisition=False,
            elapsed_seconds=time.monotonic() - started,
            geographic_estimate=False,
        ),
    )
    print(json.dumps(json.loads((output / "summary.json").read_text())), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=("DS22-001", "DSX01-S01"), required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    q = Path("/mnt/qnap01")
    if a.output.resolve() == q or q in a.output.resolve().parents:
        p.error("QNAP is read-only")
    run(a.case, a.output)
