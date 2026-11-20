"""Score native dropout, Graph assignment changes and authentic reconnection fits."""

import argparse
import gzip
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

import numpy as np

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import drop_mechanism_trial as trial
from .full_held_scores import held_references
from .full_v5_check import _sha
from .locked_assignments_results import compare_points, scientific
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
METHOD = "drop_mechanism"
read = whole_iq.read


def graph_points(observed):
    return {
        oid: dict(group=track["key"], curved=track["curved"])
        for track in observed["track_groups"]
        for oid in track["ids"]
    }


def topology(full, other, lost):
    initial, final = (graph_points(row) for row in (full, other))
    winners, retained = (set(row["observations"]) for row in (full, other))
    if retained - winners or winners - retained != lost:
        raise ValueError("installed native selection did not reproduce the lost gated positives")
    matched = initial.keys() & final.keys()
    forward, backward = defaultdict(set), defaultdict(set)
    for oid in matched:
        before, after = initial[oid]["group"], final[oid]["group"]
        forward[before].add(after)
        backward[after].add(before)
    return dict(
        common=len(matched),
        stock_groups_split=sum(len(shards) > 1 for shards in forward.values()),
        retained_groups_merged=sum(len(donors) > 1 for donors in backward.values()),
        common_curvature_class_changes=sum(
            initial[o]["curved"] != final[o]["curved"] for o in matched
        ),
        positive_before=len(winners),
        positive_after=len(retained),
        lost_positive_track_members=len(lost & initial.keys()),
        shared_observed_no_longer_in_graph=len(initial.keys() - final.keys() - lost),
        previously_unowned_now_in_graph=len(final.keys() - initial.keys()),
    )


def continuity_case(full_path, full, session, config, outcomes):
    # The hardware clock maps packet IDs to times without consulting candidate gains.
    doc = read(full_path)
    source = doc["source"]
    anchor = doc["clock_anchor"]["sample_counter"]
    times, lanes, owners = {}, defaultdict(list), {}
    winners = set(full["observations"])
    for row in source["probes"]:
        sid = f"{session}:{row['receiver_id']}:{row['valid_start_counter']}"
        ident = "sha256:" + sha256(sid.encode()).hexdigest()
        if ident in winners:
            seconds = (row["valid_start_counter"] - anchor) / source["sample_rate_hz"]
            seconds += source["probe_ms"] * 0.0005
            times[ident] = seconds
            owner = row["receiver_id"], row["channel"], row["actual_rf_hz"]
            owners[ident] = owner
            lanes[owner].append(seconds)
    if times.keys() != winners:
        raise ValueError("complete Graph observation lost its physical timing authority")
    max_gap = config["max_gap_s"]
    predecessors = []
    for value in lanes.values():
        t = np.array(sorted(value))
        predecessors.extend((np.arange(len(t)) - np.searchsorted(t, t - max_gap)).tolist())
    broken, dropped_by_lane = {}, {}
    for key, lost in outcomes.items():
        fails = []
        lane_counts = defaultdict(int)
        for oid in lost:
            rx, channel, rf = owners[oid]
            lane_counts[f"{rx}/{channel}/{rf}"] += 1
        for track in full["track_groups"]:
            points = track["ids"]
            keep = [i for i, oid in enumerate(points) if oid not in lost]
            for low, high in zip(keep, keep[1:], strict=False):
                t = [times[oid] for oid in points[low : high + 1]]
                if high > low + 1 and t[-1] - t[0] > max_gap and max(np.diff(t)) <= max_gap:
                    fails.append(
                        dict(track=track["key"], start_s=t[0], end_s=t[-1], gap_s=t[-1] - t[0])
                    )
        broken[key] = fails
        dropped_by_lane[key] = dict(sorted(lane_counts.items()))
    return dict(
        maximum_predecessors=max(predecessors),
        above_cap_48=sum(x > 48 for x in predecessors),
        newly_broken_original_intervals=broken,
        lost_gated_winners_by_receiver_channel_rf=dropped_by_lane,
    )


def failed(attempt):
    timeout = any("timeout" in log for log in attempt["terminal"])
    return dict(
        status="timed_out" if timeout else "failed",
        reason="Physical drop-mechanism solve did not complete",
        boundary="Complete or retained native GLRT through installed compact v5",
        arms={arm: dict(latlon=None) for arm in ARMS},
        metrics={},
    )


