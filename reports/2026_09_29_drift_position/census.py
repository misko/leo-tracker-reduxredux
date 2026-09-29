"""Bounded exported-track coverage audit, without loading satellite banks."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
from correction import calibrations, correct_document

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(p):
    return json.loads(p.read_text())


def main():
    donor = HERE.parent / "2026_09_29_rx_track_coherence"
    align = HERE.parent / "2026_09_29_rx_alignment"
    bindings = {}
    for parent in (donor, align):
        inventory = read(parent / "evidence-sha256.json")["sha256"]
        for name, value in inventory.items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value, name
        bindings.update(inventory)
    source = read(donor / "result.json")["scans"]
    published = {s["session_id"]: s for s in read(align / "result.json")["scans"]}
    counts = {ds: Counter() for ds in ("DS7", "DS8", "DS9")}
    details = []
    for scan in source:
        path = ROOT / scan["observations"]
        assert scan["observations"] in bindings
        doc = read(path)
        mapping = calibrations(scan)
        old = published[scan["session_id"]]
        for row in old["rows"]:
            a, b = mapping[row["rx0"]]["fit"], row["models"]["drift"]["fit"]
            assert a["qualified"] == b["qualified"]
            assert a["reason"] == b["reason"]
            if a["qualified"]:
                for key in ("drift_hz_s", "reference_s", "intercept_hz", "condition"):
                    np.testing.assert_allclose(a[key], b[key], rtol=1e-12, atol=1e-10)
        count = counts[scan["dataset"]]
        count["scans"] += 1
        count["exported_tracks"] += len(doc["tracks"])
        count["selected_pairs"] += len(mapping) // 2
        count["qualified_pairs"] += sum(v["fit"]["qualified"] for v in mapping.values()) // 2
        arm_rows = {}
        for arm in ("none", "symmetric", "rx0_anchor", "rx1_anchor"):
            corrected, receipts = correct_document(doc, scan, arm)
            assert len(corrected["tracks"]) == len(doc["tracks"])
            for original, new in zip(doc["tracks"], corrected["tracks"], strict=True):
                assert original["track_id"] == new["track_id"]
                assert len(original["measured_hz"]) == len(new["y"])
                if arm == "none":
                    np.testing.assert_array_equal(original["measured_hz"], new["y"])
            arm_rows[arm] = receipts
            changed = sum(r["corrected"] for r in receipts)
            count[arm + "_corrected_tracks"] += changed
            count[arm + "_corrected_scans"] += bool(changed)
        details.append(dict(dataset=scan["dataset"], session_id=scan["session_id"], arms=arm_rows))
    result = dict(
        audit_passed=True,
        population="all exported tracks; no geographic fit",
        counts=counts,
        scans=details,
    )
    with (HERE / "coverage.json").open("x") as f:
        json.dump(result, f, indent=2, allow_nan=False)
    # Bind every read scientific artifact and implementation; no mutable self hash.
    for p in HERE.iterdir():
        if p.is_file():
            bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    with (HERE / "coverage-seal.json").open("x") as f:
        json.dump({"sha256": bindings}, f, indent=2)
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
