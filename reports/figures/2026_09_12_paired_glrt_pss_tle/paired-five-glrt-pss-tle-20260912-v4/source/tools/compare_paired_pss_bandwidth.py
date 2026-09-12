"""Bounded offline, GLRT-selected three-lane PSS bandwidth experiment.

Reads a frozen database inventory and RecordingStore; never updates products.
Selection sees GLRT only. PSS uses blind timing/CFO acquisition in every block.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.analysis.standard.native_pss import starlink_pss_channel_reference_hz
from leo.analysis.starlink import pss_timing
from leo.analysis.starlink.pss_search import (
    PssBankSearchConfig,
    PssTrackAssociationConfig,
    associate_pss_timing_tracks,
    compile_pss_projection,
    project_pss_block,
    search_pss_frame_timing_bank,
)
from leo.analysis.starlink.pss_timing import PssTimingSearchConfig
from leo.storage import RecordingStore

POLICY = dict(
    interval_s=2.25,
    block_s=0.25,
    grid_s=0.25,
    whole_pass_fraction=0.8,
    interval_pass_fraction=0.95,
    interval_median_margin=0.25,
    count=5,
    ranking="descending weaker-lane interval median GLRT margin; capture ID tie break",
)


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def product(root: Path, row: dict) -> dict:
    path = root / row["logical_uri"].removeprefix("bulk://")
    raw = path.read_bytes()
    if "sha256:" + hashlib.sha256(raw).hexdigest() != row["digest"]:
        raise ValueError(f"product digest mismatch: {path}")
    return json.loads(raw)


def windows(document: dict) -> list[dict]:
    return [w for s in document["segments"] for w in s["windows"]]


def segment_for(binding: dict, start_s: float, duration_s: float) -> int | None:
    rate = binding["sample_rate_hz"]
    start = round(start_s * rate)
    stop = start + round(duration_s * rate)
    for s in binding["validity_inventory"]["segments"]:
        if s["device_sample_start"] <= start and stop <= s["device_sample_stop"]:
            return s["segment_index"]
    return None


def interval_metrics(rows: list[dict], start: float, duration: float) -> dict:
    selected = [
        w
        for w in rows
        if w["global_start_time_s"] >= start - 1e-9
        and w["global_end_time_s"] <= start + duration + 1e-9
    ]
    margins = [w["glrt_margin"] for w in selected if w["glrt_margin"] is not None]
    return dict(
        count=len(selected),
        pass_fraction=sum(w["passed_margin_gate"] for w in selected) / max(1, len(selected)),
        median_margin=float(np.median(margins)) if margins else 0.0,
    )


def select(root: Path, out: Path) -> None:
    inventory = json.loads((out / "inventory.json").read_text())
    grouped = defaultdict(list)
    for r in inventory["rows"]:
        grouped[r["capture_id"]].append(r)
    candidates, audit = [], []
    for capture, rows in grouped.items():
        natives = [r for r in rows if r["binding"]["sample_rate_hz"] == 25_000_000]
        for native in natives:
            nb = native["binding"]
            paired = [
                r
                for r in rows
                if r["binding"]["sample_rate_hz"] == 2_500_000
                and (r["binding"]["starlink_channel"], r["binding"]["starlink_edge"])
                == (nb["starlink_channel"], nb["starlink_edge"])
            ]
            nd = product(root, native)
            for narrow in paired:
                pd = product(root, narrow)
                whole = {
                    k: d["accounting"]["passing_count"] / max(1, d["accounting"]["valid_count"])
                    for k, d in (("native", nd), ("recorded", pd))
                }
                log = dict(capture_id=capture, whole_pass_fraction=whole, qualifying_intervals=0)
                audit.append(log)
                if min(whole.values()) < POLICY["whole_pass_fraction"]:
                    continue
                pb = narrow["binding"]
                offset = (
                    nb["timing"]["first_estimate_utc_ns"] - pb["timing"]["first_estimate_utc_ns"]
                ) / 1e9
                nw, pw = windows(nd), windows(pd)
                duration = POLICY["interval_s"]
                best = None
                for start in np.arange(
                    0,
                    nb["logical_sample_count"] / nb["sample_rate_hz"] - duration,
                    POLICY["grid_s"],
                ):
                    start = float(start)
                    if (
                        segment_for(nb, start, duration) is None
                        or segment_for(pb, start + offset, duration) is None
                    ):
                        continue
                    metrics = {
                        "native": interval_metrics(nw, start, duration),
                        "recorded": interval_metrics(pw, start + offset, duration),
                    }
                    if any(
                        m["count"] < 200
                        or m["pass_fraction"] < POLICY["interval_pass_fraction"]
                        or m["median_margin"] < POLICY["interval_median_margin"]
                        for m in metrics.values()
                    ):
                        continue
                    log["qualifying_intervals"] += 1
                    score = min(m["median_margin"] for m in metrics.values())
                    if best is None or score > best["selection_score"]:
                        best = dict(
                            capture_id=capture,
                            native=native,
                            recorded=narrow,
                            native_start_s=start,
                            recorded_start_s=start + offset,
                            start_offset_s=offset,
                            whole_pass_fraction=whole,
                            interval_metrics=metrics,
                            selection_score=score,
                        )
                if best:
                    candidates.append(best)
        if natives:
            print(f"GLRT review {capture}: {len(candidates)} eligible pairs", flush=True)
    # One pair per dwell, irrespective of how many receiver scopes it contains.
    candidates.sort(key=lambda x: (-x["selection_score"], x["capture_id"]))
    chosen, seen = [], set()
    for c in candidates:
        if c["capture_id"] not in seen:
            seen.add(c["capture_id"])
            chosen.append(c)
        if len(chosen) == POLICY["count"]:
            break
    write(
        out / "selection.json",
        dict(
            policy=POLICY,
            audit=audit,
            selected=chosen,
            eligible_pair_count=len(candidates),
            eligible_dwell_count=len({c["capture_id"] for c in candidates}),
        ),
    )
    if len(chosen) != POLICY["count"]:
        raise ValueError(f"only {len(chosen)} dwells meet the frozen GLRT gates")
    print([(c["capture_id"], c["selection_score"], c["native_start_s"]) for c in chosen])


def run(root: Path, out: Path, index: int) -> None:
    selection = json.loads((out / "selection.json").read_text())
    c = selection["selected"][index]
    dest = out / c["capture_id"]
    dest.mkdir(exist_ok=True)
    bank = PssBankSearchConfig()
    timing = PssTimingSearchConfig()
    association = PssTrackAssociationConfig()
    write(
        dest / "protocol.json",
        dict(
            selection=c,
            policy=selection["policy"],
            bank=asdict(bank),
            timing=asdict(timing),
            association=asdict(association),
            selection_uses_pss=False,
            acquisition="independent PSS CFO/timing; GLRT-selected interval",
            software_revision="a29d5ca53dddaac2b3ec92751ca0bc072bf75d55",
            tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            pss_timing_source_sha256=hashlib.sha256(
                Path(pss_timing.__file__).read_bytes()
            ).hexdigest(),
        ),
    )
    store = RecordingStore.open_read_only(root)
    try:
        bundle = store.inspect(c["capture_id"])
        if (
            "sha256:" + bundle.manifest_sha256.removeprefix("sha256:")
            != c["native"]["manifest_digest"]
        ):
            raise ValueError("manifest changed since inventory")
        modes_by_lane = defaultdict(list)
        for source in ("native", "recorded"):
            b = c[source]["binding"]
            reader = store.reader(bundle, b["stream_id"], verify=True)
            rate = b["sample_rate_hz"]
            reference = starlink_pss_channel_reference_hz(b["starlink_channel"], b["starlink_edge"])
            for block_index in range(round(POLICY["interval_s"] / POLICY["block_s"])):
                start = round((c[f"{source}_start_s"] + block_index * POLICY["block_s"]) * rate)
                span = reader.read_device_span(
                    start, round(POLICY["block_s"] * rate), receiver_ids=(b["receiver_id"],)
                )
                segments = np.unique(span.continuity_segment_ids)
                if not span.valid_samples.all() or len(segments) != 1 or segments[0] < 0:
                    raise ValueError(
                        "selected PSS block crosses missing IQ or a continuity boundary"
                    )
                iq = span.samples[:, 0, 0].astype(np.float32) + 1j * span.samples[:, 0, 1].astype(
                    np.float32
                )
                iq_hash = hashlib.sha256(span.samples.tobytes()).hexdigest()
                for lane in ("native25", "derived2p5") if source == "native" else ("recorded2p5",):
                    projection = compile_pss_projection(
                        input_sample_rate_hz=rate,
                        input_center_frequency_hz=b["tuned_center_frequency_hz"],
                        rf_bandwidth_hz=b["rf_bandwidth_hz"],
                        target_center_frequency_hz=c["recorded"]["binding"][
                            "tuned_center_frequency_hz"
                        ],
                        channel_reference_hz=reference,
                        canonical_output_sample_rate_hz=25_000_000
                        if lane == "native25"
                        else 2_500_000,
                    )
                    block = project_pss_block(
                        iq,
                        projection,
                        input_device_sample_start=start,
                        continuity_segment_index=int(segments[0]),
                    )
                    t = time.monotonic()
                    result = search_pss_frame_timing_bank(
                        block, block_index=block_index, bank_config=bank, timing_config=timing
                    )
                    modes_by_lane[lane].extend(result.modes)
                    write(
                        dest / f"{lane}-{block_index:02}.json",
                        dict(
                            lane=lane,
                            projection=asdict(projection),
                            input_device_sample_start=start,
                            selected_iq_sha256=iq_hash,
                            output_device_sample_start=block.output_device_sample_start,
                            sample_count=len(block.samples),
                            elapsed_s=time.monotonic() - t,
                            result=asdict(result),
                        ),
                    )
                    print(
                        f"{index + 1}/5 {lane} {block_index + 1}/9: "
                        f"{len(result.modes)} modes, {time.monotonic() - t:.1f}s",
                        flush=True,
                    )
        tracks = {
            lane: [asdict(t) for t in associate_pss_timing_tracks(tuple(modes), config=association)]
            for lane, modes in modes_by_lane.items()
        }
        write(dest / "tracks.json", tracks)
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("select", "run"))
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--index", type=int, default=0)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("QNAP is read-only")
    if args.action == "select":
        select(args.bulk_root, args.output)
    else:
        run(args.bulk_root, args.output, args.index)


if __name__ == "__main__":
    main()
