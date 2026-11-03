import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OLD = HERE.parent / "2026_09_29_training_waveform"


def select_visits(track):
    times = track["times_s"]
    training = sorted(
        (i for i, flag in enumerate(track["training_mask"]) if flag), key=times.__getitem__
    )
    a = training[0]
    b = next((i for i in training if times[i] >= times[a] + 2), None)
    if b is None:
        return None
    held = sorted(
        (i for i, flag in enumerate(track["training_mask"]) if not flag and times[i] > times[b]),
        key=times.__getitem__,
    )
    return (a, b, held[0]) if held else None


def main():
    old = json.loads((OLD / "plan.json").read_text())
    inventory = json.loads((OLD / "inventory.json").read_text())
    for doc in (old, inventory):
        for path, digest in doc["hashes"].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    previous = {(r["unit_id"], r["receiver_id"]): r for r in inventory["rows"]}
    selections, unsupported, reuse = [], [], []
    for original in old["selections"]:
        indices = select_visits(original["track"])
        if indices is None:
            unsupported.append(
                dict(unit_id=original["unit_id"], receiver_id=original["receiver_id"])
            )
            continue
        for role, i in zip(("A", "B", "H"), indices, strict=True):
            row = dict(original)
            row.update(
                panel_id=original["unit_id"],
                unit_id=original["unit_id"] + "_" + role,
                role=role,
                observation_index=i,
                visit=original["track"]["visits"][i],
                time_s=original["track"]["times_s"][i],
            )
            selections.append(row)
            if role == "A":
                previous_row = previous[original["unit_id"], original["receiver_id"]]
                assert previous_row["visit"] == row["visit"]
                assert previous_row["track_id"] == row["track"]["track_id"]
                if previous_row["status"] == "ok":
                    assert (
                        hashlib.sha256((ROOT / previous_row["path"]).read_bytes()).hexdigest()
                        == previous_row["sha256"]
                    )
                # Actual RF is retrieved anew; preserve cached IQ as a hash-bound hint.
                row["reuse"] = previous_row
    hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (
            OLD / "plan.json",
            OLD / "inventory.json",
            HERE / "PROTOCOL.md",
            HERE / "prepare.py",
        )
    }
    (HERE / "plan.json").write_text(
        json.dumps(dict(hashes=hashes, selections=selections, unsupported=unsupported), indent=2)
        + "\n"
    )
    print(json.dumps(dict(selections=len(selections), unsupported=unsupported)))


if __name__ == "__main__":
    main()
