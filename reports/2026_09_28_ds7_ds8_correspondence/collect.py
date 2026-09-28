"""Pilot-selected DS8 study excerpts and independent known-site Doppler labels."""

import argparse
import dataclasses
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "local"
sys.path.insert(0, str(ROOT / "reports/2026_09_27_ds7_satellite_annotations"))
from annotate import geometry, predict, scores  # noqa: E402


def main():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    parser = argparse.ArgumentParser()
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--labels", action="store_true")
    parser.add_argument("--start-index", type=int, default=0)
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    path = ROOT / "reports/2026_09_28_ds8_post_ds7/manifest.json"
    manifest = json.loads(path.read_text())
    inputs = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    if not args.export and not args.labels:
        rows = []
        for cap in manifest["captures"]:
            if cap["sample_rate_hz"] != 10000000:
                continue
            sid = cap["session_id"]
            try:
                raw = inputs.load(sid)
                assert raw.input_manifest_sha256 == cap["manifest_sha256"]
                choices = [
                    (p, c)
                    for p in raw.probes
                    if p.edge == "upper" and p.probe_start_ms == 0
                    for c in p.candidates
                    if c.passed_fractional_margin_gate
                ]
                if not choices:
                    raise ValueError("No qualified upper-edge candidate")
                p, c = max(choices, key=lambda pc: pc[1].fractional_margin)
                rows.append(
                    dict(
                        session_id=sid,
                        manifest_sha256=cap["manifest_sha256"],
                        analysis_manifest_sha256=raw.analysis_manifest_sha256,
                        start_utc_ns=cap["capture_start_utc_ns"],
                        probe={k: v for k, v in dataclasses.asdict(p).items() if k != "candidates"},
                        candidate=dataclasses.asdict(c),
                    )
                )
            except Exception as e:
                rows.append(dict(session_id=sid, error=str(e)))
            print(
                sid,
                rows[-1].get("error", rows[-1].get("candidate", {}).get("fractional_margin")),
                flush=True,
            )
        eligible = [r for r in rows if "error" not in r]
        chosen = [
            max(list(group), key=lambda r: r["candidate"]["fractional_margin"])
            for group in np.array_split(np.array(eligible, dtype=object), min(6, len(eligible)))
        ]
        result = dict(
            ds8_manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            survey=rows,
            selected=chosen,
            policy=(
                "At most six chronological strata of eligible 10 MS/s recordings; "
                "strongest cached upper-edge pilot in each. "
                "Selection precedes unknown-bit inspection."
            ),
        )
        (OUT / "selection.json").write_text(json.dumps(result, indent=2) + "\n")
        inputs.close()
        return
    selection = json.loads((OUT / "selection.json").read_text())
    reader = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    for number, selected in enumerate(selection["selected"]):
        if number < args.start_index:
            continue
        folder = OUT / f"ds8-{number}"
        if args.labels:
            inv = json.loads((folder / "inventory.json").read_text())
            raw = inputs.load(selected["session_id"])
            chosen = []
            for e in inv["exports"]:
                p = next(
                    p
                    for p in raw.probes
                    if p.visit_index == e["probe"]["visit_index"]
                    and p.receiver_id == e["probe"]["receiver_id"]
                    and p.probe_index == e["probe"]["probe_index"]
                    and p.edge == e["probe"]["edge"]
                )
                c = next(
                    c for c in p.candidates if c.candidate_rank == e["candidate"]["candidate_rank"]
                )
                chosen.append((p, c))
            labels = label(raw, chosen, selected["session_id"])
            (folder / "labels.json").write_text(json.dumps(labels, indent=2) + "\n")
            print(number, labels, flush=True)
            continue
        if (folder / "labels.json").exists():
            continue
        folder.mkdir(exist_ok=True)
        sid = selected["session_id"]
        raw = inputs.load(sid)
        assert raw.input_manifest_sha256 == selected["manifest_sha256"]
        session = reader.inspect(sid)
        assert session.manifest_sha256 == raw.input_manifest_sha256
        index = selected["probe"]["visit_index"]
        visit, values = reader.read_visit_ci16(session, index)
        exports = []
        chosen = []
        for rx in [0, 1]:
            choices = [
                (p, c)
                for p in raw.probes
                if p.visit_index == index
                and p.receiver_id == rx
                and p.probe_start_ms == 0
                and p.edge == "upper"
                for c in p.candidates
                if c.passed_fractional_margin_gate
                and abs(c.integer_epoch_sample - selected["candidate"]["integer_epoch_sample"]) < 5
            ]
            if not choices:
                raise ValueError(f"No matched peer: {sid}/{index}/RX{rx}")
            p, c = max(choices, key=lambda pc: pc[1].fractional_margin)
            chosen.append((p, c))
            excerpt = values[:, rx, :].copy()
            name = f"visit-{index}-rx-{rx}"
            np.save(folder / (name + ".npy"), excerpt)
            exports.append(
                dict(
                    name=name,
                    session_id=sid,
                    visit=visit.model_dump(mode="json"),
                    probe={k: v for k, v in dataclasses.asdict(p).items() if k != "candidates"},
                    candidate=dataclasses.asdict(c),
                    sample_rate_hz=10000000,
                    excerpt_start_in_visit=0,
                    excerpt_samples=len(excerpt),
                    excerpt_sha256=hashlib.sha256(excerpt.tobytes()).hexdigest(),
                )
            )
        (folder / "inventory.json").write_text(
            json.dumps(
                dict(
                    manifest_sha256=session.manifest_sha256,
                    exports=exports,
                    selection=selection["policy"],
                ),
                indent=2,
            )
            + "\n"
        )
        labels = label(raw, chosen, sid)
        (folder / "labels.json").write_text(json.dumps(labels, indent=2) + "\n")
        print(
            number,
            sid,
            index,
            [(r.get("receiver_id"), r.get("candidate_name")) for r in labels],
            flush=True,
        )
    reader.close()
    inputs.close()


