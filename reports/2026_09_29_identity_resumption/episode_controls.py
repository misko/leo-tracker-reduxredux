"""Endpoint/session-matched sign contrasts and candidate retrieval against metadata."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from corpus_identity import separation_bin

BASE = Path(__file__).resolve().parent
OUT = BASE / "local"
SCOPES = ("same_session_channel", "different_session_channel", "different_session_other_channel")


def shared_state(a, b):
    x, y = set(a["known_tail_states"]), set(b["known_tail_states"])
    return int(bool(x & y)) if x and y else -1


def credit(scores, truth):
    """Fractional top-1 credit for exact score ties; no label-based tie break."""
    best = np.isclose(scores, max(scores), atol=1e-12, rtol=0)
    return float(np.asarray(truth)[best].mean())


def main():
    seal = json.loads((OUT / "seal.json").read_text())["files"]
    for name in ("rows.json", "features.npz", "identity.json"):
        assert hashlib.sha256((OUT / name).read_bytes()).hexdigest() == seal[f"local/{name}"]
    rows = json.loads((OUT / "rows.json").read_text())
    identity = json.loads((OUT / "identity.json").read_text())
    ids = {r["id"]: i for i, r in enumerate(rows)}
    with np.load(OUT / "features.npz") as d:
        signs = d["real_sign"]
    # Query uses second frame, every gallery item uses its first frame.
    scores = signs[:, 1] @ signs[:, 0].T
    labeled = [i for i, r in enumerate(rows) if r["norad_id"] is not None]
    original = next(e for e in identity["experiments"]
                    if e["scope"] == "same_channel_pairs" and e["tier"] == "all")
    contrasts = []
    for p in original["matched_pairs"]:
        for left, right in [(p["left"], p["right"]), (p["right"], p["left"])]:
            i, j = ids[left], ids[right]
            a, b = rows[i], rows[j]
            target_dt = abs(a["selected_utc_ns"] - b["selected_utc_ns"]) / 1e9
            controls = []
            for k in labeled:
                c = rows[k]
                if c["norad_id"] == a["norad_id"]:
                    continue
                if any(c[v] != b[v] for v in ("session", "edge", "channel", "rate", "receiver")):
                    continue
                if c["session"] == a["session"] and c["visit"] == a["visit"]:
                    continue
                dt = abs(a["selected_utc_ns"] - c["selected_utc_ns"]) / 1e9
                if separation_bin(dt) != separation_bin(target_dt):
                    continue
                if shared_state(a, c) != shared_state(a, b) or abs(c["pilot"] - b["pilot"]) > .1:
                    continue
                controls.append(k)
            contrasts.append(dict(query=left, positive=right, separation_s=target_dt,
                                  controls=[rows[k]["id"] for k in controls],
                                  positive_score=float(scores[i, j]),
                                  control_mean=float(scores[i, controls].mean())
                                  if controls else None,
                                  excess=float(scores[i, j] - scores[i, controls].mean())
                                  if controls else None))
    cases = []
    for i in labeled:
        a = rows[i]
        for scope in SCOPES:
            groups = defaultdict(list)
            for j in labeled:
                b = rows[j]
                if a["edge"] != b["edge"] or abs(a["pilot"] - b["pilot"]) > .1:
                    continue
                if a["session"] == b["session"] and a["visit"] == b["visit"]:
                    continue
                same_session = a["session"] == b["session"]
                same_channel = a["channel"] == b["channel"]
                wanted = {"same_session_channel": same_session and same_channel,
                          "different_session_channel": not same_session and same_channel,
                          "different_session_other_channel": not same_session and not same_channel}
                wanted = wanted[scope]
                if wanted:
                    groups[b["channel"], b["rate"], b["receiver"]].append(j)
            for key, gallery in groups.items():
                # Equal candidate opportunity: one observation per ID chosen by pilot only.
                representatives = {}
                for j in gallery:
                    candidate = rows[j]["norad_id"]
                    old = representatives.get(candidate)
                    if old is None or rows[j]["pilot"] > rows[old]["pilot"]:
                        representatives[candidate] = j
                gallery = list(representatives.values())
                if a["norad_id"] not in representatives or len(gallery) < 3:
                    continue
                truth = [rows[j]["norad_id"] == a["norad_id"] for j in gallery]
                sign_scores = scores[i, gallery]
                time_scores = -np.array([abs(a["selected_utc_ns"] - rows[j]["selected_utc_ns"])
                                         / 1e9 for j in gallery])
                cfo_scores = -np.array([abs(a["cfo_hz"] - rows[j]["cfo_hz"]) for j in gallery])
                cases.append(dict(query=a["id"], session=a["session"], candidate=a["norad_id"],
                                  scope=scope, gallery_instrument=key,
                                  gallery=[rows[j]["id"] for j in gallery],
                                  sign_credit=credit(sign_scores, truth),
                                  nearest_time_credit=credit(time_scores, truth),
                                  nearest_cfo_credit=credit(cfo_scores, truth),
                                  uniform_chance=1 / len(gallery)))
    summaries = []
    for scope in SCOPES:
        selected = [r for r in cases if r["scope"] == scope]
        if not selected:
            summaries.append(dict(scope=scope, cases=0, abstention="No >=3-candidate gallery"))
            continue
        # Equal weight per query episode, not per gallery/receiver opportunity.
        blocks = defaultdict(list)
        for r in selected:
            blocks[r["session"], r["candidate"]].append(r)
        metrics = ["sign_credit", "nearest_time_credit", "nearest_cfo_credit", "uniform_chance"]
        values = np.array([[np.mean([r[k] for r in group]) for k in metrics]
                           for group in blocks.values()])
        rng = np.random.default_rng(311909)
        bootstrap = np.array([values[rng.integers(len(values), size=len(values))].mean(0)
                              for _ in range(999)])
        # CIs are descriptive clustered resampling, not a proof of identification.
        summaries.append(dict(scope=scope, cases=len(selected), episodes=len(blocks),
                              metrics=dict(zip(metrics, values.mean(0).tolist(), strict=True)),
                              sign_minus_time_ci=np.quantile(bootstrap[:, 0] - bootstrap[:, 1],
                                                             [.025, .975]).tolist(),
                              sign_minus_cfo_ci=np.quantile(bootstrap[:, 0] - bootstrap[:, 2],
                                                            [.025, .975]).tolist()))
    inputs = [OUT / name for name in ("rows.json", "features.npz", "identity.json")]
    result = dict(endpoint_contrasts=contrasts, retrieval=cases, summaries=summaries,
                  input_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in inputs},
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitations="Exploratory follow-up to the selected real-sign lead. Conditional "
                  "candidate labels partly depend on Doppler, so CFO is a confound baseline, not "
                  "independent truth. Query frame1 vs gallery frame0; same-visit pairs excluded. "
                  "Static instrument normalization reused. Episode bootstrap is descriptive and "
                  "does not remove label errors, beam confounding or cross-session dependence.")
    (OUT / "episode-controls.json").write_text(json.dumps(result, indent=2) + "\n")
    supported = [r for r in contrasts if r["controls"]]
    print("endpoint comparisons", len(contrasts), "supported", len(supported),
          "with >=3 controls", sum(len(r["controls"]) >= 3 for r in contrasts))
    for r in summaries:
        print(json.dumps(r))


if __name__ == "__main__":
    main()
