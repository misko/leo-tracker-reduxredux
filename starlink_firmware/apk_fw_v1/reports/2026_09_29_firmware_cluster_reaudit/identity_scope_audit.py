"""Revalidate matched-pair support and episode-weighted retrieval receipts."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
SOURCE = (BASE.parents[3] / "reports") / "2026_09_29_identity_resumption/local"


def episode_metrics(cases):
    blocks = defaultdict(list)
    for row in cases:
        blocks[row["session"], row["candidate"]].append(row)
    keys = ["sign_credit", "nearest_time_credit", "nearest_cfo_credit", "uniform_chance"]
    return len(blocks), {k: float(np.mean([np.mean([r[k] for r in block])
                                         for block in blocks.values()])) for k in keys}


def main():
    names = ["rows.json", "identity.json", "episode-controls.json", "stable-specificity.json"]
    inputs = {name: json.loads((SOURCE / name).read_text()) for name in names}
    metadata = {r["id"]: r for r in inputs["rows.json"]}
    support = []
    for experiment in inputs["identity.json"]["experiments"]:
        pairs = experiment.get("matched_pairs", [])
        for pair in pairs:
            a, b = [metadata[pair[key]] for key in ("left", "right")]
            assert a["norad_id"] == b["norad_id"] == pair["candidate"]
            assert (a["session"] != b["session"]) == pair["cross_session"]
        if "matched_same_pairs" in experiment:
            assert len(pairs) == experiment["matched_same_pairs"]
        support.append(dict(scope=experiment["scope"], tier=experiment["tier"],
                            matched_pairs=len(pairs),
                            cross_session_pairs=sum(p["cross_session"] for p in pairs),
                            unique_candidates=len({p["candidate"] for p in pairs}),
                            source_experiment=experiment,
                            assessment="Insufficient matched controls" if not pairs
                            else "No established identity after trajectory/session controls"))
    episode_results = []
    episode = inputs["episode-controls.json"]
    for summary in episode["summaries"]:
        cases = [r for r in episode["retrieval"] if r["scope"] == summary["scope"]]
        count, metrics = episode_metrics(cases)
        assert count == summary["episodes"] and len(cases) == summary["cases"]
        for key, value in metrics.items():
            assert abs(value - summary["metrics"][key]) < 1e-12
        episode_results.append(dict(summary=summary, recomputed_metrics=metrics, cases=cases))
    output = dict(pair_experiments=support, episode_experiments=episode_results,
                  stable_patterns=inputs["stable-specificity.json"]["experiments"],
                  source_sha256={name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest()
                                 for name in names},
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Receipt-level recount, no repeated RF/permutation scan. "
                  "All labels conditional candidates, not decoded or verified identities. "
                  "Counts do not confer independent observations. Earlier feature selection "
                  "and calibration dependencies remain. Unknown decoded fields not excluded.")
    (BASE / "local/identity-scope-audit.json").write_text(json.dumps(output, indent=2) + "\n")
    for row in support:
        print(row["scope"], row["tier"], row["matched_pairs"], row["cross_session_pairs"],
              row["unique_candidates"])


if __name__ == "__main__":
    main()
