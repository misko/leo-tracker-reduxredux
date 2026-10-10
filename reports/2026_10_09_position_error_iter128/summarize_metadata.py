"""Summarize metadata authorities and template bytes; never opens IQ."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    authority = ROOT / "reports/2026_10_09_position_error_iter110/protocol.json"
    plan = json.loads(authority.read_text())
    members = []
    for b in plan["members"]:
        label = b["member"]["inventory_label"]
        path = HERE / ("metadata-v3" if label == "DS16-020" else "metadata-v2") / f"{label}.json"
        d = json.loads(path.read_text())
        assert d["status"] == "complete" and d["session_id"] == b["member"]["session_id"]
        assert d["expected_observations"] == len(d["windows"]) == len(d["window_ids"])
        assert [w["window_id"] for w in d["windows"]] == d["window_ids"]
        assert len(set(d["window_ids"])) == len(d["window_ids"])
        ready = [w for w in d["windows"] if w["status"] == "metadata-ready"]
        members.append(
            {
                "label": label,
                "session_id": d["session_id"],
                "sample_rate_hz": d["sample_rate_hz"],
                "metadata_path": str(path.relative_to(ROOT)),
                "metadata_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "input_manifest_sha256": d["input_manifest_sha256"],
                "analysis_manifest_sha256": d["analysis_manifest_sha256"],
                "evidence_sha256": d["evidence_sha256"],
                "expected_observations": len(d["windows"]),
                "metadata_ready": len(ready),
                "receiver_counts": dict(Counter(w["receiver"] for w in ready)),
                "analyzer_id": d["analysis_binding"]["configuration"]["analyzer_id"],
                "maximum_visit_bytes": max(v["sample_count"] for v in d["visits"].values())
                * len(d["receiver_ids"])
                * 4,
                "epoch_outside_first_frame": sum(
                    w["epoch_sample"] >= round(d["sample_rate_hz"] / 750) for w in ready
                ),
                "acquired_cfo_outside_research_native_400khz": sum(
                    abs(w["acquired_cfo_hz"]) > 400000 for w in ready
                ),
            }
        )
    templates = {}
    for rate in (2_500_000, 10_000_000):
        for edge in ("lower", "upper"):
            for roll in (0, 17):
                a = np.asarray(qin_edge_pilot_frame(rate, edge, symbol_roll=roll), dtype="<c16")
                templates[f"{rate}:{edge}:roll{roll}"] = {
                    "sha256": hashlib.sha256(a.tobytes()).hexdigest(),
                    "count": len(a),
                    "dtype": "little-endian complex128 promoted template",
                }
    output = {
        "status": "metadata-complete",
        "authority_path": str(authority.relative_to(ROOT)),
        "authority_sha256": hashlib.sha256(authority.read_bytes()).hexdigest(),
        "members": members,
        "total_observations": sum(m["expected_observations"] for m in members),
        "metadata_ready": sum(m["metadata_ready"] for m in members),
        "current_templates": templates,
        "iq_reads": 0,
        "scope": "Metadata identity only; original numerical parity pending",
    }
    with (HERE / "inventory.json").open("x") as stream:
        json.dump(output, stream, indent=2)
    print(
        json.dumps(
            {k: v for k, v in output.items() if k not in ["members", "current_templates"]}, indent=2
        )
    )
    for m in members:
        print(
            m["label"],
            m["sample_rate_hz"],
            m["expected_observations"],
            m["receiver_counts"],
            m["maximum_visit_bytes"],
        )


if __name__ == "__main__":
    main()
