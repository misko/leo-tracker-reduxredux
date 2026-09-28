"""Audit exported identities and paired-window partition overlap; no fitting."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / "2026_09_27_roof_direction_subset"


def main():
    frequency = json.loads((ROOT / "held-frequency.json").read_text())
    links = json.loads((OLD / "source_links.json").read_text())
    model_rows = json.loads((OLD / "model_rows.json").read_text())
    by_candidate = {}
    status = Counter()
    rates = Counter()
    with (ROOT / "opportunities/opportunities.jsonl").open() as handle:
        for line in handle:
            row = json.loads(line)
            status[row["opportunity_status"]] += 1
            rates[row["source_window"]["sample_rate_hz"]] += 1
            for view in row["receivers"].values():
                for candidate in view["candidates"]:
                    projected = candidate.get("projected_candidate_id")
                    if projected is None:
                        continue
                    assert projected not in by_candidate, "duplicate projected source candidate"
                    by_candidate[projected] = (row["source_window_id"], candidate)

    held_keys = set()
    held_windows = []
    for row in frequency["rows"]:
        key = (row["session_id"], row["track_id"], row["observation_id"])
        assert key not in held_keys
        held_keys.add(key)
        window, candidate = by_candidate[row["source_candidate_id"]]
        assert candidate["session_id"] == row["session_id"]
        assert candidate["passed_fractional_margin_gate"]
        for field in (
            "source_group_id", "source_sample_start", "source_sample_end",
            "support_center_utc_ns",
        ):
            assert candidate["source_interval"][field] == row[field], field
        # The public projected-candidate contract supplies receiver_id rather
        # than graph stream_id. Bind the graph's documented receiver label.
        assert row["stream_id"] == f"rx-{candidate['receiver_id']}"
        assert candidate["source_interval"]["stream_id"] in (None, row["stream_id"])
        held_windows.append(window)
    expected = {(r["session_id"], r["track_id"], r["observation_id"]) for r in model_rows}
    assert held_keys == expected, "held frequency keys do not equal reception model keys"

    window_masks = defaultdict(set)
    unresolved = Counter()
    observation_counts = Counter()
    for sid, accounting in frequency["accounting"].items():
        source = {
            (r["track_id"], r["observation_id"]): r["candidate_ids"]
            for r in links[sid]["rows"]
        }
        for track in accounting["track_masks"]:
            for observation in track["observation_sources"]:
                role = "training" if observation["training"] else "held"
                observation_counts[role] += 1
                ids = source.get((track["track_id"], observation["observation_id"]), [])
                if len(ids) != 1 or ids[0] not in by_candidate:
                    unresolved[role] += 1
                    continue
                window_masks[by_candidate[ids[0]][0]].add(role)
    mixed = {window for window, roles in window_masks.items() if len(roles) > 1}
    with (ROOT / "held-window-eligibility.jsonl").open("w") as handle:
        for row, window in zip(frequency["rows"], held_windows, strict=True):
            handle.write(json.dumps({
                "session_id": row["session_id"],
                "track_id": row["track_id"],
                "observation_id": row["observation_id"],
                "source_window_id": window,
                "shares_paired_window_with_original_frequency_training": window in mixed,
                "scope": "overlap diagnostic only; not a new validation split",
            }) + "\n")
    result = {
        "held_frequency_rows": len(held_keys),
        "held_rows_joined_to_opportunities": len(held_windows),
        "held_keys_exactly_equal_existing_reception_keys": True,
        "projected_source_candidates": len(by_candidate),
        "opportunity_status_counts": dict(status),
        "opportunities_by_sample_rate_hz": dict(rates),
        "original_frequency_observation_counts": dict(observation_counts),
        "unresolved_source_links_by_partition": dict(unresolved),
        "paired_windows_with_both_training_and_held_observations": len(mixed),
        "held_rows_in_mixed_paired_windows": sum(w in mixed for w in held_windows),
        "held_rows_clear_of_original_training_paired_windows": sum(
            w not in mixed for w in held_windows
        ),
        "interpretation": (
            "Paired-window overlap is a conservative leakage warning, not proof of identical "
            "target or signal support. Existing per-observation masks must not be advertised "
            "as independent paired-window validation. No new reception model was scored."
        ),
        "source_hashes": {
            str(path.relative_to(ROOT.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                ROOT / "held-frequency.json",
                ROOT / "opportunities/opportunities.jsonl",
                OLD / "source_links.json",
                OLD / "model_rows.json",
            )
        },
    }
    (ROOT / "join-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "source_hashes"}, indent=2))


if __name__ == "__main__":
    main()
