"""Read-only source-window identity census; no tracking or position changes."""

import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from band_calibrated_merge_study import REPORT
from continuous_merge_study import sha, write

ORIGINAL = Path("/srv/bulk/leo-dev/leo-track-merge-study/reports/2026_10_12_continuous_track_merge")
OUTPUT = REPORT / "window-identity"


def summarize(probes):
    groups = defaultdict(list)
    passing = Counter()
    exposures = Counter()
    for probe in probes:
        key = tuple(
            probe[field]
            for field in (
                "receiver_id",
                "valid_start_counter",
                "payload_start_sample",
                "probe_start_ms",
            )
        )
        groups[key].append(probe)
        exposures[probe["channel"]] += 1
        if any(c["passed_fractional_margin_gate"] for c in probe["candidates"]):
            passing[probe["channel"]] += 1
    duplicates = [group for group in groups.values() if len(group) > 1]
    cross = [
        group
        for group in duplicates
        if (any(p["channel"] <= 4 for p in group) and any(p["channel"] >= 5 for p in group))
    ]
    return {
        "reported_probes": len(probes),
        "distinct_metadata_keys": len(groups),
        "repeated_keys": len(duplicates),
        "cross_band_repeated_keys": len(cross),
        "reported_exposures_by_channel": {str(ch): exposures[ch] for ch in range(1, 9)},
        "passing_probes_by_channel": {str(ch): passing[ch] for ch in range(1, 9)},
        "low_passing_probes": sum(passing[ch] for ch in range(1, 5)),
        "high_passing_probes": sum(passing[ch] for ch in range(5, 9)),
        "channels_with_pass": sum(passing[ch] > 0 for ch in range(1, 9)),
    }


def main():
    membership_path = ORIGINAL / "membership.json"
    membership = json.loads(membership_path.read_bytes())
    records = []
    bindings = {str(membership_path): sha(membership_path)}
    for member in membership["members"]:
        case = ORIGINAL / "local" / member["dataset"] / member["session_id"]
        record = {k: member[k] for k in ("dataset", "session_id", "role")}
        record.update(status="failed", reason=None)
        source_path, census_path = case / "source.json", case / "census.json"
        try:
            source = json.loads(source_path.read_bytes())
            census = json.loads(census_path.read_bytes())
            if source["session_id"] != member["session_id"]:
                raise ValueError("source recording differs from membership")
            if source["input_manifest_sha256"] != census["input_manifest_sha256"]:
                raise ValueError("source and census recording digests differ")
            record.update(
                summarize(source["probes"]),
                status="complete",
                radio_id=source["radio_id"],
                qualified=source["qualified"],
            )
            bindings.update({str(p): sha(p) for p in (source_path, census_path)})
        except (OSError, ValueError, KeyError) as error:
            record["reason"] = f"{type(error).__name__}: {error}"
        records.append(record)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write(
        OUTPUT / "results.json",
        {
            "records": records,
            "input_bindings": bindings,
            "script_sha256": sha(Path(__file__)),
            "reference_usage": "none",
            "metadata_key": [
                "receiver_id",
                "valid_start_counter",
                "payload_start_sample",
                "probe_start_ms",
            ],
            "scope": (
                "All frozen DS20/DS16 members; exact reported-window metadata collisions only. "
                "Distinct keys do not prove disjoint IQ support, true RF carrier or LNB state. "
                "Passing flags are detector output, not confirmed satellite counts. "
                "Probes without reports are not counted as exposures. "
                "No new inference or collection."
            ),
        },
    )
    fig, axis = plt.subplots(figsize=(10, 5), constrained_layout=True)
    for dataset, color in (("DS20", "tab:orange"), ("DS16", "tab:blue")):
        for role, marker in (("development", "o"), ("validation", "x")):
            selected = [
                r
                for r in records
                if r["status"] == "complete" and r["dataset"] == dataset and r["role"] == role
            ]
            axis.scatter(
                [r["low_passing_probes"] for r in selected],
                [r["high_passing_probes"] for r in selected],
                marker=marker,
                color=color,
                label=f"{dataset} {role}",
                alpha=0.8,
            )
    axis.set_xlabel("CH1–4 reported probes with a passing candidate")
    axis.set_ylabel("CH5–8 reported probes with a passing candidate")
    axis.set_yscale("symlog", linthresh=1)
    axis.grid(alpha=0.2)
    axis.legend(fontsize=8)
    axis.set_title("Frozen corpus detection support · passing GLRT is not satellite identity")
    fig.savefig(OUTPUT / "reported-detection-support.png", dpi=160)
    plt.close(fig)
    print(
        json.dumps(
            {
                "members": len(records),
                "complete": sum(r["status"] == "complete" for r in records),
                "failures": [r for r in records if r["status"] != "complete"],
                "repeated_keys": sum(r.get("repeated_keys", 0) for r in records),
                "cross_band_repeated_keys": sum(
                    r.get("cross_band_repeated_keys", 0) for r in records
                ),
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
