"""Score and bind the full actually stopped native replay against sealed terminals."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from . import online_full as full
from . import online_prefix as prefix
from .full_receiver_comparison import COMPACT as V5
from .generalization_challenge_scenes import clearance
from .online_prefix_trial import frozen_truth

METHOD = "native-clock-online-full"
MAIN = (METHOD, "online-full-terminal", V5)
BIND = ("native_sha256", "catalog_sha256")


def verify_frontiers(records):
    """Audit each worker's measured prefix independently of the host staging validation."""
    for bundle in records:
        terminal = bundle["terminal"].get("capture")
        if terminal and (
            not terminal["uses_complete_capture"]
            or terminal["first_noncausal_end_counter"] is not None
            or terminal["scheduled_visits"] != terminal["original_window_count"]
        ):
            raise ValueError("terminal archive has an incomplete original frontier")
        for row in bundle["rows"]:
            capture = row["capture"]
            end = capture["first_counter"] + row["checkpoint"] * 10_000_000
            excluded = capture["first_noncausal_end_counter"]
            complete = capture["uses_complete_capture"]
            if (
                capture["last_sample_counter"] > end
                or (not complete and (excluded is None or excluded <= end))
                or (complete and excluded is not None)
            ):
                raise ValueError("sealed prefix does not match its declared sample frontier")
            if row["result"]["status"] in {"ok", "withheld"} and (
                row["counts"]["probes"] != capture["expected_probes"]
                or row["latest_graph_time_s"] > capture["actual_last_sample_s"]
            ):
                raise ValueError("sealed Graph did not consume the expected native prefix")


def evaluate(sequence):
    rows = sequence["rows"]
    horizon = tuple(r["checkpoint"] for r in rows)
    if horizon != prefix.HORIZONS[: len(horizon)]:
        raise ValueError("the prefix sequence is outside the frozen schedule")
    recomputed = {}
    for n in range(1, len(rows) + 1):
        for arm in ARMS:
            full.decision(rows[:n], recomputed, arm)
        if n < len(rows) and len(recomputed) == 2:
            raise ValueError("the worker ran after both calibration arms resolved")
    assert {arm: list(v) for arm, v in recomputed.items()} == sequence["picked"]
    available = prefix.timeline(rows)
    terminal = sequence["terminal"]
    proof = terminal.get("capture")
    time = (
        [t + terminal["worker_wall_s"] for t in proof["available_at_elapsed_s"]]
        if (proof and terminal.get("worker_wall_s") is not None)
        else None
    )
    arms, choices = {}, {}
    for arm in ARMS:
        if arm in recomputed:
            i, decision = recomputed[arm]
            chosen = rows[i]
            arms[arm] = chosen["result"]["arms"][arm]
            choices[arm] = dict(
                checkpoint=chosen["checkpoint"],
                decision=decision,
                worker_status=chosen["result"]["status"],
                elapsed_host_s=available[i],
                terminal_elapsed_host_s=time,
                arm_worker_wall_s=sum(row["worker_wall_s"] or 0 for row in rows[: i + 1]),
                arm_worker_cpu_s=sum(
                    row.get("worker", {}).get("cpu_s", 0) for row in rows[: i + 1]
                ),
            )
        else:
            status = "failed" if sequence.get("error") else "missing"
            arms[arm] = dict(latlon=None, forced_latlon=None)
            choices[arm] = dict(worker_status=status, decision=sequence.get("error") or "batch cap")
    status = (
        "ok"
        if any(a["latlon"] is not None for a in arms.values())
        else choices[ARMS[0]]["worker_status"]
    )
    reason = None if status == "ok" else choices[ARMS[0]]["decision"]
    out = dict(
        status=status,
        reason=reason,
        boundary="Actually stopped native smooth-clock prefixes",
        arms=arms,
        metrics=dict(
            by_arm=choices,
            workers=len(rows),
            terminal_frontier_verified=bool(proof),
            repeated_worker_wall_s=sum(r["worker_wall_s"] or 0 for r in rows),
            repeated_worker_cpu_s=sum(r.get("worker", {}).get("cpu_s", 0) for r in rows),
        ),
    )
    validate_result(out)
    return dict(
        id=sequence["id"],
        recording=sequence["recording"],
        condition=sequence["condition"],
        method=METHOD,
        result=out,
        **{k: terminal[k] for k in BIND},
    )


def scored(row, truth, signed):
    result = row["result"]
    for arm in ARMS:
        a = result.get("arms", {}).get(arm, {})
        detail = result["metrics"].get("by_arm", {}).get(arm, {})
        elapsed = detail.get("elapsed_host_s")
        terminal_elapsed = detail.get("terminal_elapsed_host_s")
        early = detail.get("checkpoint", 300) < 300
        yield dict(
            id=row["id"],
            recording=row.get("recording", row["id"]),
            condition=row["condition"],
            signed_tile_clearance_km=signed,
            method=row["method"],
            arm=arm,
            status=detail.get("worker_status", result["status"]),
            reason=detail.get("decision", result.get("reason")),
            checkpoint=detail.get("checkpoint"),
            published=a.get("latlon") is not None,
            error_km=distance_km(a.get("latlon"), truth),
            forced_error_km=distance_km(a.get("forced_latlon"), truth),
            rf_rms_hz=a.get("rf_rms_hz"),
            worker_wall_s=row.get("worker_wall_s"),
            elapsed_host_s=elapsed[1] if elapsed else None,
            terminal_elapsed_host_s=terminal_elapsed[1] if terminal_elapsed else None,
            elapsed_saved_s=terminal_elapsed[1] - elapsed[1]
            if elapsed and terminal_elapsed
            else None,
            early=early and a.get("latlon") is not None,
            repeated_worker_wall_s=result["metrics"].get("repeated_worker_wall_s"),
            repeated_worker_cpu_s=result["metrics"].get("repeated_worker_cpu_s"),
        )