def label(raw, chosen, sid):
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs

    from leo.operations.tle_archive import TleArchiveReader

    class Inputs:
        def load(self, name):
            assert name == sid
            return raw

    prepared = prepare_adaptive_tle_position_inputs(
        sid, inputs=Inputs(), archive=TleArchiveReader(Path("/var/lib/leo/tle"))
    )
    points = project_scanner_candidates(raw)
    graph = reconstruct_persistent_hop_trajectories(
        points, config=PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
    )
    numerical = {t.track_id: t for t in prepared.tracks}
    assert set(numerical) <= {t.tracklet_id for t in graph.tracklets}
    if chosen is None:
        by_id = {p.candidate_id: p for p in points}
        chosen = []
        for track in graph.tracklets:
            if track.tracklet_id not in numerical:
                continue
            eligible = [
                by_id[p.candidate_id] for p in track.points if by_id[p.candidate_id].edge == "upper"
            ]
            pairs = []
            for point in eligible:
                for probe in raw.probes:
                    if (
                        (probe.visit_index, probe.receiver_id, probe.probe_index)
                        != (point.visit_index, point.receiver_id, point.probe_index)
                        or probe.probe_start_ms != 0
                        or probe.edge != "upper"
                    ):
                        continue
                    for candidate in probe.candidates:
                        if candidate.candidate_rank == point.candidate_rank:
                            pairs.append((probe, candidate))
            if pairs:
                chosen.append(max(pairs, key=lambda pc: pc[1].fractional_margin))
    pose = json.loads(
        (ROOT / "reports/2026_09_28_ds8_post_ds7/pose" / (sid + ".json")).read_text()
    )["pose_authority"]
    rec, basis = geometry(pose["latitude_deg"], pose["longitude_deg"])
    results = []
    for probe, candidate in chosen:
        ids = {
            p.candidate_id
            for p in points
            if p.visit_index == probe.visit_index
            and p.receiver_id == probe.receiver_id
            and p.probe_index == probe.probe_index
            and p.candidate_rank == candidate.candidate_rank
            and abs(p.measured_cfo_hz - candidate.fractional_tracking_cfo_hz) < 1e-6
        }
        tracks = [
            t
            for t in graph.tracklets
            if any(p.candidate_id in ids for p in t.points) and t.tracklet_id in numerical
        ]
        if len(tracks) != 1:
            results.append(
                dict(
                    receiver_id=probe.receiver_id,
                    status="unresolved_track_membership",
                    tracks=len(tracks),
                    projected_matches=len(ids),
                    unfiltered_tracks=[
                        t.tracklet_id
                        for t in graph.tracklets
                        if any(p.candidate_id in ids for p in t.points)
                    ],
                    numerical_tracks=len(numerical),
                )
            )
            continue
        tr = numerical[tracks[0].tracklet_id]
        times = np.asarray(tr.times_s)
        mask = np.arange(len(times)) < max(3, min(len(times) - 3, int(0.6 * len(times))))
        cat = prepared.catalogue
        pos, vel, ids0 = propagate_candidate_states(
            cat,
            np.arange(len(cat.satellite_numbers)),
            prepared.start_utc_ns,
            np.median(times) + np.array([-0.001, 0.0, 0.001]),
            np.array([0.0]),
        )
        active = ids0[predict(pos[:, 0], vel[:, 0], rec, basis)[2][:, 1] >= -2]
        pos, vel, ids0 = propagate_candidate_states(
            cat, active, prepared.start_utc_ns, times, np.array([0.0])
        )
        pred, az, el, ranges = predict(pos[:, 0], vel[:, 0], rec, basis)
        train, hold, offset, residual = scores(tr.measured_hz, pred, mask)
        valid = np.mean(el >= 0, axis=1) >= 0.95
        if np.sum(valid) < 2:
            results.append(
                dict(receiver_id=probe.receiver_id, status="unresolved_visible_candidates")
            )
            continue
        order = np.argsort(np.where(valid, train, np.inf))
        best, second = order[:2]
        design = np.c_[np.ones(len(times)), times - times[mask].mean()]
        null = np.linalg.lstsq(design[mask], tr.measured_hz[mask], rcond=None)[0]
        null_rms = float(np.sqrt(np.mean((tr.measured_hz[~mask] - design[~mask] @ null) ** 2)))
        qualified = bool(
            valid[best]
            and len(times) >= 20
            and times[-1] - times[0] >= 10
            and hold[best] <= 250
            and train[second] - train[best] >= 100
            and hold[second] - hold[best] >= 100
            and null_rms - hold[best] >= 25
        )
        results.append(
            dict(
                receiver_id=probe.receiver_id,
                session_id=sid,
                probe={k: v for k, v in dataclasses.asdict(probe).items() if k != "candidates"},
                candidate=dataclasses.asdict(candidate),
                track_id=tr.track_id,
                start_utc_ns=int(prepared.start_utc_ns + times[0] * 1e9),
                end_utc_ns=int(prepared.start_utc_ns + times[-1] * 1e9),
                observations=len(times),
                support=[
                    dict(
                        visit_index=p.visit_index,
                        receiver_id=p.receiver_id,
                        probe_index=p.probe_index,
                        candidate_rank=p.candidate_rank,
                        measured_cfo_hz=p.measured_cfo_hz,
                    )
                    for point in tracks[0].points
                    for p in [next(p for p in points if p.candidate_id == point.candidate_id)]
                ],
                candidate_name=cat.names[ids0[best]],
                norad_id=int(cat.satellite_numbers[ids0[best]]),
                status="conditional_doppler_label" if qualified else "tentative_doppler_label",
                train_rms_hz=float(train[best]),
                validation_rms_hz=float(hold[best]),
                runner_up_gap_hz=float(train[second] - train[best]),
                null_rms_hz=null_rms,
                azimuth_mid_deg=float(az[best, len(times) // 2]),
                elevation_mid_deg=float(el[best, len(times) // 2]),
                offset_hz=float(offset[best]),
                catalogue_size=len(cat.satellite_numbers),
                tested_visible_candidates=len(active),
                snapshot_sha256=prepared.snapshot_digest,
                alternatives=[
                    dict(
                        name=cat.names[ids0[j]],
                        norad_id=int(cat.satellite_numbers[ids0[j]]),
                        train_rms_hz=float(train[j]),
                        validation_rms_hz=float(hold[j]),
                    )
                    for j in order[:3]
                ],
                limitation=(
                    "Geometric inference, not decoded identity; no DS7 shortlist "
                    "restriction. Common clock/orbit error remains possible."
                ),
            )
        )
    return results


if __name__ == "__main__":
    main()
