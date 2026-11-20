"""Score the sealed continental compact-edge replay and its exact comparators."""

import argparse
import gzip
from collections import Counter
from pathlib import Path

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km, distribution
from . import edge_holdouts as trial
from . import screening_figures as standard
from . import transfer_budget_results as common
from .fresh_scenes import _read, _sha
from .native_joint_full_results import roi_margin

ARCHIVE = "chart-positions.jsonl.gz"
STOCK = "v5_secant_transfer_stock"
QUERIES = "figure-queries.json"
NAMES = {
    "original": "Containing tile · center offer",
    "near-inside": "True site just inside edge",
    "near-outside": "True site just outside edge",
    "far-outside": "Far omitted tile",
}


def stock_for(scientific, separate):
    """An abstention never stands in for an unfinished stock fit."""
    if separate is not None:
        if not common.matches(scientific, separate):
            raise ValueError("full stock request does not match the guarded fit")
        return dict(separate, method=STOCK, comparison="independent_worker")
    if scientific["result"]["status"] == "ok":
        return dict(scientific, method=STOCK, comparison="exact_endpoint_shadow", wall_s=None)
    missing = trial.worker.compact.portable_v5.unavailable("stock receiver was not run")
    return dict(scientific, method=STOCK, comparison="not_run", result=missing, wall_s=None)


def selection(output):
    common.sealed(output)
    recorded = _read(output / "predictions.json")
    plan = _read(output / "requests.json")
    receipt = {(row["id"], row["mode"]): row for row in plan}
    index = {(row["id"], row["mode"]): row for row in recorded}
    if len(receipt) != 15 or len(index) != len(recorded) or index.keys() != receipt.keys():
        raise ValueError("recorded numerical roster differs from the sealed plan")
    if any(not common.matches(row, receipt[key]) for key, row in index.items()):
        raise ValueError("matched offer or input differs from the locked request")
    return index


def targets(output, observed):
    committed = _read(output / "input-lock.json")
    captures = _read(output / "public-captures.json")
    truth = _read(output / "released-labels.json")
    if len(captures) != 3 or captures.keys() != truth.keys():
        raise ValueError("expected the three independent sealed sites")
    for capture in captures:
        for folder, panel in (("public", captures), ("private", truth)):
            digest = trial.INPUTS.cold._sha(encoded(panel[capture]) + b"\n")
            if committed[f"{folder}/{capture}.json"] != digest:
                raise ValueError("released inputs or target material differs from its commitment")
        native = committed[f"public/{capture}.native.json"]
        if native != captures[capture]["packet_sha256"] or any(
            row["native_sha256"] != native
            for row in observed.values()
            if row["capture_id"] == capture
        ):
            raise ValueError("native inputs differ from the bound capture")
    indexed = {
        ident: dict(target, role=role, capture_id=capture)
        for capture, target in truth.items()
        for ident, role in target["roles"].items()
    }
    if len(indexed) != 12 or set(indexed) != {key[0] for key in observed}:
        raise ValueError("every recorded offer needs an authenticated scorer target")
    return indexed


