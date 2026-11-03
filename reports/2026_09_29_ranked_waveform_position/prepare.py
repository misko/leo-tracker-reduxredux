import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def main():
    queue_path = HERE.parent / "2026_09_29_observation_influence/queue.json"
    source_path = HERE.parent / "2026_09_29_donor_residual_transfer/plan.json"
    queue, source = [json.loads(p.read_text()) for p in (queue_path, source_path)]
    for p, h in queue["hashes"].items():
        assert hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h
    units = {u["unit_id"]: u for u in source["units"]}
    selections = []
    hashes = {}
    for row in queue["rows"]:
        entry = next(
            e
            for e in units[row["panel"]]["group"]["inputs"]
            if e["session_id"] == row["session_id"]
        )
        artifact = next(a for a in entry["artifacts"] if a["kind"] == "observations")
        p = Path(artifact["path"])
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        assert "sha256:" + digest == artifact["sha256"]
        hashes[str(p.relative_to(ROOT))] = digest
        doc = json.loads(p.read_text())
        track = next(t for t in doc["tracks"] if t["track_id"] == row["track_id"])
        i = row["index"]
        assert track["visits"][i] == row["visit"] and track["times_s"][i] == row["time_s"]
        assert track["training_mask"][i] and doc["sample_rate_hz"] == row["sample_rate_hz"]
        selections.append(
            dict(
                panel_id=row["panel"],
                unit_id=f"{row['panel']}_rank{row['rank']:02d}",
                role="T",
                receiver_id=row["receiver_id"],
                session_id=row["session_id"],
                manifest_sha256=entry["manifest_sha256"],
                start_utc_ns=doc["start_utc_ns"],
                sample_rate_hz=doc["sample_rate_hz"],
                track=track,
                observation_index=i,
                visit=row["visit"],
                time_s=row["time_s"],
                ranking=row,
            )
        )
    assert len(selections) == 72
    for p in (queue_path, source_path, HERE / "prepare.py", HERE / "PROTOCOL.md"):
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    (HERE / "plan.json").write_text(
        json.dumps(dict(hashes=hashes, selections=selections), indent=2) + "\n"
    )
    print(len(selections), "frozen selections")


if __name__ == "__main__":
    main()
