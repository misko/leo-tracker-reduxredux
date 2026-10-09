"""Publish metadata coverage, exposure and group assignment without position data."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    manifest = json.loads((HERE / "local/manifest.json").read_bytes())
    data = json.loads((HERE / "membership.json").read_bytes())
    groups = data["grouping"]["groups"]
    assignment = {sid: g["assignment"] for g in groups for sid in g["session_ids"]}
    colors = {
        "development": "#197278",
        "closed_reserve": "#d79420",
        "pending_exposure_review": "#9553a6",
    }
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for state in colors:
        rows = [r for r in data["members"] if assignment[r["session_id"]] == state]
        if rows:
            axes[0].scatter(
                [datetime.fromtimestamp(r["capture_start_utc_ns"] / 1e9, UTC) for r in rows],
                [r["sample_rate_hz"] / 1e6 for r in rows],
                c=colors[state],
                label=f"{state} ({len(rows)})",
            )
    axes[0].set_ylabel("Sample rate, MS/s")
    axes[0].set_xlabel("Recording start UTC")
    axes[0].legend(fontsize=8)
    axes[0].tick_params(axis="x", rotation=25)
    for i, group in enumerate(groups):
        axes[1].bar(i + 1, len(group["session_ids"]), color=colors[group["assignment"]])
    axes[1].set_xlabel("Acquisition group in frozen hash-rank order")
    axes[1].set_ylabel("Whole recordings per group")
    fig.suptitle("Newer sealed recordings: metadata only, no localization outcomes")
    fig.savefig(HERE / "membership.png", dpi=170)
    plt.close(fig)
    count = manifest["counts"]
    assignment_counts = Counter(assignment.values())
    exposure_counts = Counter(r["exposure"]["exposure"] for r in data["members"])
    links = data["grouping"]["metadata_links"]
    lines = [
        "# Iteration89: newer-data metadata mint and split",
        "",
        "**Metadata inventory and seal verification completed. No new localization "
        "outcome was opened, no analysis or RF collection was started, and no retention "
        "hold was created. All eleven existing POST18-RESERVE outcomes remain closed.**",
        "",
        "![Metadata membership and acquisition groups](membership.png)",
        "",
        "| Property | Value |",
        "|---|---|",
        "| Window, start inclusive / cutoff exclusive | "
        f"{data['window'][0]} / {data['window'][1]} |",
        f"| Full sealed membership | {count['recordings']} |",
        f"| Retained visits | {count['visits']} |",
        f"| Valid seconds per receiver | {count['valid_seconds_per_receiver']:.2f} |",
        f"| Referenced compressed bytes | {count['compressed_bytes']} |",
        f"| Sample-rate counts | {count['sample_rate_counts']} |",
        f"| Source kinds | {count['source_kind_counts']} |",
        "| Exclusions / observed unsealed partials | "
        f"{len(manifest['excluded_candidates'])} / {len(manifest['incomplete_recordings'])} |",
        f"| Whole acquisition groups | {len(groups)} |",
        f"| Group assignments | {data['grouping']['group_assignment_counts']} |",
        f"| Recording assignments | {dict(assignment_counts)} |",
        f"| Manifest SHA256 | `{data['manifest_sha256']}` |",
        "",
        "The cutoff was clock-frozen before inventory and committed/published in "
        "`15e7ef869`. All784 frozen source/runtime/parent hashes passed before the "
        "unchanged read-only mint ran. Published metadata used public storage ports; "
        "firmware archive inventory had no quality or analysis-readiness gate. "
        "No raw IQ was copied, decompressed or rehashed. Live inventory is non-atomic; "
        "the execution receipt records observed begin/end times.",
        "",
        "[membership.json](membership.json) binds every member, metadata/source hashes, "
        "exposure matches, groups and random ranks. [mint-execution.json](mint-execution.json) "
        "records exact commands and successful mint/verify exits. The local manifest and "
        "seal are authoritative, with copied parent provenance. "
        "[metadata.tar.zst](metadata.tar.zst) publishes the complete sealed metadata snapshot "
        "without raw IQ. [verification.json](verification.json) records independent seal, "
        "coverage and random-rank checks. Disjointness passed by "
        "session and IQ digest against DS16(63), DS17(51), DS18(34) and the existing "
        "reserve(11). Previous dataset names and membership remain unchanged.",
        "",
        "## Exposure and independence",
        "",
        f"Exposure classifications: {dict(exposure_counts)}. Exact identity search "
        "included hidden and ignored local receipts in both report worktrees and returned "
        "only filenames and identity tokens. No localization lines or values were opened. "
        "Known inspected rollout diagnostics are consumed development. Other matches "
        "require metadata-only classification before their groups can be reserved. "
        "No match alone establishes unseen validation. External machines, notebooks and "
        "conversation-only exposure were not fully audited.",
        "",
        "Available explicit acquisition identifiers: "
        f"{sum(bool(r['acquisition_identifiers']) for r in links)} "
        f"of{len(links)} recordings. Grouping joins available acquisition identities, "
        "duplicate manifest/IQ identities and fixed two-hour UTC start blocks. "
        "These groups remain an independence assumption; missing campaign metadata "
        "can leave longer clock/thermal dependence. Group random ranks use the frozen "
        "seed; consumed groups are development. Fewer than five eligible unconsumed "
        "groups produces no new reserve under the frozen rule. No split is rebalanced "
        "using quality or outcomes.",
        "",
        "Candidate/control policy must be frozen before opening new development results; "
        "reserved outcomes stay closed through tuning and final candidate freeze. "
        "Future evaluation reports all member failures, matched c0/fitted-c and "
        "frequency-fit effects separately from position accuracy.",
        "",
        "| Member | Session | Start UTC | MS/s | Visits | Exposure | Group assignment |",
        "|---|---|---|---:|---:|---|---|",
    ]
    for row in data["members"]:
        start = datetime.fromtimestamp(row["capture_start_utc_ns"] / 1e9, UTC).isoformat()
        lines.append(
            f"| {row['dataset_label']} | {row['session_id']} | {start} | "
            f"{row['sample_rate_hz'] / 1e6:g} | {row['visits']} | "
            f"{row['exposure']['exposure']} | {assignment[row['session_id']]} |"
        )
    lines += [
        "",
        "## Explicit unsealed partials",
        "",
        "These are not sealed evaluable members. Their observed metadata remains explicit; "
        "none is silently treated as an error-free recording.",
    ]
    for partial in manifest["incomplete_recordings"]:
        lines.append("\n- " + json.dumps(partial))
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    files = [p for p in HERE.iterdir() if p.is_file() and p.name != "integrity.json"]
    integrity = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    (HERE / "integrity.json").write_text(json.dumps(integrity, indent=2) + "\n")


if __name__ == "__main__":
    main()
