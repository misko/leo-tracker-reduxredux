"""Freeze both receiver arms for every existing consecutive panel."""

import hashlib
import json
from pathlib import Path

from receiver_filter import receiver_documents

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_09_29_consecutive_panels"
bindings = json.loads((PREVIOUS / "evidence-sha256.json").read_text())
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
prior = json.loads((PREVIOUS / "plan.json").read_text())
groups, units, membership = [], [], {}
for original, oldunit in zip(
    prior["models"][0]["groups"], prior["models"][0]["units"], strict=True
):
    panel = original["dataset_id"]
    documents = []
    for item in original["inputs"]:
        path = next(Path(a["path"]) for a in item["artifacts"] if a["kind"] == "observations")
        documents.append(json.loads(path.read_text()))
    frozen_rows = json.loads((PREVIOUS / "t0" / panel / "source_held/result.json").read_text())[
        "rows"
    ]
    eligible = {(r["session_id"], r["track_id"]) for r in frozen_rows}
    documents = [
        {**d, "tracks": [t for t in d["tracks"] if (d["session_id"], t["track_id"]) in eligible]}
        for d in documents
    ]
    assert sum(len(d["tracks"]) for d in documents) == len(eligible)
    for receiver in ("0", "1"):
        selected = receiver_documents(documents, receiver)
        key = f"{panel}_rx{receiver}"
        tracks = [t for d in selected for t in d["tracks"]]
        train = sum(sum(t["training_mask"]) for t in tracks)
        held = sum(len(t["training_mask"]) - sum(t["training_mask"]) for t in tracks)
        groups.append(
            {
                **original,
                "dataset_id": key,
                "panel_id": panel,
                "receiver_id": receiver,
                "tracks": len(tracks),
                "training_observations": train,
                "held_observations": held,
                "receiver_partition": [
                    {
                        "session_id": d["session_id"],
                        "track_ids": [t["track_id"] for t in d["tracks"]],
                    }
                    for d in selected
                ],
            }
        )
        units.append({**oldunit, "unit_id": key, "source_datasets": [key]})
        membership[key] = prior["membership"][panel]
assert len(groups) == 36
for group in groups:
    group["original_panel_excluded_tracks"] = group.pop("excluded_tracks")
for path in (
    PREVIOUS / "evidence-sha256.json",
    HERE / "prepare.py",
    HERE / "PROTOCOL.md",
    HERE / "receiver_filter.py",
    HERE / "test_receiver_filter.py",
    HERE / "tests.log",
):
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
with (HERE / "plan.json").open("x") as stream:
    json.dump(
        {
            "config": prior["config"],
            "membership": membership,
            "models": [{"decay_s": 0, "groups": groups, "units": units}],
        },
        stream,
        indent=2,
    )
with (HERE / "input-seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
print("Frozen 36 receiver arms with", len(bindings), "bindings")
