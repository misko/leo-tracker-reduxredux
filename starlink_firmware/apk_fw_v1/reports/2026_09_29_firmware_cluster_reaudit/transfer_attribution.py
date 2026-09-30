"""Frozen upper-eight-group attribution, without selecting a new classifier."""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from frame_transfer import normalize
from scipy.spatial.distance import cdist

BASE = Path(__file__).resolve().parent
SOURCE = (BASE.parents[3] / "reports") / "2026_09_29_identity_resumption/local/rows.json"


def expected_match(labels, predicted, strata):
    expected = np.empty(len(labels))
    for group in strata:
        for i in group:
            expected[i] = np.mean(predicted[group] == labels[i])
    return expected


def macro_excess(labels, difference, keep, classes=8):
    if any(not np.any(keep & (labels == c)) for c in range(classes)):
        return None
    return float(np.mean([difference[keep & (labels == c)].mean() for c in range(classes)]))


def main():
    receipt = BASE / "local/frame-transfer.json"
    original = json.loads(receipt.read_text())
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == original["source_sha256"]
    frozen = next(r for r in original["experiments"] if r["edge"] == "upper" and r["groups"] == 8)
    rows = [r for r in json.loads(SOURCE.read_text()) if r["edge"] == "upper"]
    membership = {name: int(c) for c, names in frozen["cluster_members"].items() for name in names}
    assert set(membership) == {r["id"] for r in rows}
    labels = np.array([membership[r["id"]] for r in rows])
    arrays = []
    for r in rows:
        path = Path(r["source_artifact"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == r["source_artifact_sha256"]
        with np.load(path) as d:
            meta = json.loads(str(d["metadata"]))
            bins = np.array([486, 487, 496, 497])
            ix = np.searchsorted(d["bins"], bins)
            assert np.array_equal(d["bins"][ix], bins)
            arrays.append(normalize(d["z"][meta["evaluation_frames"], :6][:, :, ix]))
    arrays = np.array(arrays)
    centers = np.array([arrays[labels == c, 0].mean(axis=0) for c in range(8)])
    predicted = cdist(arrays[:, 1], centers).argmin(axis=1)
    recall = [(predicted[labels == c] == c).mean() for c in range(8)]
    np.testing.assert_allclose(recall, frozen["held_recall_by_group"])
    strata = defaultdict(list)
    for i, r in enumerate(rows):
        strata[r["session"], r["channel"], r["rate"], r["receiver"]].append(i)
    expected = expected_match(labels, predicted, list(strata.values()))
    difference = (predicted == labels).astype(float) - expected
    weights = np.array([1 / (8 * np.sum(labels == c)) for c in labels])
    contributions = difference * weights
    groups = []
    for c in range(8):
        ix = np.flatnonzero(labels == c)
        groups.append(dict(group=c, n=len(ix), held_recall=float(recall[c]),
            conditional_expected_recall=float(expected[ix].mean()),
            contribution=float(contributions[ix].sum()),
            dataset_counts=dict(Counter(rows[i]["dataset"] for i in ix)),
            receiver_counts=dict(Counter(str(rows[i]["receiver"]) for i in ix)),
            channel_counts=dict(Counter(str(rows[i]["channel"]) for i in ix)),
            rate_counts=dict(Counter(str(rows[i]["rate"]) for i in ix)),
            pilot_median=float(np.median([rows[i]["pilot"] for i in ix])),
            cfo_median_hz=float(np.median([rows[i]["cfo_hz"] for i in ix])),
            candidate_counts=dict(Counter(str(rows[i]["norad_id"]) for i in ix))))
    sessions = []
    for session in sorted({r["session"] for r in rows}):
        mask = np.array([r["session"] == session for r in rows])
        sessions.append(dict(session=session, entries=int(mask.sum()),
            contribution=float(contributions[mask].sum()),
            leave_session_out_excess=macro_excess(labels, difference, ~mask)))
    sessions.sort(key=lambda r: -r["contribution"])
    result = dict(groups=groups, sessions=sessions,
        observations=[dict(id=r["id"], group=int(labels[i]), predicted=int(predicted[i]),
                           conditional_match=float(expected[i]),
                           contribution=float(contributions[i]))
                      for i, r in enumerate(rows)],
        held_balanced_accuracy=float(np.mean(recall)),
        exact_conditional_baseline=float(np.mean([expected[labels == c].mean() for c in range(8)])),
        total_excess=float(contributions.sum()),
        source_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitation="Post-selection attribution of an exploratory lead, "
        "not a new significance test. "
        "No clusters or centroids refit. Session omission recomputes macro weights; abstains if "
        "a class disappears. Metadata summaries are descriptive, not field mappings.")
    (BASE / "local/transfer-attribution.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Held, conditional baseline, excess", result["held_balanced_accuracy"],
          result["exact_conditional_baseline"], result["total_excess"])
    for r in groups:
        print("Group", r["group"], "n", r["n"], "contribution", r["contribution"])
    print("Leading sessions", sessions[:3])
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 3.5), layout="constrained")
    ax.bar(range(8), [100 * r["contribution"] for r in groups],
           color=["tab:orange" if r["group"] == 7 else "tab:blue" for r in groups])
    ax.set(xticks=range(8), xlabel="Discovery group",
           ylabel="Contribution to excess accuracy (percentage points)",
           title="Upper-edge transfer: a small group dominates the excess")
    fig.savefig(BASE / "local/transfer-attribution.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
