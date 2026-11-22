"""Compare canonical duplicate polynomial fits on four saved detector files."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from leo.analysis.polynomial_tracklets import TrackConfig
from tools.pipeline_eval.variants.experimental.graph_alias import canonical_alias_proposals

from graph_saved_trial import membership_difference, run


def summary(base, canonical):
    def owners(prepared):
        return {oid: t["key"] for t in prepared["tracks"] for oid in t["observation_ids"]}

    before, after = owners(base), owners(canonical)
    moved = [oid for oid in before.keys() & after.keys() if before[oid] != after[oid]]
    return dict(lost=len(before.keys() - after.keys()), gained=len(after.keys() - before.keys()),
                reassigned=len(moved))


def read_saved(config, paths):
    cfg = TrackConfig(**json.loads(config.read_bytes())["config"])
    cases = ("dense_deployed", "dense_packed", "public_north", "public_south")
    pairs = {}
    output = dict(config_sha256=sha256(config.read_bytes()).hexdigest(), cases={})
    for i, (case, path) in enumerate(zip(cases, paths, strict=True)):
        data = path.read_bytes()
        document = json.loads(data)
        def candidate():
            with canonical_alias_proposals() as metrics:
                prepared, stats = run(document, cfg)
            return prepared, stats, dict(metrics)
        if i % 2:
            optimized, b, counters = candidate()
            prior, a = run(document, cfg)
        else:
            prior, a = run(document, cfg)
            optimized, b, counters = candidate()
        pairs[case] = prior, optimized
        stats = {
            key: {field: row[field] for field in ("cpu_ns", "digest", "owned", "track_count")}
            for key, row in (("reference", a), ("canonical", b))
        }
        output["cases"][case] = dict(
            path=str(path), sha256=sha256(data).hexdigest(), winners=a["observations"],
            curved_keys_equal=a["curved_keys"] == b["curved_keys"],
            curved_key_counts=[len(a["curved_keys"]), len(b["curved_keys"])],
            metrics=counters, ownership_changes=summary(prior, optimized), **stats,
        )
    a, b = pairs["dense_deployed"], pairs["dense_packed"]
    output["dense_receiver_comparison"] = {
        label: membership_difference(x, y) for label, x, y in zip(("reference", "canonical"), a, b)
    }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("native", type=Path, metavar="detections.json", nargs=4,
                        help="deployed DS30, packed DS30, public north and public south")
    args = parser.parse_args()
    print(json.dumps(read_saved(args.config, args.native), indent=2))


if __name__ == "__main__":
    main()
