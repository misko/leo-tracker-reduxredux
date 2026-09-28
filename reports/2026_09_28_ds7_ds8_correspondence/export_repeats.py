"""Select cross-dataset repeat targets using geometry and pilots, then read IQ."""

import dataclasses
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from collect import OUT, ROOT


def main():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    prior = ROOT / "reports/2026_09_27_ds7_satellite_annotations/local"
    ds7 = json.loads((prior / "track-annotations.json").read_text())
    inputs = {
        r["session_id"]: r for r in json.loads((prior / "inputs.json").read_text())["recordings"]
    }
    manifest = json.loads((ROOT / "reports/2026_09_27_ds7_post_ds6/manifest.json").read_text())
    ten = {r["session_id"] for r in manifest["captures"] if r["sample_rate_hz"] == 10000000}
    ds7 = [r for r in ds7 if r["status"] == "likely_conditional" and r["session_id"] in ten]
    ds8 = [
        r
        for p in OUT.glob("*-tracks.json")
        for r in json.loads(p.read_text())
        if r.get("status") == "conditional_doppler_label"
    ]
    repeats = [(b, a) for b in ds8 for a in ds7 if a["norad_id"] == b["norad_id"]]
    repeats.sort(
        key=lambda pair: (-pair[0]["candidate"]["fractional_margin"], pair[1]["validation_rms_hz"])
    )
    selection_path = OUT / "repeat-selection.json"
    if not selection_path.exists():
        selected, seen = [], set()
        for b, a in repeats:
            if b["norad_id"] in seen:
                continue
            seen.add(b["norad_id"])
            selected.extend([dict(dataset="DS7", label=a), dict(dataset="DS8", label=b)])
            if len(seen) == 2:
                break
        if not selected:
            raise ValueError("No conditional cross-dataset repeat with 10 MS/s DS7 support")
        selection_path.write_text(
            json.dumps(
                dict(
                    policy="Up to two distinct likely satellites shared across datasets; "
                    "rank DS8 pilot margin, "
                    "then DS7 validation RMS. Selected before decoding these excerpts.",
                    selected=selected,
                ),
                indent=2,
            )
            + "\n"
        )
    selected = json.loads(selection_path.read_text())["selected"]
    extra_path = OUT / "repeat-extra-selection.json"
    if not extra_path.exists():
        targets = {r["label"]["norad_id"] for r in selected}
        used = {
            (r["label"]["session_id"], r["label"]["probe"]["visit_index"])
            for r in selected
            if r["dataset"] == "DS8"
        }
        extra = []
        for row in sorted(ds8, key=lambda r: -r["candidate"]["fractional_margin"]):
            key = row["session_id"], row["probe"]["visit_index"]
            if row["norad_id"] in targets and key not in used:
                extra.append(dict(dataset="DS8", label=row))
                used.add(key)
            if len(extra) == 2:
                break
        extra_path.write_text(
            json.dumps(
                dict(
                    policy="Two additional distinct visits of the selected repeat satellite, "
                    "ranked by pilot margin before decoding their bits.",
                    selected=extra,
                ),
                indent=2,
            )
            + "\n"
        )
    selected += json.loads(extra_path.read_text())["selected"]
    ds7_retry_path = OUT / "repeat-ds7-selection.json"
    if not ds7_retry_path.exists():
        target_ids = {r["label"]["norad_id"] for r in selected}
        used_tracks = {r["label"]["track_id"] for r in selected if r["dataset"] == "DS7"}
        retry = [
            dict(dataset="DS7", label=r)
            for r in ds7
            if r["norad_id"] in target_ids and r["track_id"] not in used_tracks
        ][:2]
        ds7_retry_path.write_text(
            json.dumps(
                dict(
                    policy="Up to two other likely DS7 tracklets of the repeat target; "
                    "strongest bound pilot selected before decoding these excerpts.",
                    selected=retry,
                ),
                indent=2,
            )
            + "\n"
        )
    selected += json.loads(ds7_retry_path.read_text())["selected"]
    source = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    reader = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    started = time.monotonic()
    for number, item in enumerate(selected):
        folder = OUT / f"repeat-{number}"
        if (folder / "labels.json").exists():
            continue
        if (folder / "unavailable.json").exists():
            continue
        row = item["label"]
        sid = row["session_id"]
        raw = source.load(sid)
        if item["dataset"] == "DS8":
            probe = next(
                p
                for p in raw.probes
                if p.visit_index == row["probe"]["visit_index"]
                and p.receiver_id == row["receiver_id"]
                and p.probe_index == row["probe"]["probe_index"]
                and p.edge == "upper"
            )
            candidate = next(
                c
                for c in probe.candidates
                if c.candidate_rank == row["candidate"]["candidate_rank"]
            )
        else:
            export = json.loads(Path(inputs[sid]["tracks"]).read_text())
            assert raw.input_manifest_sha256 == export["manifest_sha256"]
            assert raw.analysis_manifest_sha256 == export["analysis_manifest_sha256"]
            tr = next(t for t in export["tracks"] if t["track_id"] == row["track_id"])
            from leo.analysis.persistent_hop_trajectory import (
                PersistentHopTrajectoryConfig,
                reconstruct_persistent_hop_trajectories,
            )
            from leo.application.scanner_trajectory import project_scanner_candidates

            points = project_scanner_candidates(raw)
            graph = reconstruct_persistent_hop_trajectories(
                points, config=PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
            )
            track = next(t for t in graph.tracklets if t.tracklet_id == tr["track_id"])
            member_ids = {p.candidate_id for p in track.points}
            members = {
                (p.visit_index, p.receiver_id, p.probe_index, p.candidate_rank)
                for p in points
                if p.candidate_id in member_ids
            }
            candidates = []
            for p in raw.probes:
                if p.receiver_id != row["receiver_id"] or p.probe_start_ms != 0:
                    continue
                for c in p.candidates:
                    if (p.visit_index, p.receiver_id, p.probe_index, c.candidate_rank) in members:
                        candidates.append((p, c))
            if not candidates:
                raise ValueError(f"No edge pilot bound to {sid}/{row['track_id']}")
            probe, candidate = max(candidates, key=lambda pc: pc[1].fractional_margin)
        folder.mkdir(exist_ok=True)
        session = reader.inspect(sid)
        assert session.manifest_sha256 == raw.input_manifest_sha256
        visit, values = reader.read_visit_ci16(session, probe.visit_index)
        exports = []
        for rx in (0, 1):
            choices = [
                (p, c)
                for p in raw.probes
                if p.visit_index == probe.visit_index
                and p.receiver_id == rx
                and p.edge == probe.edge
                and p.probe_start_ms == 0
                for c in p.candidates
                if c.passed_fractional_margin_gate
                and abs(c.integer_epoch_sample - candidate.integer_epoch_sample) < 5
            ]
            if not choices:
                (folder / "unavailable.json").write_text(
                    json.dumps(
                        dict(
                            reason="No qualified epoch-matched dual-receiver peer",
                            receiver_id=rx,
                            session_id=sid,
                            visit=probe.visit_index,
                            label=row,
                        ),
                        indent=2,
                    )
                    + "\n"
                )
                print(number, "no dual-receiver peer", sid, probe.visit_index, flush=True)
                break
            p, c = max(choices, key=lambda pc: pc[1].fractional_margin)
            data = values[:, rx, :].copy()
            name = f"visit-{probe.visit_index}-rx-{rx}"
            np.save(folder / (name + ".npy"), data)
            exports.append(
                dict(
                    name=name,
                    session_id=sid,
                    visit=visit.model_dump(mode="json"),
                    probe={k: v for k, v in dataclasses.asdict(p).items() if k != "candidates"},
                    candidate=dataclasses.asdict(c),
                    sample_rate_hz=10000000,
                    excerpt_start_in_visit=0,
                    excerpt_samples=len(data),
                    excerpt_sha256=hashlib.sha256(data.tobytes()).hexdigest(),
                )
            )
        if len(exports) != 2:
            continue
        (folder / "inventory.json").write_text(
            json.dumps(
                dict(
                    dataset=item["dataset"],
                    manifest_sha256=session.manifest_sha256,
                    exports=exports,
                    selection="repeat-selection.json; strongest bound pilot; both RX epoch matched",
                ),
                indent=2,
            )
            + "\n"
        )
        (folder / "labels.json").write_text(json.dumps([row], indent=2) + "\n")
        print(number, item["dataset"], row["norad_id"], sid, probe.visit_index, flush=True)
        if time.monotonic() - started > 60:
            break
    reader.close()
    source.close()


if __name__ == "__main__":
    main()
