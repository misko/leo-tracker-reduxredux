"""Compare exact winner translations, observed Graph support, and positions."""

from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from ..__main__ import save_json
from ..scoring import ARMS, distance_km, distribution
from .alias_attribution import CONDITIONS, delta
from .alias_attribution_trial import ORDER, REPORT
from .factor_cross_results import checked_result
from .factor_cross_trial import write_members
from .full_held_scores import held_references
from .input_factor_bridge import REPO, _sha, check, read
from .input_factor_comparison import ledger, sealed
from .peak_support_results import systemd_runtime
from .peak_support_trial import read_band
from .prefix_figures import csv_file

LABELS = {
    "alias": "Capture-era alias index on matched winners",
    "residual": "Capture-era wrapped CFO on matched winners",
    "joint": "Capture-era alias index and wrapped CFO",
    "null": "Circular exchange of donor CFO deltas",
}


def owners(graph):
    result = {}
    for index, track in enumerate(graph["tracks"]):
        members = zip(track["ids"], track["times_s"], track["graph_cfo_hz"], strict=True)
        for observation, time, cfo in members:
            if observation in result:
                raise ValueError("Graph assigned an observation to more than one track")
            result[observation] = (index, time, cfo)
    if len(result) != graph["points"]:
        raise ValueError("Graph support accounting changed")
    return result


def coherent_spans(graph, steps):
    runs = []
    for track in graph["tracks"]:
        current = []
        sign = 0
        for i, obs in enumerate(track["ids"]):
            lift = steps.get(obs, 0)
            direction = (lift > 0) - (lift < 0)
            if direction != sign or direction == 0:
                if len(current) >= 2:
                    runs.append((len(current), current[-1] - current[0]))
                current = []
            if direction:
                current.append(track["times_s"][i])
            sign = direction
        if len(current) >= 2:
            runs.append((len(current), current[-1] - current[0]))
    return dict(
        runs_ge2=len(runs),
        runs_ge3_and_2s=sum(n >= 3 and t >= 2.0 for n, t in runs),
        largest_run_points=max((n for n, _ in runs), default=0),
        longest_span_s=max((t for _, t in runs), default=0),
    )


def graph_comparison(capture, wide, matched):
    first, second = owners(capture), owners(wide)
    common = first.keys() & second.keys()
    matched_ids = {r["observation"]: r for r in matched}
    compared = common & matched_ids.keys()
    overlap = defaultdict(Counter)
    for obs in sorted(common):
        overlap[second[obs][0]][first[obs][0]] += 1
    lifts = {}
    transitions = Counter()
    gauges = defaultdict(Counter)
    for obs in sorted(compared):
        raw = matched_ids[obs]["steps"]
        resolved, _ = delta(first[obs][2], second[obs][2])
        lifts[obs] = resolved
        transitions[f"{raw:+d}→{resolved:+d}"] += 1
        gauges[first[obs][0], second[obs][0]][resolved] += 1
    return dict(
        capture_points=len(first),
        wide_points=len(second),
        shared_graph_ids=len(common),
        capture_graph_only=len(first.keys() - second.keys()),
        wide_graph_only=len(second.keys() - first.keys()),
        selected_both_graphs=len(compared),
        selected_capture_graph_only=len((first.keys() - second.keys()) & matched_ids.keys()),
        selected_wide_graph_only=len((second.keys() - first.keys()) & matched_ids.keys()),
        selected_neither_graph=len(matched_ids.keys() - (first.keys() | second.keys())),
        selected_raw_nonzero_on_both=sum(bool(matched_ids[i]["steps"]) for i in compared),
        resolved_nonzero=sum(bool(x) for x in lifts.values()),
        graph_track_pairs=len(gauges),
        graph_track_pairs_with_inconsistent_offsets=sum(
            len(value) > 1 for value in gauges.values()
        ),
        resolved_nonmodal_after_one_offset_per_track_pair=sum(
            sum(value.values()) - max(value.values()) for value in gauges.values()
        ),
        transition_counts=dict(transitions),
        tracks_capture=len(capture["tracks"]),
        tracks_wide=len(wide["tracks"]),
        curved_capture=capture["curved"],
        curved_wide=wide["curved"],
        capture_track_span_s=distribution(
            [r["times_s"][-1] - r["times_s"][0] for r in capture["tracks"]]
        ),
        wide_track_span_s=distribution(
            [r["times_s"][-1] - r["times_s"][0] for r in wide["tracks"]]
        ),
        wide_track_dominant_capture_fraction=distribution(
            [max(c.values()) / sum(c.values()) for c in overlap.values()]
        ),
        per_track_raw_runs=coherent_spans(
            wide, {obs: r["steps"] for obs, r in matched_ids.items()}
        ),
        per_track_resolved_runs=coherent_spans(wide, lifts),
    )


