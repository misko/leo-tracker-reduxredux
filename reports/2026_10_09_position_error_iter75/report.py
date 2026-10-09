"""Publish reserve membership and acquisition-time metadata, never positions."""

import json
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "membership.json").read_text())
manifest = json.loads((HERE / "local/manifest.json").read_text())
members = data["members"]
fig, ax = plt.subplots(figsize=(10, 3), layout="constrained")
for rate, color in ((2500000, "#227c9d"), (10000000, "#ee7733")):
    rows = [r for r in members if r["sample_rate_hz"] == rate]
    ax.scatter(
        [datetime.fromtimestamp(r["capture_start_utc_ns"] / 1e9, UTC) for r in rows],
        [rate / 1e6] * len(rows),
        label=f"{rate / 1e6:g} MS/s",
        color=color,
        s=65,
    )
ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=UTC))
ax.set(
    xlabel="Capture start UTC (Oct8–9)",
    ylabel="Sample rate MS/s",
    yticks=[2.5, 10],
    title="Post-DS18 sealed reserve: metadata only, no positioning results inspected",
)
ax.legend()
fig.savefig(HERE / "reserve.png", dpi=160)
matches = sum(bool(r["prior_matching_files"]) for r in members)
excluded = len(manifest["excluded_candidates"])
partials = len(manifest["incomplete_recordings"])
text = f"""# Iteration75: sealed post-DS18 reserve for future validation

Frozen **{len(members)} existing whole recordings** after DS18's endpoint, before
inspecting their localization outcomes. This is a potential validation reserve,
**not yet certified unseen validation** and not a change to DS16/DS17/DS18.
No new RF collection, analysis run, publication or retention hold was initiated.

![Reserve timing and rates](reserve.png)

| Property | Value |
|---|---|
| Reserve identifier | POST18-RESERVE |
| Start inclusive | {data["window"][0]} |
| Cutoff exclusive; sealed by cutoff | {data["window"][1]} |
| Recordings | {len(members)} |
| Retained visits | {data["counts"]["visits"]} |
| Valid seconds per receiver | {data["counts"]["valid_seconds_per_receiver"]:.2f} |
| Sample rates | 3 at2.5MS/s,8 at10MS/s |
| Manifest SHA256 | `{data["manifest_sha256"]}` |
| Excluded candidates / observed unsealed partials | {excluded} / {partials} |
| Prior filename matches in the audited scope | {matches} recordings |

Commit `c7184a7ea` froze the boundary and source hashes before inventory. The end
is the clock timestamp taken before the first live inventory. The existing
metadata-only DS17/DS18 mint was reused unchanged with explicit successor identity
and boundaries. Its seal verifier passed. The parent DS18 manifest is bound to
the user-specified894a6f4b7055e5f6bd602f94ce3acf7f722f204c68c2b521a06dfd6be35a7516.

Authoritative local manifest:
`/home/mouse9911/gits/leo-hard60-default/reports/2026_10_09_position_error_iter75/local/manifest.json`,
with `seal.json` alongside it. Source snapshots and seals stay local; the small
[membership receipt](membership.json) publishes every member and its bindings.
Raw IQ was not copied, decompressed or rehashed. Inventory is a live, non-atomic
metadata read; future storage availability is not guaranteed.

## Complete membership

| Label | Session | Capture start UTC | MS/s | Visits | Prior matching files |
|---|---|---|---:|---:|---:|
"""
for r in members:
    time = datetime.fromtimestamp(r["capture_start_utc_ns"] / 1e9, UTC).isoformat()
    text += (
        f"| {r['dataset_label']} | `{r['session_id']}` | {time} | "
        f"{r['sample_rate_hz'] / 1e6:g} | {r['visits']} | {len(r['prior_matching_files'])} |\n"
    )
text += """
Both receivers stay together. Admission depends on capture-start boundary and
seal completion, not localization availability, signal quality or position error.
Disjointness from all63DS16,51DS17 and34DS18 members was checked by session ID and
uncompressed-IQ digest, with zero intersections. The parent-manifest hashes and
counts are retained in membership.json.

## Prior exposure and interpretation

The exact session IDs were searched in JSON/Markdown/Python/CSV report text in
both repository worktrees, returning only filenames and matching IDs. No
localization values were extracted, inspected or used. Default ignore rules apply;
external notebooks, other machines and private conversations were not audited.
No matching filename alone cannot prove independence. Matching filenames, if any,
are preserved per member for classification before validation, not used as a
quality-based membership exclusion.

The first unprivileged search stopped on unreadable local report-cache paths;
no no-match conclusion was taken from it. Its exact source is preserved as
exposure-attempt1.txt. A privileged batched exact-ID search completed afterward.
The intermediate privileged launch lacked rg in its default PATH; the completed
attempt used the explicit installed rg path. Neither failed attempt produced an
exposure conclusion or changed membership.

Keep positioning outcomes unexamined until the candidate and validation protocol
are frozen. A future evaluation must retain all11 members, explicitly report
missing inputs/failures, match c0/fitted-c observations/banks/priors/budgets, and
show position metrics separately from frequency-fit effects. Any revealed outcome
becomes consumed development evidence for subsequent tuning. This small reserve
does not establish worldwide, mobile-receiver or broad hardware generalization.

## Ongoing research and deployment

Iteration71's ordinary clock-proposal/cross-arm experiment continues unchanged.
The full148 DS16/DS17/DS18 benchmark mean remains1.360148km fitted-c /1.738896km
zero-c. The below1km goal is not achieved. Existing production hard60 recovery,
fitted-c default and longest16-track PNGs are preserved. No RF collection,
analysis default, contract, fixture or QNAP path was changed.
"""
(HERE / "README.md").write_text(text)
print("Reserve report", len(members), "members;", matches, "with prior filename matches")