def summary(scored):
    groups = defaultdict(list)
    for r in scored:
        groups["/".join(r[k] for k in ("condition", "method", "arm"))].append(r)
    totals = {}
    for key, rows in groups.items():
        publications = [r for r in rows if r["published"]]
        totals[key] = dict(
            attempted=len(rows),
            published=len(publications),
            statuses=dict(Counter(r["status"] for r in rows)),
            within_1km=sum(r["error_km"] is not None and r["error_km"] <= 1 for r in rows),
            early=sum(r["early"] for r in rows),
            checkpoints=dict(Counter(str(r["checkpoint"]) for r in rows)),
            **{
                k: distribution(r[k] for r in rows)
                for k in (
                    "error_km",
                    "forced_error_km",
                    "rf_rms_hz",
                    "worker_wall_s",
                    "repeated_worker_wall_s",
                    "repeated_worker_cpu_s",
                )
            },
            published_scenario_time_s=distribution(r["elapsed_host_s"] for r in publications),
            early_scenario_gain_s=distribution(
                r["elapsed_saved_s"] for r in publications if r["early"]
            ),
        )
    return totals


def main(report):
    seal = full.read(report / "prediction-lock.json")
    raw = report / "raw.jsonl.gz"
    assert (
        full.checksum(raw) == seal["raw_sha256"]
        and full.checksum(report / "plan.json") == seal["plan_sha256"]
    )
    records = list(map(json.loads, gzip.decompress(raw.read_bytes()).splitlines()))
    assert len(records) == seal["cases"] == 176
    verify_frontiers(records)
    truth = frozen_truth()
    compact = {
        r["id"]: r for r in full.sealed_rows(full.COMPACT, "roof-lock.json", f"{V5}.jsonl.gz")
    }
    predictions, by_scope, scores = defaultdict(list), defaultdict(list), []
    for bundle in records:
        ident, sid, mode = (bundle[k] for k in ("id", "recording", "condition"))
        choice, terminal = evaluate(bundle), bundle["terminal"]
        tile = terminal["tile"]
        site = truth[sid]
        signed = clearance(site, tile["center"], tile.get("width_km", 25.0))
        if mode != "matched" and signed >= 0:
            raise ValueError("authenticated omitted tile includes the truth")
        by_scope[mode].append(
            dict(
                id=ident,
                recording=sid,
                condition=mode,
                truth=site,
                bindings={k: choice[k] for k in BIND},
            )
        )
        variants = [choice, dict(terminal, method="online-full-terminal", condition=mode)]
        if mode == "matched":
            original = compact[sid]
            assert all(original[k] == choice[k] for k in BIND)
            variants.append(dict(original, condition=mode, method=V5))
        predictions[mode].extend(variants)
        scores.extend(s for r in variants for s in scored(r, site, signed))
    for mode, rows in predictions.items():
        filename, refs = f"{mode}-positions.jsonl.gz", f"{mode}-queries.json"
        write(report / filename, full.compressed_rows(rows))
        save_json(report / refs, dict(queries=by_scope[mode]))
        save_json(
            report / f"{mode}-figure-lock.json",
            dict(
                cases=[r["id"] for r in by_scope[mode]],
                files={k: full.checksum(report / k) for k in (filename, refs)},
            ),
        )
    paired = []
    matched = {(r["id"], r["arm"], r["method"]): r for r in scores if r["condition"] == "matched"}
    for cmp in MAIN[1:]:
        for arm in ARMS:
            values = []
            for ident in compact:
                x, y = matched[ident, arm, METHOD], matched[ident, arm, cmp]
                if x["published"] and y["published"]:
                    values.append((x, y))
            paired.append(
                dict(
                    ref=cmp,
                    arm=arm,
                    n=len(values),
                    positional_change_km=distribution(
                        a["error_km"] - b["error_km"] for a, b in values
                    ),
                    rf_change_hz=distribution(
                        a["rf_rms_hz"] - b["rf_rms_hz"]
                        for a, b in values
                        if a["rf_rms_hz"] is not None and b["rf_rms_hz"] is not None
                    ),
                )
            )
    save_json(
        report / "scores.json",
        dict(
            rows=scores,
            totals=summary(scores),
            paired=paired,
            measured=seal,
            actual_worker_counts=dict(Counter(len(r["rows"]) for r in records)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=full.OUT)
    main(local_output(parser.parse_args().report))
