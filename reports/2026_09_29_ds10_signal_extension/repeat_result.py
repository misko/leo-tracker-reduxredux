"""Audit the preselected longer-excerpt cross-session comparison."""

import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from extend import OUT, PRIOR, sha, write  # noqa: E402

sys.path.insert(0, str(PRIOR))
from cluster_tracks import mean_phase, normalized_phase_features  # noqa: E402


def main():
    plan = json.loads((OUT / "extended-repeat/plan.json").read_text())
    census = {c["unit"]: c for c in json.loads((OUT / "census.json").read_text())["captures"]}
    rows, first_two, all_frames = [], [], []
    for item in plan["candidates"]:
        unit = item["unit"]
        p = OUT / "extended-repeat/decoded" / unit / "results.json"
        r = json.loads(p.read_text())["rows"][0]
        old_path = OUT / "decoded" / unit / "results.json"
        old = json.loads(old_path.read_text())["rows"][item["original_index"]]
        assert r["track_id"] == old["track_id"] == item["track_id"]
        assert r["excerpt_sha256"] == old["excerpt_sha256"]
        assert r["visit"] == old["visit"]
        c = census[unit]
        track = c["tracks"][item["original_index"]]
        seconds = next(t for v, t in zip(track["visits"], track["times_s"], strict=True)
                       if v == r["visit"])
        with np.load(r["artifact"]) as data:
            q = r["qualified_frames"]
            assert len(q) >= 2
            z = data["z"][:, :6, np.searchsorted(data["bins"], [486, 487, 496, 497])]
            first_two.append(mean_phase(z[q[:2]]))
            all_frames.append(mean_phase(z[q]))
        rows.append(dict(
            unit=unit, original_index=item["original_index"], visit=r["visit"],
            selected_utc_ns=c["start_utc_ns"] + round(seconds * 1e9),
            qualified_frames=q, accepted_words=sum(w["accepted"] for w in r["words"]),
            source_sha256=sha(p), original_source_sha256=sha(old_path),
            same_raw_excerpt=True,
        ))
    a, b = normalized_phase_features(first_two)
    x, y = normalized_phase_features(all_frames)
    result = dict(
        norad_id=plan["norad_id"], entries=rows,
        separation_s=abs(rows[0]["selected_utc_ns"] - rows[1]["selected_utc_ns"]) / 1e9,
        first_two_qualified_frame_correlation=float(a @ b),
        all_qualified_frame_correlation=float(x @ y),
        method_sha256=sha(Path(__file__)),
        limitation="Conditional orbit labels, not verified identity. Additional evaluation "
        "frames and a changed calibration split provide more opportunities to pass the "
        "unchanged .5 pilot gate. One selected matched pair, not a population claim. "
        "No tail word passed either side. No post-hoc sign/phase alignment.",
    )
    write(OUT / "extended-repeat/comparison.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