def runs(work, plan):
    path = trial.sealed(REPORT, "prediction-lock.json", "attempts.jsonl.gz")
    raw = rows_from(path)
    found = {(a["id"], a["method"]) for a in raw}
    if len(found) != len(raw) or found != {(i, m) for i in trial.PINS for m in trial.METHODS}:
        raise ValueError("missing complete attempt roster")
    results, resources = {}, []
    for a in raw:
        ident, method = a["id"], a["method"]
        cell = plan["cases"][ident]["source"][trial.METHODS[method]]
        if (
            a["native_sha256"] != cell["native_sha256"]
            or a["plan_sha256"] != _sha(REPORT / "plan.json")
            or a["pin"] != plan["pins"][ident]
        ):
            raise ValueError("measured endpoint differs from the prospectively locked input")
        root = work / ident / method / "observation"
        log = whole_iq.checked(root / "service.log", a["log_sha256"])
        files = [log]
        actual = None
        if a["outcome_sha256"]:
            outcome = whole_iq.checked(root / "outcome.json", a["outcome_sha256"])
            files.append(outcome)
            if a["returncode"] == 0:
                actual = read(outcome)
        if a["returncode"] == 0 and not actual:
            raise ValueError("completed fit has no resource/position evidence")
        for file in files:
            write(
                REPORT / f"{ident}-{method}-{file.name}.gz",
                gzip.compress(file.read_bytes(), mtime=0),
            )
        metrics = (actual or {}).get("bounds", {})
        for edge in ("start", "end"):
            if metrics:
                record = metrics[edge]
                if (
                    record["memory.max"] != plan["memory_bytes"]
                    or record["memory.swap.max"]
                    or record["memory.swap.current"]
                    or metrics["pin"] != a["pin"]
                ):
                    raise ValueError("worker exceeded its recorded physical resource policy")
        result = actual["result"] if actual else failed(a)
        validate_result(result)
        results[ident, method] = result, (actual or {}).get("observation")
        resources.append(
            dict(
                id=ident,
                method=method,
                pin=a["pin"],
                status=result["status"],
                returncode=a["returncode"],
                service_wall_s=a["supervisor_wall_s"],
                process_wall_s=metrics.get("wall_s"),
                process_cpu_s=metrics.get("cpu_s"),
                cg_peak_bytes=metrics.get("end", {}).get("memory.peak"),
                _stage_s=result["metrics"].get("stage_s", {}),
            )
        )
    labels = sorted({k for r in resources for k in r["_stage_s"]})
    for r in resources:
        times = r.pop("_stage_s")
        r.update({name + "_wall_s": times.get(name) for name in labels})
    return results, resources


def archived():
    q = trial.arrival
    return {
        "full": {
            row["id"]: row
            for row in rows_from(
                trial.sealed(q.PARENT, "prediction-lock.json", "positions.jsonl.gz")
            )
            if row["method"] == q.whole_center_union.METHOD
        },
        "retained": {
            row["id"]: row
            for row in rows_from(
                trial.sealed(
                    q.REPORT, "positions-candidate-lock.json", "positions-candidate.jsonl.gz"
                )
            )
        },
    }


def before_after(left, right, repairs):
    new_ids = {r["id"] for r in repairs}
    if repairs and len(new_ids) != len(repairs):
        raise ValueError("repair duplicated an input graph point")
    orig, new = (graph_points(value) for value in (left, right))
    if (
        left["observations"] != right["observations"]
        or new.keys() - orig.keys() != new_ids
        or any(new.get(k) != v for k, v in orig.items())
        or new_ids - set(left["observations"])
    ):
        raise ValueError("reconnect changed original group membership or invented an observation")
    return new_ids


def effects(case, cell, estimates, parents):
    data = {}
    present, full = estimates[case, "full"]
    candidates = {}
    for method in trial.METHODS:
        result, graph = estimates[case, method]
        if graph is None:
            data[method] = dict(status=result["status"])
            continue
        one = dict(
            status=result["status"],
            graph_tracks=len(graph["track_groups"]),
            active_curved_tracks=sum(row["curved"] for row in graph["track_groups"]),
            native_positive=len(graph["observations"]),
            cavity_offered=graph.get("cavity_offered"),
            cavity_adopted=graph.get("cavity_adopted"),
            cavity_trials=graph.get("cavity_trials", []),
            fit_path=graph.get("fit_path"),
            signed=graph.get("signed"),
        )
        if one["signed"]:
            one["signed_to_returned_km"] = {
                arm: distance_km(one["signed"][arm]["latlon"], result["arms"][arm]["latlon"])
                for arm in ARMS
            }
        inp = cell["source"][trial.METHODS[method]]
        if method in ("full", "retained"):
            expected = parents[method][case]
            if expected["native_sha256"] != inp["native_sha256"]:
                raise ValueError("archived position does not use this input")
            one["exact_archived_parent"] = scientific(result) == scientific(expected["result"])
        if method != "full" and full:
            missing = set(inp["lost_positive_ids"])
            candidates[method] = missing
            one["graph_over_full"] = topology(full, graph, missing)
            for layer in ("conservative", "final"):
                if layer in graph and layer in full:
                    one[layer] = {
                        a: compare_points(full[layer][a], graph[layer][a])
                        for a in ("curved", "predictive")
                    }
                    for a, evidence in one[layer].items():
                        evidence["gate_positive_lost_from_full_active"] = len(
                            missing & full[layer][a].keys()
                        )
                        evidence["surviving_full_points_no_longer_active"] = len(
                            full[layer][a].keys() - graph[layer][a].keys() - missing
                        )
        if method.startswith("corrected-"):
            control = {"corrected-real": "retained", "corrected-hash": "hash"}[method]
            original, base = estimates[case, control]
            one["links"] = graph["gains"]
            if base:
                gained = before_after(base, graph, graph["gains"])
                one["linked_previously_grouped_in_complete"] = (
                    len(gained & graph_points(full).keys()) if full else None
                )
                one["fit_moves_km"] = {
                    a: distance_km(original["arms"][a]["latlon"], result["arms"][a]["latlon"])
                    for a in ARMS
                }
                if not gained and scientific(original) != scientific(result):
                    raise ValueError("empty reconnect altered science")
        data[method] = one
    if full and present["status"] == "ok":
        native = whole_iq.checked(
            Path(cell["source"]["full"]["native"]), cell["source"]["full"]["native_sha256"]
        )
        config = read(whole_iq.checked(Path(cell["config"]["path"]), cell["config"]["sha256"]))
        data["continuity"] = continuity_case(
            native, full, cell["session"], config["config"], candidates
        )
    return data


