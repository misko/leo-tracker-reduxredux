"""Read-only bounded expansion: four preselected later DS7 10 MS/s sessions."""

import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "local/expanded"


def main():
    OUT.mkdir(exist_ok=True)
    path = ROOT / "reports/2026_09_27_ds7_post_ds6/manifest.json"
    manifest = json.loads(path.read_text())
    captures = [r for r in manifest["captures"] if r["sample_rate_hz"] == 10000000]
    store = AdaptiveHopIqStore(Path(manifest["source_bulk_root"]), read_only=True)
    inputs = ScannerTrackingInputStore(Path(manifest["source_bulk_root"]))
    exports, inventory = [], []
    for index in [4, 9, 14, 18]:
        capture = captures[index]
        sid = capture["session_id"]
        session = store.inspect(sid)
        assert session.manifest_sha256 == capture["manifest_sha256"]
        raw = inputs.load(sid)
        assert raw.input_manifest_sha256 == session.manifest_sha256
        candidates = sorted(
            [
                (c.fractional_margin, p, c)
                for p in raw.probes
                for c in p.candidates
                if c.passed_fractional_margin_gate and p.edge == "upper"
            ],
            key=lambda r: r[0],
            reverse=True,
        )
        seen = set()
        with store.reader(sid, expected=session) as reader:
            for margin, probe, candidate in candidates:
                if probe.visit_index in seen:
                    continue
                seen.add(probe.visit_index)
                visit, values = reader.read_visit_ci16(probe.visit_index)
                start = round(probe.probe_start_ms * raw.sample_rate_hz / 1000)
                excerpt = values[start : start + 200000, probe.receiver_id, :].copy()
                assert len(excerpt) == 200000
                name = f"{sid}-visit-{probe.visit_index}-rx-{probe.receiver_id}"
                np.save(OUT / (name + ".npy"), excerpt)
                exports.append(
                    dict(
                        name=name,
                        session_id=sid,
                        manifest_sha256=session.manifest_sha256,
                        analysis_manifest_sha256=raw.analysis_manifest_sha256,
                        visit=visit.model_dump(mode="json"),
                        probe={
                            k: v for k, v in dataclasses.asdict(probe).items() if k != "candidates"
                        },
                        candidate=dataclasses.asdict(candidate),
                        sample_rate_hz=raw.sample_rate_hz,
                        excerpt_start_in_visit=start,
                        excerpt_samples=len(excerpt),
                        excerpt_sha256=hashlib.sha256(excerpt.tobytes()).hexdigest(),
                    )
                )
                print(name, margin, flush=True)
                if len(seen) == 2:
                    break
        inventory.append(dict(session_id=sid, qualified_upper_candidates=len(candidates)))
    inputs.close()
    (OUT / "inventory.json").write_text(
        json.dumps(
            dict(
                dataset_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                reader_release=manifest["storage_reader_release"],
                captures=inventory,
                exports=exports,
                selection=(
                    "10 MS/s chronological indices 4,9,14,18; "
                    "top two distinct upper-edge pilot visits each"
                ),
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
