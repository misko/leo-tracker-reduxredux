"""Export one existing 120 ms dual-receiver visit, with matched cached epochs."""

import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def main():
    base = Path(__file__).parent / "local"
    out = base / "dual"
    out.mkdir(exist_ok=True)
    inventory = json.loads((base / "inventory.json").read_text())
    original = inventory["exports"][0]
    sid = original["session_id"]
    visit_index = original["probe"]["visit_index"]
    seed = original["candidate"]
    source = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    raw = source.load(sid)
    source.close()
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    session = store.inspect(sid)
    binding = next(r for r in inventory["captures"] if r["session_id"] == sid)
    assert session.manifest_sha256 == binding["manifest_sha256"] == raw.input_manifest_sha256
    visit, values = store.read_visit_ci16(session, visit_index)
    assert len(values) == 1200000
    rows = []
    for receiver in [0, 1]:
        candidates = [
            (p, c)
            for p in raw.probes
            if p.visit_index == visit_index and p.receiver_id == receiver and p.probe_start_ms == 0
            for c in p.candidates
            if c.passed_fractional_margin_gate
            and abs(c.integer_epoch_sample - seed["integer_epoch_sample"]) < 5
        ]
        probe, c = max(candidates, key=lambda pc: pc[1].fractional_margin)
        excerpt = values[:, receiver, :].copy()
        name = f"visit-{visit_index}-rx-{receiver}"
        np.save(out / (name + ".npy"), excerpt)
        rows.append(
            dict(
                name=name,
                session_id=sid,
                visit=visit.model_dump(mode="json"),
                probe={k: v for k, v in dataclasses.asdict(probe).items() if k != "candidates"},
                candidate=dataclasses.asdict(c),
                sample_rate_hz=10000000,
                excerpt_start_in_visit=0,
                excerpt_samples=len(excerpt),
                excerpt_sha256=hashlib.sha256(excerpt.tobytes()).hexdigest(),
            )
        )
        print(name, c, flush=True)
    (out / "inventory.json").write_text(
        json.dumps(
            dict(
                dataset_sha256=inventory["dataset_sha256"],
                reader_release=inventory["reader_release"],
                manifest_sha256=session.manifest_sha256,
                exports=rows,
                selection=(
                    "full 120 ms of prior strongest cached upper-edge visit; "
                    "both receivers; matched epoch"
                ),
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