def publish(work):
    plan = read(trial.sealed(REPORT, "prediction-lock.json", "plan.json"))
    for name, digest in plan["parents"].items():
        whole_iq.checked(ROOT / name, digest)
    estimates, resources = runs(work, plan)
    parents = archived()
    previous = {
        ident: effects(ident, row, estimates, parents) for ident, row in plan["cases"].items()
    }
    save_json(REPORT / "path-effects.json", previous)
    _, records = held_references(None, trial.PINS)
    refs = {r["id"]: r for r in records}
    rows, scores = [], []
    for (ident, method), (result, obs) in estimates.items():
        case = plan["cases"][ident]
        source = case["source"]
        one = source[trial.METHODS[method]]
        rows.append(
            dict(
                id=ident,
                method=f"{METHOD}_{method}",
                result=result,
                tile=case["tile"],
                native_sha256=one["native_sha256"],
                paired_capture_sha256=case["paired_capture_sha256"],
                original_request_sha256=case["request_sha256"],
                catalog_sha256=case["catalogue"],
                complete_native_sha256=source["full"]["native_sha256"],
                real_native_sha256=source["real"]["native_sha256"],
                hash_native_sha256=source["hash"]["native_sha256"],
            )
        )
        for arm, measurement in result["arms"].items():
            ref = refs[ident]
            scores.append(
                dict(
                    id=ident,
                    condition=method,
                    arm=arm,
                    status=result["status"],
                    error_km=distance_km(measurement["latlon"], ref["truth"]),
                    rms_hz=measurement.get("rf_rms_hz"),
                    frequency_objective=result["metrics"].get(f"{arm}_frequency_score"),
                    omitted_visits=len(one["omitted_visits"]),
                    lost_positives=len(one["lost_positive_ids"]),
                    reattached_observations=len(obs.get("gains", [])) if obs else None,
                    **{f"v5_{r}_error_km": ref["reference"][r][arm]["error_km"] for r in ROLES},
                )
            )
    write(REPORT / "positions.jsonl.gz", compressed_rows(rows))
    csv_file(REPORT / "scores.csv", scores)
    csv_file(REPORT / "resources.csv", resources)
    figures()


def figures():
    provenance = ("prediction-lock.json", "scores.csv", "resources.csv", "path-effects.json")
    files = ("positions.jsonl.gz", *provenance)
    save_json(
        REPORT / "figure-lock.json",
        dict(
            cases=list(trial.PINS),
            files={name: _sha(REPORT / name) for name in files},
        ),
    )
    match = [
        "tile",
        "catalog_sha256",
        "paired_capture_sha256",
        "original_request_sha256",
        "complete_native_sha256",
        "real_native_sha256",
        "hash_native_sha256",
    ]
    methods = (
        ("real", "retained", "Genuine queue loss"),
        ("hash", "hash", "Count-matched hash loss"),
    )
    charts = []
    for label, case, title in methods:
        charts.append(
            dict(
                id=f"drop-reconnect-{label}",
                method=f"{METHOD}_corrected-{label}",
                scope="roof",
                cases="sealed",
                seal="figure-lock.json",
                provenance=list(provenance),
                title=f"Private track reconnect · {title}",
                caption=(
                    "Complete and dropped factors from the same two original recordings. "
                    "Reconnect uses observed gated positives and missing-visit lane clocks."
                ),
                series=[
                    dict(
                        key=key,
                        value=f"{METHOD}_{mode}",
                        label=name,
                        file=files[0],
                        native_field="paired_capture_sha256",
                        match=match,
                    )
                    for key, name, mode in (
                        ("one", "Reconnect policy", f"corrected-{label}"),
                        ("stock", "Original complete factors", "full"),
                        ("one_native_factors", title, case),
                    )
                ],
            )
        )
    save_json(REPORT / "figures.json", dict(version=1, charts=charts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    publish(parser.parse_args().work)
