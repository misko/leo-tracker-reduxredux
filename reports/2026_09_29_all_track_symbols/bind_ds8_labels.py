"""Bind saved conditional DS8 associations by exact session/track identity."""

import hashlib
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).parent
SOURCE = BASE.parent / "2026_09_28_ds7_ds8_correspondence/local"


def check_binding(label, track):
    checks = dict(
        dataset=track["dataset"] == "DS8",
        session=label["session_id"] == track["session"],
        track=label["track_id"] == track["track_id"],
        receiver=label["receiver_id"] == track["receiver"],
        channel=label["probe"]["channel"] == track["channel"],
        edge=label["probe"]["edge"] == track["edge"],
        start=abs(label["start_utc_ns"] - track["start_utc_ns"]) <= 1000,
        end=abs(label["end_utc_ns"] - track["end_utc_ns"]) <= 1000,
    )
    return checks


def main():
    census = BASE / "local/clustering.json"
    tracks = json.loads(census.read_text())["tracks"]
    lookup = {(t["session"], t["track_id"]): t for t in tracks}
    assert len(lookup) == len(tracks)
    bound, rejected, hashes = [], [], {str(census): hashlib.sha256(census.read_bytes()).hexdigest()}
    seen = set()
    for path in sorted(SOURCE.glob("*-tracks.json")):
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        for label in json.loads(path.read_text()):
            if label["status"] != "conditional_doppler_label":
                continue
            key = (label["session_id"], label["track_id"])
            assert key not in seen
            seen.add(key)
            track = lookup.get(key)
            if track is None:
                rejected.append(dict(source=str(path), label=label, reason="no_exact_track"))
                continue
            checks = check_binding(label, track)
            if not all(checks.values()):
                rejected.append(dict(source=str(path), label=label, checks=checks))
                continue
            bound.append(
                dict(
                    id=track["id"],
                    dataset=track["dataset"],
                    session=track["session"],
                    track_id=track["track_id"],
                    norad_id=label["norad_id"],
                    satellite_name=label["candidate_name"],
                    identity_status=label["status"],
                    decode_status=track["status"],
                    source=str(path),
                    checks=checks,
                    original_label=label,
                )
            )
    qualified = [t for t in tracks if t["status"] == "qualified" and t["norad_id"] is not None]
    qualified += [
        dict(
            lookup[(r["session"], r["track_id"])],
            norad_id=r["norad_id"],
            satellite_name=r["satellite_name"],
            identity_status=r["identity_status"],
        )
        for r in bound
        if r["decode_status"] == "qualified"
    ]
    repeats = [
        dict(left=a["id"], right=b["id"], norad_id=a["norad_id"])
        for i, a in enumerate(qualified)
        for b in qualified[i + 1 :]
        if a["norad_id"] == b["norad_id"] and a["session"] != b["session"]
    ]
    result = dict(
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        input_sha256=hashes,
        bound=bound,
        rejected=rejected,
        bound_decode_status=dict(Counter(r["decode_status"] for r in bound)),
        combined_qualified_labels=len(qualified),
        cross_session_repeat_pairs=repeats,
    )
    out = BASE / "local/bound-ds8-labels"
    out.mkdir(exist_ok=True)
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"input_sha256", "bound"}}, indent=2
        )
    )


if __name__ == "__main__":
    main()
