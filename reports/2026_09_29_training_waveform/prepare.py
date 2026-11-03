"""Select early training observations without consulting pilot or held scores."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def select_track(tracks, rx):
    options = []
    for t in tracks:
        if t["receiver_id"] != rx:
            continue
        indices = [i for i, m in enumerate(t["training_mask"]) if m]
        if len(indices) < 2 or len(indices) == len(t["training_mask"]):
            continue
        first = min(indices, key=lambda i: (t["times_s"][i], i))
        options.append((t["times_s"][first], t["track_id"], first, t))
    if not options:
        return None
    _, _, i, t = min(options, key=lambda v: v[:3])
    return dict(track=t, observation_index=i, visit=t["visits"][i])


def main():
    source = HERE.parent / "2026_09_29_donor_residual_transfer/plan.json"
    plan = json.loads(source.read_text())
    selections = []
    hashes = {}
    for u in plan["units"]:
        if u["role"] != "target":
            continue
        for entry in u["group"]["inputs"]:
            a = next(a for a in entry["artifacts"] if a["kind"] == "observations")
            p = Path(a["path"])
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            assert "sha256:" + h == a["sha256"]
            hashes[str(p.relative_to(ROOT))] = h
            obs = json.loads(p.read_text())
            if obs["sample_rate_hz"] < 5e6:
                continue
            for rx in (0, 1):
                chosen = select_track(obs["tracks"], rx)
                assert chosen is not None
                selections.append(
                    dict(
                        unit_id=u["unit_id"],
                        session_id=entry["session_id"],
                        manifest_sha256=entry["manifest_sha256"],
                        start_utc_ns=obs["start_utc_ns"],
                        sample_rate_hz=obs["sample_rate_hz"],
                        receiver_id=rx,
                        **chosen,
                    )
                )
            break
    assert len(selections) == 18
    for p in (source, HERE / "prepare.py", HERE / "PROTOCOL.md"):
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    (HERE / "plan.json").write_text(
        json.dumps(dict(hashes=hashes, selections=selections), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
