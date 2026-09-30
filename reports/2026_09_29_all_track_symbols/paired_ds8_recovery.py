"""Bounded paired recovery of an already recorded DS8 candidate visit."""

import argparse
import dataclasses
import hashlib
import json
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import numpy as np  # noqa: E402
from decode_tracks import SEED, codebook, recover, slots  # noqa: E402
from local_header_recovery import audit  # noqa: E402
from ten_msps_atlas import classify  # noqa: E402


def main():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    parser = argparse.ArgumentParser()
    parser.add_argument("--unit", default="DS8-F039")
    parser.add_argument("--visit", type=int, default=1498)
    parser.add_argument("--receiver", type=int, choices=[0, 1], default=1)
    args = parser.parse_args()
    tag = f"{args.unit}-v{args.visit}"
    legacy = args.unit == "DS8-F039" and args.visit == 1498
    out = BASE / ("local/paired-ds8" if legacy else f"local/paired-ds8-{tag}")
    out.mkdir(exist_ok=True)
    census = json.loads((BASE / "local/census.json").read_text())
    capture = next(c for c in census["captures"] if c["unit"] == args.unit)
    selection_path = BASE / f"local/ds8-fourteen-frames/decoded/{args.unit}/results.json"
    prior = next(
        r
        for r in json.loads(selection_path.read_text())["rows"]
        if r["visit"] == args.visit
        and r["receiver"] == args.receiver
        and r["status"] == "qualified"
    )
    inventory_path = BASE.parent / "2026_09_28_signal_clustering/local/inventory.json"
    aliases = [
        r["signal"]
        for r in json.loads(inventory_path.read_text())
        if r["session"] == capture["session"] and r["visit"] == args.visit
    ]
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    inputs = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        raw = inputs.load(capture["session"])
        assert raw.input_manifest_sha256 == capture["capture_manifest"]
        assert raw.analysis_manifest_sha256 == capture["analysis_manifest"]
        probes = [p for p in raw.probes if p.visit_index == args.visit]
        assert all(
            p.channel == prior["channel"]
            and p.edge == prior["edge"]
            and p.actual_rf_hz == prior["actual_rf_hz"]
            for p in probes
        )
        selected = [
            next(p for p in probes if p.receiver_id == rx and p.probe_index == 0) for rx in range(2)
        ]
        assert selected[0].valid_start_counter == selected[1].valid_start_counter
        epoch = (
            prior["candidate"]["integer_epoch_sample"]
            + prior["candidate"]["fractional_epoch_offset_samples"]
        )
        candidates = []
        for rx, probe in enumerate(selected):
            eligible = [
                c
                for c in probe.candidates
                if abs(c.integer_epoch_sample + c.fractional_epoch_offset_samples - epoch) < 2
                and c.passed_fractional_margin_gate
            ]
            if rx == args.receiver:
                eligible = [
                    c for c in eligible if c.candidate_rank == prior["candidate"]["candidate_rank"]
                ]
            if not eligible:
                raise ValueError(f"No timing-compatible pilot candidate for RX{rx}")
            candidates.append(max(eligible, key=lambda c: (c.fractional_margin, -c.candidate_rank)))
        epochs = [c.integer_epoch_sample + c.fractional_epoch_offset_samples for c in candidates]
        assert abs(epochs[0] - epochs[1]) < 2
        assert (
            abs(
                candidates[args.receiver].fractional_tracking_cfo_hz
                - prior["candidate"]["fractional_tracking_cfo_hz"]
            )
            < 1e-6
        )
        with store.reader(capture["session"]) as reader:
            _, values = reader.read_visit_ci16(args.visit)
        arrays, sources = {}, []
        with tempfile.TemporaryDirectory(dir=out) as temp:
            for rx, (probe, candidate) in enumerate(zip(selected, candidates, strict=True)):
                assert probe.probe_start_ms == 0
                excerpt = values[: min(len(values), round(0.120 * capture["rate"])), rx, :].copy()
                np.save(Path(temp) / "stream.npy", excerpt)
                p = dataclasses.asdict(probe)
                p.pop("candidates")
                row = dict(
                    name="stream",
                    sample_rate_hz=capture["rate"],
                    probe=p,
                    candidate=dataclasses.asdict(candidate),
                    excerpt_sha256=hashlib.sha256(excerpt.tobytes()).hexdigest(),
                )
                bins, z, meta = recover(row, Path(temp), 90, all_supported_bins=True)
                arrays.update(
                    {
                        f"bins{rx}": bins,
                        f"z{rx}": z.astype(np.complex64),
                        f"metadata{rx}": json.dumps(meta),
                    }
                )
                sources.append(dict(row, samples=len(excerpt)))
        path = out / f"{tag}-soft.npz"
        np.savez_compressed(path, **arrays)
    finally:
        inputs.close()
        store.close()
    data = np.load(path)
    metadata = [json.loads(str(data[f"metadata{rx}"])) for rx in range(2)]
    bins = np.intersect1d(data["bins0"], data["bins1"])
    bins = bins[~np.isin(bins, np.union1d(metadata[0]["pilot_bins"], metadata[1]["pilot_bins"]))]
    a, b = [data[f"z{rx}"][:, :, np.searchsorted(data[f"bins{rx}"], bins)] for rx in range(2)]
    frames = sorted(set(metadata[0]["evaluation_frames"]) & set(metadata[1]["evaluation_frames"]))
    frames = [
        f
        for f in frames
        if min(m["diagnostics"][f]["held_pilot_coherence"] for m in metadata) > 0.5
    ]
    words = np.array([[1 if b == "1" else -1 for b in w] for w in codebook(list(map(int, SEED)))])
    rng = np.random.default_rng(20260929)
    windows = [
        dict(
            frame=f,
            **classify(a[f, 192:224], b[f, 192:224], slots(bins, np.arange(194, 226)), words, rng),
        )
        for f in frames
    ]
    # Existing audit includes its saved bins, so supply a data-only copy to exclude pilots.
    header_path = out / f"{tag}-data-soft.npz"
    np.savez_compressed(
        header_path,
        bins0=bins,
        bins1=bins,
        z0=a,
        z1=b,
        metadata0=data["metadata0"],
        metadata1=data["metadata1"],
    )
    header = audit(header_path)
    result = dict(
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        selection_source_sha256=hashlib.sha256(selection_path.read_bytes()).hexdigest(),
        selected_track_id=prior["track_id"],
        prior_inventory_aliases=aliases,
        alias_inventory_sha256=hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
        source_capture=capture,
        sources=sources,
        qualified_frames=frames,
        paired_data_bins=bins.tolist(),
        shapes=[list(a.shape), list(b.shape)],
        soft_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        windows=windows,
        header=header,
    )
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                shapes=result["shapes"],
                qualified_frames=len(frames),
                known_repeat_frames=sum(w["label"] == 1 for w in windows),
                header={k: v for k, v in header.items() if k not in ["raw_signs", "per_symbol"]},
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
