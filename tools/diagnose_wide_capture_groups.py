"""Compare acquisition groups after independent wide inference; no reference input."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from compare_positioning_cohorts import fit
from replay_regional_doppler import digest, write_json

from leo.analysis.research.regional_doppler import Region


def episode_metadata(assignments, evidence):
    documents, sources, rows = {}, {}, []
    for assignment in assignments:
        sid = assignment["session_id"]
        if sid not in documents:
            path = evidence / "evidence" / (sid + ".json")
            documents[sid] = json.loads(path.read_text())
            sources[str(path)] = digest(path)
        doc = documents[sid]
        episodes = [e for e in doc["episodes"] if e["episode_id"] == assignment["episode_id"]]
        if len(episodes) != 1:
            raise ValueError("episode identity missing or duplicated")
        members = episodes[0]["members"]
        series = [s for s in doc["series"] if s["tracklet_id"] in members]
        if len(series) != len(members):
            raise ValueError("episode member evidence missing or duplicated")
        channels = {s["channel"] for s in series}
        edges = {s["edge"] for s in series}
        rows.append(
            dict(
                **assignment,
                sample_rate_hz=doc["inventory"]["sample_rate_hz"],
                channel=str(next(iter(channels))) if len(channels) == 1 else "mixed",
                edge=next(iter(edges)) if len(edges) == 1 else "mixed",
                utc_6h=datetime.fromtimestamp(
                    (doc["inventory"]["reference_utc_ns"] // (21600 * 10**9)) * 21600,
                    tz=UTC,
                ).isoformat(),
            )
        )
    return rows, sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["run", "evidence", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument(
        "--grouping", action="append", choices=["sample_rate_hz", "channel", "edge", "utc_6h"]
    )
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("fresh output required")
    parent_path = args.run / "inference.json"
    parent = json.loads(parent_path.read_text())
    if (
        not parent["complete"]
        or parent["position_truth_used"]
        or parent["prior_matched_norads_used"]
    ):
        raise ValueError("completed independent parent required")
    data = dict(np.load(args.run / "states.npz"))
    rows, sources = episode_metadata(parent["assignments"], args.evidence)
    selected = [
        i for i, a in enumerate(parent["assignments"]) if a in parent["selected_assignments"]
    ]
    output = dict(
        evaluation_location_used=False,
        parent_digest=digest(parent_path),
        states_digest=digest(args.run / "states.npz"),
        evidence_digests=sources,
        assignments=rows,
        interpretation="conditional subgroup diagnostics; identities frozen from full wide search",
        models=[],
    )
    for grouping in args.grouping or ["sample_rate_hz", "channel", "edge"]:
        labels = np.asarray([r[grouping] for r in rows])[data["episode"]]
        for label in np.unique(labels):
            for cohort in ["all", "selected"]:
                mask = labels == label
                if cohort == "selected":
                    mask &= np.isin(data["episode"], selected)
                if len(np.unique(data["norad"][mask])) < 3:
                    output["models"].append(
                        dict(
                            grouping=grouping,
                            group=str(label),
                            cohort=cohort,
                            status="insufficient independent satellite identities",
                        )
                    )
                    continue
                for clock in [False, True]:
                    result = fit(
                        data,
                        Region(**parent["region"]),
                        parent["initial"],
                        "observation",
                        True,
                        subset=mask,
                        fit_clock=clock,
                    )
                    row = dict(grouping=grouping, group=str(label), cohort=cohort, **result)
                    output["models"].append(row)
                    print(
                        grouping,
                        label,
                        cohort,
                        clock,
                        result["latitude_deg"],
                        result["longitude_deg"],
                        flush=True,
                    )
    write_json(args.output, output)


if __name__ == "__main__":
    main()