def endpoints(observed, truth):
    rows, compact, queries = [], [], []
    latitudes = {t["capture_id"]: t["location"][0] for t in truth.values()}
    for capture, site in enumerate(sorted(latitudes, key=latitudes.get, reverse=True), 1):
        ident_by_role = {t["role"]: k for k, t in truth.items() if t["capture_id"] == site}
        for role in trial.ROLES:
            ident = ident_by_role[role]
            original = observed[ident, "gate"]
            control = stock_for(original, observed.get((ident, "control")))
            terminal = original.get("terminal_result", original["result"])
            if terminal != trial.edge.guard(original["result"], original["tile"]):
                raise ValueError("stored terminal answer differs from the frozen endpoint rule")
            candidate = dict(original, method=trial.METHOD, result=terminal, comparison="live_gate")
            target, tile = truth[ident]["location"], original["tile"]
            queries.append(
                dict(
                    id=ident,
                    recording=f"Site {capture}",
                    truth=target,
                    condition=NAMES[role],
                    bindings={key: original[key] for key in common.FIELDS},
                )
            )
            for record in (candidate, control):
                compact.append(record)
                result = record["result"]
                initial = next((r for r in record["trace"] if r["stage"] == "initial_evidence"), {})
                for arm in ARMS:
                    position = result.get("arms", {}).get(arm, {})
                    fix, forced = position.get("latlon"), position.get("forced_latlon")
                    endpoint = fix if fix is not None else forced
                    rows.append(
                        dict(
                            id=ident,
                            site=site,
                            label=f"Site {capture}",
                            role=role,
                            arm=arm,
                            method=record["method"],
                            comparison=record["comparison"],
                            status=result["status"],
                            reason=result.get("reason"),
                            native=record["native_sha256"],
                            position_error_km=distance_km(fix, target),
                            forced_error_km=distance_km(forced, target),
                            margin_km=roi_margin(target, tile),
                            solution_margin_km=trial.edge.margin(endpoint, tile)
                            if endpoint
                            else None,
                            rf_rms_hz=position.get("rf_rms_hz"),
                            wall_s=record["wall_s"],
                            initial_pass_fraction=(
                                initial["accepted_points"] / initial["tracked_points"]
                                if initial.get("tracked_points")
                                else None
                            ),
                            false_publication=fix is not None and role.endswith("outside"),
                        )
                    )
    return rows, compact, queries


def groups(rows):
    output = []
    for method in (trial.METHOD, STOCK):
        for arm in ARMS:
            for role in trial.ROLES:
                values = [
                    r for r in rows if (r["method"], r["arm"], r["role"]) == (method, arm, role)
                ]
                output.append(
                    dict(
                        method=method,
                        arm=arm,
                        role=role,
                        attempts=len(values),
                        statuses=dict(Counter(r["status"] for r in values)),
                        position=distribution(r["position_error_km"] for r in values),
                        forced=distribution(r["forced_error_km"] for r in values),
                        conditional_rf=distribution(r["rf_rms_hz"] for r in values),
                        comparisons=dict(Counter(r["comparison"] for r in values)),
                        false_publications=sum(r["false_publication"] for r in values),
                    )
                )
    return output


def export(output):
    observed = selection(output)
    rows, comparisons, queries = endpoints(observed, targets(output, observed))
    save_json(output / "scores.json", dict(rows=rows, groups=groups(rows)))
    write(
        output / ARCHIVE, gzip.compress(b"".join(encoded(r) + b"\n" for r in comparisons), mtime=0)
    )
    save_json(output / QUERIES, dict(queries=queries))
    proof = ("prediction-lock.json", "input-lock.json", "source-lock.json", "released-labels.json")
    save_json(
        output / "figure-lock.json",
        dict(
            files={name: _sha(output / name) for name in (*proof, ARCHIVE, QUERIES)},
            cases=[q["id"] for q in queries],
        ),
    )
    save_json(
        output / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="compact-edge-three-latitudes",
                    method=trial.METHOD,
                    scope="transfer",
                    cases="sealed",
                    title="Frozen compact edge policy across three new simulated sites",
                    caption="Same native factors, offered tiles and causal history. "
                    "Stock far offers ran independently. The other stock endpoints are the "
                    "identical full-fit endpoints when available.",
                    queries=QUERIES,
                    seal="figure-lock.json",
                    provenance=list(proof),
                    series=[
                        dict(
                            key="candidate",
                            label="Frozen support + 20 m interior",
                            file=ARCHIVE,
                            value=trial.METHOD,
                            forced_label="Guarded endpoint · diagnostic only",
                        ),
                        dict(
                            key="stock",
                            label="Stock compact secant",
                            file=ARCHIVE,
                            value=STOCK,
                            match=list(common.FIELDS),
                        ),
                    ],
                )
            ],
        ),
    )
    standard.generate(output / "figures", evidence=output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=trial.REPORT)
    args = parser.parse_args()
    export(args.out)
