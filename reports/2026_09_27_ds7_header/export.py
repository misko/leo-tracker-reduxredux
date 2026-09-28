"""Bounded, read-only DS7 metadata audit and four strong 10 MHz IQ probes.

Run with the dataset's pinned storage-reader release, not a reference repository.
The native reader verifies compressed and uncompressed chunk digests.
"""

import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "local"


def main():
    OUT.mkdir(exist_ok=True)
    manifest_path = ROOT / "reports/2026_09_27_ds7_post_ds6/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    store = AdaptiveHopIqStore(Path(manifest["source_bulk_root"]), read_only=True)
    audit = []
    for row in manifest["captures"]:
        session = store.inspect(row["session_id"])
        assert session.manifest_sha256 == row["manifest_sha256"]
        geometry = session.manifest.receipt.plan.geometry
        audit.append(
            dict(
                session_id=session.session_id,
                manifest_sha256=session.manifest_sha256,
                sample_rate_hz=geometry.sample_rate_hz,
                bandwidth_hz=geometry.bandwidth_hz,
                targets=[p.target.model_dump(mode="json") for p in geometry.profiles],
            )
        )
    sid = "scan-fw-a40658642d9ade6a"
    inputs = ScannerTrackingInputStore(Path(manifest["source_bulk_root"]))
    raw = inputs.load(sid)
    session = store.inspect(sid)
    assert raw.input_manifest_sha256 == session.manifest_sha256
    candidates = sorted(
        [
            (c.fractional_margin, p, c)
            for p in raw.probes
            for c in p.candidates
            if c.passed_fractional_margin_gate and p.edge == "upper"
        ],
        key=lambda x: x[0],
        reverse=True,
    )
    selected, seen = [], set()
    for _, probe, candidate in candidates:
        if probe.visit_index in seen:
            continue
        seen.add(probe.visit_index)
        selected.append((probe, candidate))
        if len(selected) == 4:
            break
    exports = []
    with store.reader(sid, expected=session) as reader:
        for probe, candidate in selected:
            visit, values = reader.read_visit_ci16(probe.visit_index)
            start = round(probe.probe_start_ms * raw.sample_rate_hz / 1000)
            count = round(raw.probe_ms * raw.sample_rate_hz / 1000)
            excerpt = values[start : start + count, probe.receiver_id, :].copy()
            assert len(excerpt) == count
            name = f"visit-{probe.visit_index}-rx-{probe.receiver_id}"
            np.save(OUT / (name + ".npy"), excerpt)
            exports.append(
                dict(
                    name=name,
                    session_id=sid,
                    visit=visit.model_dump(mode="json"),
                    probe={k: v for k, v in dataclasses.asdict(probe).items() if k != "candidates"},
                    candidate=dataclasses.asdict(candidate),
                    sample_rate_hz=raw.sample_rate_hz,
                    excerpt_start_in_visit=start,
                    excerpt_samples=count,
                    excerpt_sha256=hashlib.sha256(excerpt.tobytes()).hexdigest(),
                )
            )
    inputs.close()
    (OUT / "inventory.json").write_text(
        json.dumps(
            dict(
                dataset_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                reader_release=manifest["storage_reader_release"],
                captures=audit,
                selection=(
                    "four distinct visits with highest cached fractional pilot margin; "
                    "upper edge; 10 MS/s"
                ),
                analysis_manifest_sha256=raw.analysis_manifest_sha256,
                exports=exports,
            ),
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            dict(
                recordings=len(audit),
                excerpts=len(exports),
                exported_complex_samples=sum(x["excerpt_samples"] for x in exports),
            )
        )
    )


if __name__ == "__main__":
    main()
