"""Metadata-only sparse event/ordinal audit; never opens a reader."""

import hashlib
import json
from pathlib import Path

from mapping import visit_ordinals

from leo.storage.adaptive_hop import AdaptiveHopIqStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.parent / "2026_10_09_position_error_iter128"


def main():
    plan = json.loads((OLD / "protocol.json").read_text())
    store = AdaptiveHopIqStore(Path(plan["data_root"]), read_only=True)
    members = []
    for member in plan["members"]:
        path = ROOT / member["metadata_path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != member["metadata_sha256"]:
            raise ValueError("metadata digest mismatch")
        metadata = json.loads(path.read_text())
        capture = store.inspect(member["session_id"])
        if capture.manifest_sha256 != member["input_manifest_sha256"]:
            raise ValueError("capture digest mismatch")
        visits = capture.manifest.receipt.visits
        mapping = visit_ordinals(visits, metadata)
        gaps = [
            {"ordinal": i, "event_id": v.event.visit_index}
            for i, v in enumerate(visits)
            if i != v.event.visit_index
        ]
        expected_failed_ids = [
            w["window_id"] for w in metadata["windows"] if mapping[w["visit"]] != w["visit"]
        ]
        old_rows = [
            json.loads(line)
            for line in (OLD / "results" / member["label"] / "rows.jsonl").read_text().splitlines()
        ]
        observed_failed_ids = [r["window_id"] for r in old_rows if r["status"] != "complete"]
        members.append(
            {
                "label": member["label"],
                "manifest_sha256": capture.manifest_sha256,
                "retained_visits": len(visits),
                "last_event_id": visits[-1].event.visit_index,
                "nonordinal_visits": len(gaps),
                "first_difference": gaps[0] if gaps else None,
                "selected_nonordinal_observations": len(expected_failed_ids),
                "observed_failures_exactly_predicted": set(expected_failed_ids)
                == set(observed_failed_ids),
                "selected_event_to_ordinal": mapping,
            }
        )
    with (HERE / "mapping-audit.json").open("x") as stream:
        json.dump(
            {"scope": "public manifest/selected metadata only", "iq_reads": 0, "members": members},
            stream,
            indent=2,
            sort_keys=True,
        )


if __name__ == "__main__":
    main()
