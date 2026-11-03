"""Read-only descriptive identity fragmentation on saved, complete protocols.

No model evaluation, CFO score, position/reference read, fit or selection occurs.
The model-assigned catalogue IDs are not independent satellite identity truth.
"""

import csv
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
DATA = REPORTS / "2026_10_16_dsx01_fast_association_losses"
SOURCES = ("S01", "S02", "S03", "S04", "S05")
METHODS = ("original", "fixed", "expanded", "b1000")
MAXIMUM_GAP_S = 1.0


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def state_path(method, source, arm):
    if method == "original":
        if arm != "fitted-c":
            raise ValueError("No original c0 protocol exists in this comparison")
        return (
            REPORTS / "2026_10_16_dsx01_models/results" / (f"{source}-full-fitted-c-original.npz")
        )
    if method in ("fixed", "expanded"):
        folder = "results" if method == "fixed" else "expanded-results"
        return REPORTS / "2026_10_16_dsx01_iteration2" / folder / (f"{source}-{arm}-profile.npz")
    if method == "b1000":
        return (
            REPORTS
            / "2026_10_17_dsx01_iteration4/frequency_bias/results"
            / (f"{source}-{arm}-b1000-profile.npz")
        )
    raise ValueError(method)


def validate_alignment(state, metadata):
    count = len(metadata)
    required = ("associated", "satellite_number", "times_s")
    if any(np.asarray(state[k]).shape != (count,) for k in required):
        raise ValueError("Saved state must retain every original source observation")
    if np.asarray(state["associated"]).dtype != np.bool_:
        raise ValueError("Saved association flags must be boolean")
    np.testing.assert_array_equal(state["times_s"], [r["time_s"] for r in metadata])
    checks = ["exact source length", "exact ordered time vector"]
    for key, field, transform in (
        ("observation_id", "observation_id", str),
        ("receiver", "receiver", lambda value: int(value) - 1),
        ("channel", "channel", int),
    ):
        if key in state:
            np.testing.assert_array_equal(state[key], [transform(r[field]) for r in metadata])
            checks.append("exact ordered " + key)
    if not np.isfinite(state["times_s"]).all():
        raise ValueError("Nonfinite source timestamps")
    if not np.issubdtype(state["satellite_number"].dtype, np.integer):
        raise ValueError("Integer model catalogue IDs required")
    return checks


def window_stats(state, indices, metadata, *, maximum_gap_s=MAXIMUM_GAP_S):
    if not np.isfinite(maximum_gap_s) or maximum_gap_s <= 0:
        raise ValueError("Positive finite adjacency gap required")
    ix = np.asarray(indices, dtype=int)
    if ix.ndim != 1 or len(set(ix)) != len(ix) or np.any(ix < 0) or np.any(ix >= len(metadata)):
        raise ValueError("Window membership must contain unique valid original row indices")
    assigned = state["associated"][ix]
    identities = state["satellite_number"][ix]
    counts = Counter(map(int, identities[assigned]))
    ordered_counts = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    dominant, dominant_count = ordered_counts[0] if ordered_counts else (None, 0)
    # Stable input order breaks equal-time ties. Unassigned rows are retained;
    # they break adjacency rather than bridging apparently continuous tracks.
    order = ix[np.argsort(np.asarray([metadata[i]["time_s"] for i in ix]), kind="stable")]
    eligible, switches = 0, 0
    exclusions = Counter()
    for a, b in zip(order[:-1], order[1:], strict=True):
        if not (state["associated"][a] and state["associated"][b]):
            exclusions["unassigned_endpoint"] += 1
            continue
        if any(
            metadata[a][field] != metadata[b][field]
            for field in ("receiver", "channel", "actual_rf_hz")
        ):
            exclusions["different_lane"] += 1
            continue
        gap = metadata[b]["time_s"] - metadata[a]["time_s"]
        if gap > maximum_gap_s:
            exclusions["gap_above_limit"] += 1
            continue
        eligible += 1
        switches += int(state["satellite_number"][a] != state["satellite_number"][b])
    n, selected = len(ix), int(assigned.sum())
    assert eligible + sum(exclusions.values()) == max(0, n - 1)
    return dict(
        observations=n,
        assigned=selected,
        unassigned=n - selected,
        distinct_assigned_ids=len(counts),
        ids_with_at_least_3_assignments=sum(v >= 3 for v in counts.values()),
        dominant_model_id=dominant,
        dominant_count=dominant_count,
        dominant_fraction_of_all=dominant_count / n if n else None,
        dominant_fraction_of_assigned=dominant_count / selected if selected else None,
        model_id_counts={str(k): v for k, v in ordered_counts},
        adjacent_observed_pairs=max(0, n - 1),
        adjacency_maximum_gap_s=maximum_gap_s,
        adjacent_assigned_comparisons=eligible,
        adjacent_identity_switches=switches,
        adjacent_identity_switch_fraction=switches / eligible if eligible else None,
        adjacency_exclusions=dict(exclusions),
    )


def comparison(original, variant):
    if original["observations"] != variant["observations"]:
        raise ValueError("Original denominator must not change")
    missing = original["observations"] - original["assigned"]
    net = variant["assigned"] - original["assigned"]
    return dict(
        original_assigned=original["assigned"],
        original_missing=missing,
        net_assigned_gain=net,
        net_original_missing_restored_fraction=net / missing if missing else None,
        strong_restoration_descriptive=bool(missing and net / missing >= 0.8),
    )


