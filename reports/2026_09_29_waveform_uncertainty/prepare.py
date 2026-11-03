import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OLD = HERE.parent / "2026_09_29_training_waveform"
RECENT = HERE.parent / "2026_09_29_waveform_trajectory"


def select_visits(track):
    train = []
    times = track["times_s"]
    for i in sorted(range(len(times)), key=times.__getitem__):
        if track["training_mask"][i] and (not train or times[i] >= times[train[-1]] + 1):
            train.append(i)
        if len(train) == 4:
            break
    if len(train) < 4:
        return None
    held = sorted(
        (
            i
            for i, flag in enumerate(track["training_mask"])
            if not flag and times[i] > times[train[-1]]
        ),
        key=times.__getitem__,
    )[:2]
    return (train, held) if held else None


def main():
    old = json.loads((OLD / "plan.json").read_text())
    inventory = json.loads((RECENT / "inventory.json").read_text())
    for doc in (old, inventory):
        for path, digest in doc["hashes"].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    previous = {
        (r["session_id"], r["track_id"], r["observation_index"]): r for r in inventory["rows"]
    }
    selections, unsupported = [], []
    for original in old["selections"]:
        selected = select_visits(original["track"])
        if selected is None:
            unsupported.append(
                dict(panel_id=original["unit_id"], receiver_id=original["receiver_id"])
            )
            continue
        train, held = selected
        for role, i in [(f"T{n}", i) for n, i in enumerate(train)] + [
            (f"H{n}", i) for n, i in enumerate(held)
        ]:
            row = dict(original)
            row.update(
                panel_id=original["unit_id"],
                unit_id=original["unit_id"] + "_" + role,
                role=role,
                observation_index=i,
                visit=original["track"]["visits"][i],
                time_s=original["track"]["times_s"][i],
            )
            key = row["session_id"], row["track"]["track_id"], i
            if key in previous:
                row["reuse"] = previous[key]
            selections.append(row)
    hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (
            OLD / "plan.json",
            RECENT / "inventory.json",
            HERE / "PROTOCOL.md",
            HERE / "prepare.py",
        )
    }
    (HERE / "plan.json").write_text(
        json.dumps(dict(hashes=hashes, selections=selections, unsupported=unsupported), indent=2)
        + "\n"
    )
    print(
        json.dumps(
            dict(
                selections=len(selections),
                reuse=sum("reuse" in r for r in selections),
                unsupported=unsupported,
            )
        )
    )


if __name__ == "__main__":
    main()
