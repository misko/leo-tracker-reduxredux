"""Audit labeled cross-session repeats and compare frozen common-carrier profiles."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent


def main():
    source = BASE / "local/clustering.json"
    tracks = json.loads(source.read_text())["tracks"]
    labeled = [t for t in tracks if t["status"] == "qualified" and t["norad_id"] is not None]
    pairs = [
        (a, b)
        for i, a in enumerate(labeled)
        for b in labeled[i + 1 :]
        if a["session"] != b["session"] and a["norad_id"] == b["norad_id"]
    ]
    folder = BASE / "local/clusters/upper_early_profiles"
    labels = json.loads((folder / "labels.json").read_text())
    features = np.load(folder / "features.npy")
    index = {label: i for i, label in enumerate(labels)}
    results = []
    for a, b in pairs:
        if a["id"] not in index or b["id"] not in index:
            results.append(dict(left=a, right=b, status="outside_upper_feature_view"))
            continue
        score = float(features[index[a["id"]]] @ features[index[b["id"]]])
        rates = sorted([a["rate"], b["rate"]])
        controls = []
        for i, left in enumerate(labeled):
            for right in labeled[i + 1 :]:
                if (
                    left["edge"] != a["edge"]
                    or right["edge"] != a["edge"]
                    or left["channel"] != a["channel"]
                    or right["channel"] != a["channel"]
                    or sorted([left["rate"], right["rate"]]) != rates
                    or left["session"] == right["session"]
                    or left["norad_id"] == right["norad_id"]
                ):
                    continue
                controls.append(
                    dict(
                        left=left["id"],
                        right=right["id"],
                        correlation=float(
                            features[index[left["id"]]] @ features[index[right["id"]]]
                        ),
                    )
                )
        values = np.array([r["correlation"] for r in controls])
        by_id = {t["id"]: t for t in labeled}
        receiver_controls = [
            r["correlation"]
            for r in controls
            if sorted([by_id[r["left"]]["receiver"], by_id[r["right"]]["receiver"]])
            == sorted([a["receiver"], b["receiver"]])
        ]
        results.append(
            dict(
                left=a,
                right=b,
                status="compared",
                correlation=score,
                track_start_separation_s=abs(a["start_utc_ns"] - b["start_utc_ns"]) / 1e9,
                different_id_pairs=len(controls),
                control_quantiles=np.quantile(values, [0.05, 0.5, 0.95]).tolist()
                if len(values)
                else None,
                control_fraction_below_repeat=float(np.mean(values < score))
                if len(values)
                else None,
                controls=controls,
                receiver_matched_count=len(receiver_controls),
                receiver_matched_quantiles=np.quantile(
                    receiver_controls, [0.05, 0.5, 0.95]
                ).tolist()
                if receiver_controls
                else None,
                receiver_matched_fraction_below_repeat=float(
                    np.mean(np.array(receiver_controls) < score)
                )
                if receiver_controls
                else None,
            )
        )
    result = dict(
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [source, folder / "features.npy", folder / "labels.json"]
        },
        qualified_labeled_tracks=len(labeled),
        cross_session_repeat_pairs=len(pairs),
        same_rate_repeat_pairs=sum(a["rate"] == b["rate"] for a, b in pairs),
        results=results,
    )
    out = BASE / "local/satellite-repeat-audit"
    out.mkdir(exist_ok=True)
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                **result,
                "results": [{k: v for k, v in r.items() if k != "controls"} for r in results],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
