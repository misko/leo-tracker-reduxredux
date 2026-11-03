"""Bounded reanalysis of eight existing DSX01 IQ windows; no RF acquisition."""

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from dsx01_pilot_clock import FrameClock

ROOT = Path(__file__).resolve().parents[1]


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def select(case):
    """Two fixed quantiles of longest raw curved track per RX/band."""
    from compare_dsx01_retention_localization import Scan

    scan = Scan(case)
    chosen = []
    for receiver in (1, 2):
        for band in (0, 1):
            tracks = [
                scan.tracks[i]
                for i in scan.curved
                if scan.tracks[i]["receiver"] == receiver
                and int(scan.tracks[i]["channel"] > 4) == band
            ]
            track = min(tracks, key=lambda t: (-len(t["times"]), t["key"]))
            for quantile in (0.2, 0.8):
                index = round(quantile * (len(track["times"]) - 1))
                chosen.append(
                    dict(
                        observation_id=track["observation_ids"][index],
                        track=track["key"],
                        receiver=receiver,
                        band=band,
                        quantile=quantile,
                        context_time_s=float(track["times"][index]),
                    )
                )
    return chosen


def extract(case, output, selected_path):
    # Concrete read-only storage ports belong in this tool, never in the kernel.
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource

    started = time.monotonic()
    selected = json.loads(selected_path.read_text())
    if not 1 <= len(selected) <= 8:
        raise ValueError("bounded experiment permits at most eight IQ windows")
    sources = json.loads(
        (ROOT / "reports/2026_10_16_dsx01_fast_association_losses/sources.json").read_text()
    )
    source = next(s for s in sources if "DSX01-" + s["source_id"] == case)
    payload = Path(source["tracking_input_path"]).read_bytes()
    if "sha256:" + hashlib.sha256(payload).hexdigest() != source["tracking_input_sha256"]:
        raise ValueError("original tracking input changed")
    document = json.loads(payload)
    scores = json.loads(
        (ROOT / "reports/2026_10_18_dsx01_causal_repairs/glrt_scores.json").read_text()
    )[case]
    if scores["source_sha256"] != hashlib.sha256(payload).hexdigest():
        raise ValueError("score inventory differs from original tracking input")
    bywindow = {
        (p["receiver_id"] + 1, p["channel"], p["valid_start_counter"]): p
        for p in document["source"]["probes"]
    }
    for point in selected:
        score = scores["scores"][point["observation_id"]]
        probe = bywindow[score["receiver"], score["channel"], score["valid_start_counter"]]
        eligible = [c for c in probe["candidates"] if c["passed_fractional_margin_gate"]]
        winner = max(eligible, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]))
        if abs(winner["fractional_tracking_cfo_hz"] - score["measured_cfo_hz"]) > 1e-8:
            raise ValueError("winning original GLRT CFO differs")
        point.update(probe=probe, winner=winner, score=score)
    output.mkdir(parents=True, exist_ok=False)
    inventory = FastScanStore("/srv/bulk/leo").source(
        document["source"]["session_id"], document["source"]["input_manifest_sha256"]
    )
    arrays, receipts = {}, []
    for segment in inventory["segments"]:
        adapter = FastSegmentSource(segment)
        for window in adapter.windows():
            if time.monotonic() - started > 180:
                raise TimeoutError("bounded existing-IQ read exceeded 180 seconds")
            for number, point in enumerate(selected):
                if point["probe"]["visit_index"] != window.acquisition["global_visit"]:
                    continue
                if window.acquisition["sample_start"] != point["probe"]["valid_start_counter"]:
                    raise ValueError("IQ support differs from original GLRT window")
                if f"iq_{number}" in arrays:
                    raise ValueError("selected IQ window occurs twice")
                receiver = adapter.receiver_ids.index(point["probe"]["receiver_id"])
                raw = window.samples[:, receiver, :]
                arrays[f"iq_{number}"] = raw[:, 0].astype(np.float32) + 1j * raw[:, 1].astype(
                    np.float32
                )
                receipts.append(
                    dict(
                        number=number,
                        **point,
                        iq_sha256=window.iq_sha256,
                        segment_manifest_sha256=segment["manifest_digest"],
                    )
                )
            if len(receipts) == len(selected):
                break
        if len(receipts) == len(selected):
            break
    if len(receipts) != len(selected):
        raise ValueError("not all selected IQ windows were found")
    np.savez_compressed(output / "selected_iq.npz", **arrays)
    write(
        output / "selection.json",
        dict(
            case=case,
            selection="20/80 percent points of longest raw curved track per RX/band",
            selection_uses_GPS_or_satellite_labels=False,
            new_RF_collection=False,
            sample_rate_hz=document["source"]["sample_rate_hz"],
            tracking_input_sha256=source["tracking_input_sha256"],
            inventory_sha256=document["source"]["input_manifest_sha256"],
            elapsed_seconds=time.monotonic() - started,
            windows=sorted(receipts, key=lambda r: r["number"]),
        ),
    )


def analyze(output):
    started = time.monotonic()
    data = json.loads((output / "selection.json").read_text())
    arrays = np.load(output / "selected_iq.npz")
    rate = data["sample_rate_hz"]
    rows = []
    for point in data["windows"]:
        iq = arrays[f"iq_{point['number']}"]
        candidate, probe = point["winner"], point["probe"]
        epoch = candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]
        acquired = candidate["fractional_tracking_cfo_hz"]
        # Three fixed interior frames; carrier/channel phases are independent.
        for frame in (2, 7, 12):
            if time.monotonic() - started > 180:
                raise TimeoutError("bounded frame-clock analysis exceeded 180 seconds")
            origin = epoch + frame * rate / 750
            model = FrameClock(iq, rate, origin, acquired, probe["edge"])
            common, joint = model.fit(symbol_clock=False), model.fit()
            control = FrameClock(iq, rate, origin, acquired, probe["edge"], roll=17).fit()
            halves = [
                FrameClock(iq, rate, origin, acquired, probe["edge"], half=h).fit() for h in (0, 1)
            ]
            row = dict(
                number=point["number"],
                frame=frame,
                track=point["track"],
                observation_id=point["observation_id"],
                receiver=point["receiver"],
                channel=probe["channel"],
                context_time_s=point["context_time_s"],
                original_cfo_hz=acquired,
                common=asdict(common),
                joint=asdict(joint),
                control=asdict(control),
                halves=[asdict(h) for h in halves],
                joint_minus_common_hz=joint.residual_cfo_hz - common.residual_cfo_hz,
                half_cfo_difference_hz=abs(halves[1].residual_cfo_hz - halves[0].residual_cfo_hz),
                half_ppm_difference=abs(halves[1].symbol_clock_ppm - halves[0].symbol_clock_ppm),
            )
            rows.append(row)
            print(
                json.dumps(
                    {
                        k: row[k]
                        for k in ["number", "frame", "joint_minus_common_hz", "half_ppm_difference"]
                    }
                ),
                flush=True,
            )
            write(output / "progress.json", rows)
    write(
        output / "results.json",
        dict(
            case=data["case"],
            rows=rows,
            elapsed_seconds=time.monotonic() - started,
            all_frames_independent=True,
            carrier_search_hz=[-1000, 1000],
            symbol_clock_search_ppm=[-100, 100],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["select", "extract", "analyze"])
    parser.add_argument("--case", default="DSX01-S05")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--selection", type=Path)
    args = parser.parse_args()
    if args.action == "select":
        write(args.output, select(args.case))
    elif args.action == "extract":
        extract(args.case, args.output, args.selection)
    else:
        analyze(args.output)
