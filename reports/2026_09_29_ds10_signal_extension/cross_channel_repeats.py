"""Explicit cross-channel repeat hypotheses; never equate opposite-edge carrier bits."""

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from extend import OUT, sha, write  # noqa: E402


def main():
    rows = json.loads((OUT / "qualified-tracks.json").read_text())
    with np.load(OUT / "qualified-features.npz") as data:
        features = data["region0"]
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        if r["norad_id"] is not None:
            groups[r["norad_id"]].append(i)
    pairs = []
    for norad, indices in groups.items():
        for ai, i in enumerate(indices):
            for j in indices[ai + 1:]:
                a, b = rows[i], rows[j]
                if a["session"] == b["session"] or not any(
                        r["dataset"] == "DS10" for r in (a, b)):
                    continue
                pair = dict(
                    norad_id=norad, satellite_name=a["satellite_name"] or b["satellite_name"],
                    left=a, right=b,
                    separation_hours=abs(a["selected_utc_ns"] - b["selected_utc_ns"]) / 3.6e12,
                    status="opposite_edges_no_common_early_carriers",
                )
                if a["edge"] != b["edge"]:
                    pairs.append(pair)
                    continue
                score = float(features[i] @ features[j])
                controls = []
                for anchor_index, target in [(i, b), (j, a)]:
                    anchor = rows[anchor_index]
                    for k, candidate in enumerate(rows):
                        if (candidate["norad_id"] is None or candidate["norad_id"] == norad
                                or candidate["session"] == anchor["session"]):
                            continue
                        if any(candidate[key] != target[key]
                               for key in ["channel", "edge", "rate", "receiver"]):
                            continue
                        delta = abs(anchor["selected_utc_ns"] - candidate["selected_utc_ns"])
                        if delta < 7200e9:
                            continue
                        controls.append(dict(
                            anchor=anchor["id"], other=candidate["id"],
                            norad_id=candidate["norad_id"],
                            correlation=float(features[anchor_index] @ features[k]),
                        ))
                values = np.array([c["correlation"] for c in controls])
                pair.update(
                    status="cross_channel_comparison", correlation=score,
                    control_n=len(controls), controls=controls,
                    control_percentile=float(np.mean(values < score)) if len(values) else None,
                    control_quantiles=np.quantile(values, [.05, .5, .95]).tolist()
                    if len(values) else None,
                )
                pairs.append(pair)
    write(OUT / "cross-channel-repeats.json", dict(
        pairs=pairs, source_sha256=sha(OUT / "qualified-tracks.json"),
        features_sha256=sha(OUT / "qualified-features.npz"),
        method_sha256=sha(Path(__file__)),
        limitation="Same relative carrier coordinates on different RF channels; tests a "
        "channel-invariant profile hypothesis, not identical transmitted resource elements. "
        "Controls share an endpoint and match the other endpoint's channel, edge, rate, RX "
        "and >2h separation. Conditional identities; dependent pairs; no significance claim.",
    ))
    for p in pairs:
        print(p["norad_id"], p["left"]["id"], p["right"]["id"], p["status"],
              p.get("correlation"), p.get("control_n"), p.get("control_percentile"), flush=True)


if __name__ == "__main__":
    main()