def charts():
    return dict(
        version=1,
        charts=[
            dict(
                id=f"alias-attribution-{treatment}",
                method="alias_attribution",
                scope="roof",
                title=LABELS[treatment],
                caption=(
                    "All wide probes and winners retained. Winner CFO changes are limited "
                    "to unique physical matches. Capture-era v5 options are displayed separately."
                ),
                cases=list(ORDER[:4]),
                seal="figure-lock.json",
                provenance=["scores.csv", "numeric-summary.json", "graph-attribution.json"],
                series=[
                    dict(
                        key=key,
                        label=label,
                        file="figure-positions.jsonl.gz",
                        value=value,
                        native_authority="ordinary",
                        native_field="origin_native_sha256",
                    )
                    for key, label, value in (
                        ("one", LABELS[treatment], treatment),
                        ("stock", "Same phase-release solver on unchanged wide factors", "stock"),
                    )
                ],
            )
            for treatment in LABELS
        ],
    )


def arms(result):
    return {arm: {k: result["arms"][arm].get(k) for k in ("latlon", "rf_rms_hz")} for arm in ARMS}


def publish():
    lock = sealed(REPORT, "prediction-lock.json")
    plan = read(REPORT / "plan.json")
    for rel, expected in plan["sources"].items():
        check(REPO / rel, expected)
    for n, expected in plan["files"].items():
        check(REPORT / n, expected)
    measured = ledger(REPORT / "results.jsonl.gz")
    if set(measured) != set(lock["cases"]):
        raise ValueError("result row set differs from sealed measurement")
    graph = ledger(REPORT / "graph-traces.jsonl.gz")
    matched = ledger(REPORT / "winner-pairs.jsonl.gz")
    raw = {}
    for ident, pairs in matched.items():
        data = pairs["matches"]
        raw[ident] = dict(
            phase_delta_abs_ns=distribution([abs(r["epoch_samples"]) * 100 for r in data]),
            wrapped_cfo_delta_abs_hz=distribution([abs(r["residual_hz"]) for r in data]),
            median_integer_branch_residual_hz=median([r["residual_hz"] for r in data]),
        )
    raw_audit = read(REPORT / "match-audit.json")
    save_json(REPORT / "cfo-distributions.json", dict(case_counts=raw_audit, distributions=raw))
    archived, _ = read_band()
    refs = {r["id"]: r["truth"] for r in held_references("", ORDER[:4])[1]}
    selected, score, shape, summary = [], [], {}, defaultdict(Counter)
    for ident in ORDER[:4]:
        current = graph.get(ident + "-stock", {})
        donor = graph.get(ident, {})
        if current.get("status") == "ok" and donor.get("status") == "ok":
            summary["graph"]["completed_captures"] += 1
            shape[ident] = graph_comparison(
                donor["graph"], current["graph"], matched[ident]["matches"]
            )
            original_owner = owners(current["graph"])
            for condition in CONDITIONS[1:]:
                changed = graph.get(ident + "-" + condition, {})
                if changed.get("status") == "ok":
                    new = owners(changed["graph"])
                    shape[ident][condition] = dict(
                        points=len(new),
                        tracks=len(changed["graph"]["tracks"]),
                        graph_points_lost=len(original_owner.keys() - new.keys()),
                        graph_points_gained=len(new.keys() - original_owner.keys()),
                        shared_graph_resolved_changes=sum(
                            original_owner[i][2] != new[i][2]
                            for i in original_owner.keys() & new.keys()
                        ),
                    )
    for binding in plan["inputs"]:
        ident, condition = binding["recording"], binding["condition"]
        record = measured.get(binding["id"])
        original = archived[ident]
        if (
            binding["recipient_native_sha256"] != original["native_sha256"]
            or binding["origin_native_sha256"] != original["paired_ordinary_sha256"]
        ):
            raise ValueError("independent wide comparator differs from recorded native inputs")
        if record:
            fit = checked_result(record, binding, plan)
        else:
            fit = dict(
                status="missing",
                reason="No terminal service receipt",
                boundary="Stored GLRT factors through phase-release",
                metrics=dict(position_attempted=False),
            )
        reference = measured.get(ident + "-stock", {}).get("result", original["result"])
        if condition == "stock" and fit["status"] == "ok":
            summary["stock"]["exact_archived_endpoints_rms"] += arms(fit) == arms(
                original["result"]
            )
        selected.append(
            dict(
                id=ident,
                tile=original["tile"],
                method=condition,
                native_sha256=binding["native_sha256"],
                origin_native_sha256=binding["origin_native_sha256"],
                catalog_sha256=binding["catalog_sha256"],
                result=fit,
            )
        )
        summary[condition][fit["status"]] += 1
        measured_graph = graph.get(binding["id"], {}).get("graph")
        for arm in ARMS:
            arm_result = fit.get("arms", {}).get(arm, {})
            ref_arm = reference.get("arms", {}).get(arm, {})
            err = distance_km(arm_result.get("latlon"), refs[ident])
            old = distance_km(ref_arm.get("latlon"), refs[ident])
            freq, old_freq = arm_result.get("rf_rms_hz"), ref_arm.get("rf_rms_hz")
            score.append(
                dict(
                    id=ident,
                    condition=condition,
                    arm=arm,
                    status=fit["status"],
                    error_km=err,
                    stock_error_km=old,
                    error_delta_km=None if err is None or old is None else err - old,
                    conditional_rms_hz=freq,
                    stock_conditional_rms_hz=old_freq,
                    conditional_rms_delta_hz=None
                    if freq is None or old_freq is None
                    else freq - old_freq,
                    changed_winners=binding["changes"].get("changed_winners", 0),
                    nonzero_alias_changes=binding["changes"].get("nonzero_alias_changes", 0),
                    graphs=len(measured_graph["tracks"]) if measured_graph is not None else None,
                    wall_s=record["wall_s"] if record else None,
                    systemd_runtime_s=systemd_runtime(record["diagnostics"]) if record else None,
                )
            )
    save_json(REPORT / "graph-attribution.json", shape)
    save_json(
        REPORT / "numeric-summary.json",
        dict(
            completed=len(measured),
            planned=len(plan["inputs"]),
            inclusive=dict(summary),
            prediction_lock_sha256=_sha(REPORT / "prediction-lock.json"),
        ),
    )
    csv_file(REPORT / "scores.csv", score)
    write_members(REPORT / "figure-positions.jsonl.gz", selected)
    save_json(REPORT / "figures.json", charts())
    save_json(
        REPORT / "figure-lock.json",
        dict(
            cases=list(ORDER[:4]),
            scorer_sha256=_sha(Path(__file__)),
            files={
                name: _sha(REPORT / name)
                for name in (
                    "graph-attribution.json",
                    "numeric-summary.json",
                    "scores.csv",
                    "cfo-distributions.json",
                    "figure-positions.jsonl.gz",
                    "prediction-lock.json",
                )
            },
        ),
    )


if __name__ == "__main__":
    publish()
