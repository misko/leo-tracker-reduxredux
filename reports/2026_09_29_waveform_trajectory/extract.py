"""Read only the selected probe excerpts; preserve exact track/candidate binding."""

import dataclasses
import hashlib
import json
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def main():
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    path = HERE / "plan.json"
    plan = json.loads(path.read_text())
    owner = path.stat()
    for name, digest in plan["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    source = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    inventory = HERE / "inventory.json"
    hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (path, HERE / "extract.py")
    }
    previous = (
        json.loads(inventory.read_text())
        if inventory.exists() and inventory.stat().st_size
        else None
    )
    if previous:
        assert previous["hashes"] == hashes
    rows = previous["rows"] if previous else []
    completed = {(r["unit_id"], r["receiver_id"]) for r in rows}
    for row in rows:
        if row["status"] == "ok":
            assert hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest() == row["sha256"]
    folder = HERE / "local"
    folder.mkdir(exist_ok=True)
    try:
        for session in dict.fromkeys(r["session_id"] for r in plan["selections"]):
            selected = [r for r in plan["selections"] if r["session_id"] == session]
            selected = [r for r in selected if (r["unit_id"], r["receiver_id"]) not in completed]
            if not selected:
                continue
            raw = source.load(session)
            assert raw.input_manifest_sha256 == selected[0]["manifest_sha256"]
            points = project_scanner_candidates(raw)
            graph = reconstruct_persistent_hop_trajectories(
                points, config=PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
            )
            tracks = {t.tracklet_id: t for t in graph.tracklets}
            points = {p.candidate_id: p for p in points}
            probes = {(p.receiver_id, p.visit_index, p.probe_index): p for p in raw.probes}
            with store.reader(session) as reader:
                for selected_row in selected:
                    r = dict(selected_row)
                    t = r.pop("track")
                    try:
                        track = tracks[t["track_id"]]
                        matched = [points[p.candidate_id] for p in track.points]
                        assert [p.visit_index for p in matched] == t["visits"]
                        assert all(
                            abs((p.support_center_utc_ns - r["start_utc_ns"]) / 1e9 - v) < 1e-9
                            for p, v in zip(matched, t["times_s"], strict=True)
                        )
                        point = matched[r["observation_index"]]
                        assert bool(t["training_mask"][r["observation_index"]]) == (
                            r["role"] != "H"
                        )
                        probe = probes[point.receiver_id, point.visit_index, point.probe_index]
                        candidate = next(
                            c for c in probe.candidates if c.candidate_rank == point.candidate_rank
                        )
                        reuse = r.pop("reuse", None)
                        if reuse and reuse["status"] == "ok":
                            assert reuse["candidate"] == dataclasses.asdict(candidate)
                            assert reuse["analysis_manifest_sha256"] == raw.analysis_manifest_sha256
                            out = ROOT / reuse["path"]
                            assert hashlib.sha256(out.read_bytes()).hexdigest() == reuse["sha256"]
                        else:
                            _, samples = reader.read_visit_ci16(point.visit_index)
                            begin = round(probe.probe_start_ms * raw.sample_rate_hz / 1000)
                            iq = samples[
                                begin : begin + round(raw.sample_rate_hz * 0.020),
                                probe.receiver_id,
                                :,
                            ].copy()
                            assert len(iq) == round(raw.sample_rate_hz * 0.020)
                            out = folder / f"{r['unit_id']}-rx{r['receiver_id']}.npy"
                            np.save(out, iq)
                            os.chown(out, owner.st_uid, owner.st_gid)
                        r.update(
                            status="ok",
                            track_id=t["track_id"],
                            candidate=dataclasses.asdict(candidate),
                            edge=probe.edge,
                            actual_rf_hz=probe.actual_rf_hz,
                            path=str(out.relative_to(ROOT)),
                            sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
                            analysis_manifest_sha256=raw.analysis_manifest_sha256,
                        )
                    except Exception as exc:
                        r.update(
                            status="failed",
                            track_id=t["track_id"],
                            reason=f"{type(exc).__name__}: {exc}",
                        )
                    rows.append(r)
                    checkpoint = inventory.with_suffix(".tmp")
                    checkpoint.write_text(
                        json.dumps(dict(hashes=hashes, rows=rows), indent=2) + "\n"
                    )
                    os.chown(checkpoint, owner.st_uid, owner.st_gid)
                    checkpoint.replace(inventory)
    finally:
        source.close()
    os.chown(folder, owner.st_uid, owner.st_gid)
    print(json.dumps(dict(hashes=hashes, rows=rows), indent=2))


if __name__ == "__main__":
    main()