def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def main():
    started = time.monotonic()
    metadata = {s: [] for s in SOURCES}
    fields = (
        "observation_id",
        "time_s",
        "receiver",
        "channel",
        "actual_rf_hz",
        "original_associated",
        "original_best_satellite",
    )
    # Do not access measured CFO, posterior scores or position metadata.
    for line in (DATA / "context-observations.jsonl").read_text().splitlines():
        row = json.loads(line)
        metadata[row["source_id"]].append({key: row[key] for key in fields})
    regions = read_csv(DATA / "regions.csv")
    membership = read_csv(DATA / "membership.csv")
    lookup = {
        s: {r["observation_id"]: i for i, r in enumerate(rows)} for s, rows in metadata.items()
    }
    if any(len(lookup[s]) != len(metadata[s]) for s in SOURCES):
        raise ValueError("Unique observation IDs required")
    indices = {}
    for region in regions:
        members = [m for m in membership if m["region_id"] == region["region_id"]]
        if any(m["source_id"] != region["source_id"] for m in members):
            raise ValueError("Region source mismatch")
        indices[region["region_id"]] = [
            lookup[region["source_id"]][m["observation_id"]] for m in members
        ]
        if len(indices[region["region_id"]]) != int(region["observation_count"]):
            raise ValueError("Frozen membership denominator mismatch")
    assert len(regions) == 15 and sum(map(len, indices.values())) == 693
    assert sum(map(len, metadata.values())) == 20084
    inventory = [
        (method, arm, source, state_path(method, source, arm))
        for method in METHODS
        for arm in ("fitted-c", "zero-c")
        if not (method == "original" and arm == "zero-c")
        for source in SOURCES
    ]
    paths = [
        Path(__file__),
        HERE / "test_audit.py",
        HERE / "test_audit_v2.py",
        HERE / "V2_ERRATUM.md",
        HERE / "PROTOCOL.md",
        DATA / "context-observations.jsonl",
        DATA / "regions.csv",
        DATA / "membership.csv",
    ]
    paths += [path for _, _, _, path in inventory]
    # Bind the saved producers because old NPZs lack persisted row IDs.
    paths += [
        REPORTS / "2026_10_16_dsx01_models/run_evaluation.py",
        REPORTS / "2026_10_16_dsx01_models/common.py",
        REPORTS / "2026_10_16_dsx01_iteration2/run_profiles.py",
        REPORTS / "2026_10_16_dsx01_iteration2/run_expansion.py",
        REPORTS / "2026_10_17_dsx01_iteration4/frequency_bias/run_pilot.py",
    ]
    authority = {str(p): digest(p) for p in paths}
    with (HERE / "plan_v2.json").open("x") as stream:
        json.dump(
            dict(
                source_sha256=authority,
                objectives=0,
                fits=0,
                maximum_seconds=120,
                no_CFO_scores=True,
                no_position_reads=True,
            ),
            stream,
            indent=2,
        )
    states, alignment = {}, []
    for method, arm, source, path in inventory:
        with np.load(path, allow_pickle=False) as data:
            state = {
                key: data[key]
                for key in (
                    "associated",
                    "satellite_number",
                    "times_s",
                    "observation_id",
                    "receiver",
                    "channel",
                )
                if key in data
            }
        checks = validate_alignment(state, metadata[source])
        if method == "original":
            np.testing.assert_array_equal(
                state["associated"], [r["original_associated"] for r in metadata[source]]
            )
            np.testing.assert_array_equal(
                state["satellite_number"], [r["original_best_satellite"] for r in metadata[source]]
            )
            checks.append("original assignment and model-ID labels match frozen context")
        states[method, arm, source] = state
        alignment.append(
            dict(
                method=method,
                arm=arm,
                source_id=source,
                checks=checks,
                row_id_persisted="observation_id" in state,
                limitation=None
                if "observation_id" in state
                else (
                    "Ordered times plus frozen producer/common-observation ordering; "
                    "equal-time row swaps cannot be independently ruled out from this NPZ alone"
                ),
            )
        )
    rows = []
    for region in regions:
        source, window = region["source_id"], region["region_id"]
        original = window_stats(
            states["original", "fitted-c", source], indices[window], metadata[source]
        )
        if original["assigned"] != int(region["original_associated_count"]):
            raise ValueError("Original window replay mismatch")
        for method, arm, s, _ in inventory:
            if s != source:
                continue
            stats = window_stats(states[method, arm, source], indices[window], metadata[source])
            rows.append(
                dict(
                    window=window,
                    source_id=source,
                    method=method,
                    arm=arm,
                    **stats,
                    **comparison(original, stats),
                )
            )
    if time.monotonic() - started > 120:
        raise TimeoutError("Read-only audit budget exceeded")
    if any(digest(path) != expected for path, expected in authority.items()):
        raise ValueError("Source changed during audit")
    summary = dict(
        rows=rows,
        alignment=alignment,
        full_observations=20084,
        requested_observations=693,
        windows=15,
        complete_protocols=7,
        elapsed_seconds=time.monotonic() - started,
        objectives=0,
        fits=0,
        interpretation=(
            "Descriptive model-assignment dominance and fragmentation, "
            "not verified identity purity. A coherent segment may contain "
            "multiple real emitters."
        ),
        selection=(
            "No per-window method selection; every row retained, including "
            "failed-KKT endpoints from complete saved protocols."
        ),
    )
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (HERE / "windows.csv").open("w", newline="") as stream:
        flat = [
            {k: json.dumps(v, sort_keys=True) if isinstance(v, dict) else v for k, v in row.items()}
            for row in rows
        ]
        writer = csv.DictWriter(stream, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    print(
        json.dumps(
            dict(
                rows=len(rows),
                elapsed_seconds=summary["elapsed_seconds"],
                b1000_fitted_strong=[
                    r["window"]
                    for r in rows
                    if r["method"] == "b1000"
                    and r["arm"] == "fitted-c"
                    and r["strong_restoration_descriptive"]
                ],
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
