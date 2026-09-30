"""Choose peer acquisition alternatives on calibration-frame pilots only."""

import dataclasses
import hashlib
import json
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import numpy as np  # noqa: E402
from decode_tracks import recover  # noqa: E402


def choose(rows):
    return max(rows, key=lambda r: (r["calibration_median"], -r["candidate_rank"]))


def main():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    out = BASE / "local/peer-candidates"
    out.mkdir(exist_ok=True)
    inputs = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    results = []
    try:
        for unit, visit, peer in [("DS8-F027", 19, 1), ("DS8-F039", 84, 0)]:
            tag = f"{unit}-v{visit}"
            prior_path = BASE / f"local/paired-ds8-{tag}/summary.json"
            prior = json.loads(prior_path.read_text())
            capture = prior["source_capture"]
            source = prior["sources"][peer]
            raw = inputs.load(capture["session"])
            assert raw.input_manifest_sha256 == capture["capture_manifest"]
            assert raw.analysis_manifest_sha256 == capture["analysis_manifest"]
            probe = next(
                p
                for p in raw.probes
                if p.visit_index == visit and p.receiver_id == peer and p.probe_index == 0
            )
            epoch = (
                source["candidate"]["integer_epoch_sample"]
                + source["candidate"]["fractional_epoch_offset_samples"]
            )
            unique = {}
            for candidate in probe.candidates:
                ce = candidate.integer_epoch_sample + candidate.fractional_epoch_offset_samples
                if not candidate.passed_fractional_margin_gate or abs(ce - epoch) >= 2:
                    continue
                key = (round(ce, 6), round(candidate.fractional_tracking_cfo_hz, 6))
                if key not in unique or candidate.candidate_rank < unique[key].candidate_rank:
                    unique[key] = candidate
            assert unique
            with store.reader(capture["session"]) as reader:
                _, values = reader.read_visit_ci16(visit)
            excerpt = values[: source["samples"], peer, :].copy()
            assert hashlib.sha256(excerpt.tobytes()).hexdigest() == source["excerpt_sha256"]
            rows = []
            with tempfile.TemporaryDirectory(dir=out) as temp:
                np.save(Path(temp) / "stream.npy", excerpt)
                for candidate in unique.values():
                    row = dict(source, candidate=dataclasses.asdict(candidate), name="stream")
                    bins, z, meta = recover(row, Path(temp), 90, all_supported_bins=True)
                    q = [d["held_pilot_coherence"] for d in meta["diagnostics"]]
                    cal = [q[f] for f in meta["calibration_frames"]]
                    ev = [q[f] for f in meta["evaluation_frames"]]
                    frames = [f for f in meta["evaluation_frames"] if q[f] > 0.5]
                    path = out / f"{tag}-rx{peer}-rank{candidate.candidate_rank}.npz"
                    np.savez_compressed(
                        path, bins=bins, z=z.astype(np.complex64), metadata=json.dumps(meta)
                    )
                    rows.append(
                        dict(
                            candidate_rank=candidate.candidate_rank,
                            candidate=dataclasses.asdict(candidate),
                            calibration_median=float(np.median(cal)),
                            evaluation_median=float(np.median(ev)),
                            evaluation_max=float(max(ev)),
                            qualified_frames=frames,
                            artifact=str(path),
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        )
                    )
            selected = choose(rows)
            d = np.load(BASE / f"local/paired-ds8-{tag}/{tag}-soft.npz")
            source_meta = json.loads(str(d[f"metadata{1 - peer}"]))
            source_ok = {
                f
                for f in source_meta["evaluation_frames"]
                if source_meta["diagnostics"][f]["held_pilot_coherence"] > 0.5
            }
            results.append(
                dict(
                    visit=tag,
                    peer_receiver=peer,
                    candidates=rows,
                    prior_sha256=hashlib.sha256(prior_path.read_bytes()).hexdigest(),
                    selected_rank=selected["candidate_rank"],
                    jointly_qualified_frames=sorted(source_ok & set(selected["qualified_frames"])),
                )
            )
    finally:
        inputs.close()
        store.close()
    result = dict(
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), results=results
    )
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
