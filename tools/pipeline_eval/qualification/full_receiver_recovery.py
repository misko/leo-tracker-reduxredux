"""Compare sealed receiver decisions on the same complete 135-recording roof panel."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from .. import corpus
from ..__main__ import local_output, read_predictions, save_json
from ..scoring import ARMS, ROLES, distance_km, distribution, thresholds, validate_result
from ..variants import late_preflight
from . import clock_offset_results as clocks
from . import full_receiver_comparison as common
from . import full_receiver_refinement as refinement
from . import late_preflight_results as preflight
from . import native_agreement_cascade_eval as cascade
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

REPORT = common.SCREEN / "recovery/full-receivers"
CHART = "receiver_recovery-roof135"
METHOD = "receiver_recovery"
CLOCK = clocks.model.METHOD
CASCADE = cascade.gate.METHOD
PREFLIGHT = preflight.trial.METHOD
SERIES = (
    (common.COMPACT, "Compact v5 secant", "one"),
    (CLOCK, "Native clock + offset OU", "one_native_factors"),
    (CASCADE, "Cascade · archived routing", "stock"),
    (PREFLIGHT, "RF preflight · archive replay", "all_visits"),
)
ORIGINS = {
    common.COMPACT: "matched_compact_replays",
    CLOCK: "measured_complete_native_replay",
    CASCADE: "archived_route_with_matched_compact_fallback",
    PREFLIGHT: "archived_stage_decision_replay",
    **dict.fromkeys(ROLES, "original_v5_execution"),
}
POSITION = "positions.jsonl.gz"
MATCH = ("native_sha256", "catalog_sha256", "tile")
FILES = (POSITION, "sources.json", "summary.json", "summary.csv", "scores.csv", "pairings.json")


def links(folder, name, lock, prediction):
    return dict(
        receipt=str((folder / name).relative_to(common.ROOT)),
        receipt_sha256=common.sha(folder / name),
        prediction=str((folder / prediction).relative_to(common.ROOT)),
        prediction_sha256=lock["files"][prediction],
        files=lock["files"],
    )


def selected(path, method, *, cohort=None):
    with gzip.open(path, "rt") as stream:
        chosen = [
            row
            for row in map(json.loads, stream)
            if row["method"] == method and (cohort is None or row.get("cohort") == cohort)
        ]
    result = {row["id"]: row for row in chosen}
    common.roster_matches([r["id"] for r in chosen], result, method)
    for row in result.values():
        validate_result(row["result"])
    return result


def require_matched(records, inputs, method):
    common.roster_matches(records, inputs, method)
    for ident, row in records.items():
        source = inputs[ident]
        common.require_fields(
            row,
            dict(
                id=ident,
                method=method,
                native_sha256=source["native"]["sha256"],
                catalog_sha256=source["catalog"]["sha256"],
                tile=source["regions"][0],
            ),
        )
        result = row["result"]
        validate_result(result)
        if (
            result["status"] not in ("ok", "withheld")
            or set(result["arms"]) != set(ARMS)
            or result["metrics"].get("position_attempted") is False
        ):
            raise ValueError(f"{ident} {method} does not contain a complete paired decision")


def clocks_on_roof(inputs, smooth, compact_link):
    folder = clocks.trial.REPORT / "full"
    primary = "prediction-lock.json"
    lock = common.seal(folder, primary, (POSITION, "plan.json"))
    plan = common.read(folder / "plan.json")
    common.require_fields(
        plan,
        dict(
            study_stage="full",
            compact_reference_receipt_sha256=compact_link["receipt_sha256"],
            formula_sha256=common.sha(clocks.trial.REPORT / "PROTOCOL.md"),
        ),
    )
    common.secant_full._verify_files(common.ROOT, plan["implementation"])
    containers = read_predictions(folder / POSITION)
    common.roster_matches(lock["cases"], containers, CLOCK)
    common.roster_matches([q["id"] for q in plan["cases"]], containers, CLOCK)
    run = lock["run"]
    statuses = Counter(r["result"]["status"] for r in containers.values())
    if (
        run["statuses"] != statuses
        or run["attempted"] != len(containers)
        or run["scheduled"] != len(containers)
        or not 0 < run["wall_s"] <= plan["wall_cap_s"]
    ):
        raise ValueError("clock/offset run receipt differs from the full native replay")
    roof_lock_name = "all_roof-figure-lock.json"
    roof_lock = common.seal(folder, roof_lock_name, (clocks.ALL,))
    common.require_fields(roof_lock, {"plan_sha256": lock["files"]["plan.json"]})
    common.roster_matches(roof_lock["cases"], inputs, CLOCK)
    published = selected(folder / clocks.ALL, CLOCK, cohort="roof")
    expected = clocks._models(containers, plan["challenge"])[CLOCK]
    common.roster_matches(published, inputs, CLOCK)
    jobs = {q["id"]: q for q in plan["cases"] if q["cohort"] == "roof"}
    common.roster_matches(jobs, inputs, CLOCK)
    for ident, row in published.items():
        packet, _ = common.native_lean_eval.request(inputs[ident], "native")
        common.require_fields(jobs[ident], dict(recording=ident, packet=packet))
        if row != expected[ident]:
            raise ValueError(f"{ident} flattened clock/offset endpoint differs from its archive")
        refinement.verify_native(ident, row, smooth[ident], CLOCK, "nuisance_backend")
    return published, dict(
        origin=ORIGINS[CLOCK],
        run=links(folder, primary, lock, POSITION),
        chart=links(folder, roof_lock_name, roof_lock, clocks.ALL),
    )


def routed_on_roof(inputs, smooth, anchors, compact, parent_links):
    folder = cascade.REPORT
    name = "roof-figure-lock.json"
    lock = common.seal(folder, name, (POSITION, "sources.json", "routing.json"))
    common.roster_matches(lock["cases"], inputs, CASCADE)
    sources = common.read(folder / "sources.json")
    common.require_fields(
        sources,
        dict(
            parent_links,
            protocol=common.sha(folder / "PROTOCOL.md"),
            router=common.sha(Path(cascade.gate.__file__)),
            evaluator=common.sha(Path(cascade.__file__)),
        ),
    )
    routes = cascade.decisions(smooth, anchors)
    common.require_fields(
        common.read(folder / "routing.json"),
        dict(primary_threshold_km=cascade.gate.LIMIT_KM, decisions=routes),
    )
    published = selected(folder / POSITION, CASCADE, cohort="roof")
    common.roster_matches(published, inputs, CASCADE)
    expected = {r["id"]: r for r in cascade.model(smooth, anchors, compact, routes)}
    if published != expected:
        raise ValueError("archived cascade endpoints disagree with the sealed parents and route")
    return published, dict(
        origin=ORIGINS[CASCADE],
        chart=links(folder, name, lock, POSITION),
        routes=dict(Counter(r["route"] for r in routes.values())),
        agreement_ceiling_km=cascade.gate.LIMIT_KM,
    )


def preflight_on_roof(inputs, refs, compact_link):
    trial = preflight.trial
    folder = trial.REPORT
    seal_name = "roof-lock.json"
    seal = common.seal(folder, seal_name, preflight.ARTIFACTS)
    common.roster_matches(seal["cases"], inputs, PREFLIGHT)
    lock = common.read(folder / "predecision-lock.json")
    originals_path = common.secant_full.REPORT / "original-v5-inputs.json"
    common.require_fields(
        lock,
        dict(
            original_v5_inputs_sha256=common.sha(originals_path),
            original_v5_run_receipt_sha256=compact_link["receipt_sha256"],
            prior_eligibility_sha256=common.sha(trial.PRIOR),
        ),
    )
    common.secant_full._verify_files(common.ROOT, lock["source_sha256"])
    originals = common.read(originals_path)
    eligibility = {r["id"]: r for r in common.read(trial.PRIOR)["rows"]}
    common.roster_matches(lock["cases"], inputs, PREFLIGHT)
    blind_bytes = gzip.decompress((folder / "predecision.json.gz").read_bytes())
    if corpus._sha(blind_bytes) != lock["files"]["predecision.json"]:
        raise ValueError("preflight trace differs from its predecision seal")
    blind = json.loads(blind_bytes)
    with gzip.open(folder / "outcomes.json.gz", "rt") as stream:
        outcomes = json.load(stream)
    for rows in (blind, outcomes):
        common.roster_matches([r["id"] for r in rows], inputs, PREFLIGHT)
    outcomes = {r["id"]: r for r in outcomes}
    published = selected(folder / POSITION, PREFLIGHT)
    common.roster_matches(published, inputs, PREFLIGHT)
    for row in blind:
        ident = row["id"]
        common.require_fields(
            row,
            dict(originals[ident]["baseline"], archive_sha256=eligibility[ident]["archive_sha256"]),
        )
        go, reason, families = late_preflight.preflight(row["features"])
        common.require_fields(
            row["preflight"], dict(run=go, reason=reason, plausible=list(families))
        )
        outcome = outcomes[ident]
        if published[ident] != preflight.replay_packet(row, outcome)[0]:
            raise ValueError(f"{ident} preflight endpoint differs from the sealed archive replay")
        for arm in ARMS:
            baseline = refs[ident]["reference"]["baseline"][arm]["latlon"]
            final = outcome["stages"][arm]["final"]["latlon"]
            if distance_km(final, baseline) != 0:
                raise ValueError(f"{ident} preflight original full-v5 endpoint differs")
    return published, dict(
        origin=ORIGINS[PREFLIGHT],
        chart=links(folder, seal_name, seal, POSITION),
        bypassed=sum(not r["preflight"]["run"] for r in blind),
    )


def summarize(rows, refs):
    groups = {}
    for row in rows:
        key = row["method"], row["arm"]
        by_id = groups.setdefault(key, {})
        if row["id"] in by_id:
            raise ValueError(f"{row['id']} duplicated a method and calibration arm")
        by_id[row["id"]] = row
    order = (*ROLES, *(m for m, _, _ in SERIES))
    summary = []
    pairings = {}
    for method in order:
        paired = {arm: groups[method, arm] for arm in ARMS}
        for arm, by_id in paired.items():
            common.roster_matches(by_id, refs, f"{method} {arm}")
        accepted = {
            arm: {i for i, row in by_id.items() if row["within_v5_10pct"]}
            for arm, by_id in paired.items()
        }
        fixed = {
            arm: {i for i, row in by_id.items() if row["error_km"] is not None}
            for arm, by_id in paired.items()
        }
        both = set.intersection(*fixed.values())
        both_gate = set.intersection(*accepted.values())
        pairings[method] = dict(
            fixed_both=sorted(both),
            within_10pct_both=sorted(both_gate),
            published={arm: sorted(ids) for arm, ids in fixed.items()},
            within_10pct={arm: sorted(ids) for arm, ids in accepted.items()},
        )
        for arm, by_id in paired.items():
            errors = [r["error_km"] for r in by_id.values()]
            dist = distribution(errors)
            within = thresholds(errors)
            rf = distribution(r["conditional_rms_hz"] for r in by_id.values())
            summary.append(
                dict(
                    method=method,
                    arm=arm,
                    evidence_origin=ORIGINS[method],
                    offered=len(refs),
                    fixes=len(fixed[arm]),
                    within_1km=within["1"],
                    within_2km=within["2"],
                    within_5km=within["5"],
                    median_km=dist["p50"],
                    p95_km=dist["p95"],
                    within_10pct_of_paired_v5=len(accepted[arm]),
                    within_10pct_both_arms=len(both_gate),
                    fixes_both_arms=len(both),
                    conditional_rms_median_hz=rf["p50"],
                    conditional_rms_count=rf["n"],
                )
            )
    return summary, pairings


def build(output):
    refs, inventory = _frozen_roof()
    inputs = common.full_roster(refs, inventory)
    compact, compact_link = common.compact_predictions(inputs, refs, audit_archive=True)
    natives, native_links = common.native_predictions(inputs)
    smooth = natives[common.CLOCK]
    anchors, anchors_link = refinement.anchor_predictions(inputs, natives[common.JOINT])
    clock, clock_link = clocks_on_roof(inputs, smooth, compact_link)
    route, route_link = routed_on_roof(
        inputs,
        smooth,
        anchors,
        compact,
        dict(
            native_clock=native_links[common.CLOCK],
            curve_anchors=anchors_link,
            compact=compact_link,
        ),
    )
    rf, rf_link = preflight_on_roof(inputs, refs, compact_link)
    methods = {common.COMPACT: compact, CLOCK: clock, CASCADE: route, PREFLIGHT: rf}
    for method, rows in methods.items():
        require_matched(rows, inputs, method)
    pack(output / POSITION, [r for group in methods.values() for r in group.values()])
    rows = list(refinement.scores(refs, methods))
    for row in rows:
        row["evidence_origin"] = ORIGINS[row["method"]]
        if row["recorded_wall_s"] is None:
            row["timing_origin"] = None
    summary, pairings = summarize(rows, refs)
    csv_file(output / "scores.csv", rows)
    csv_file(output / "summary.csv", summary)
    save_json(output / "summary.json", dict(corpus=dict(DS26=127, DS29=8), methods=summary))
    save_json(output / "pairings.json", pairings)
    original = common.secant_full.REPORT / "original-v5-inputs.json"
    original_ref = corpus.FROZEN / "provenance.json"
    save_json(
        output / "sources.json",
        dict(
            methods={
                common.COMPACT: dict(compact_link, origin=ORIGINS[common.COMPACT]),
                CLOCK: clock_link,
                CASCADE: route_link,
                PREFLIGHT: rf_link,
            },
            original_v5=dict(
                roles=ROLES,
                audited_executions=len(inputs) * len(ROLES),
                receipt=compact_link["receipt"],
                receipt_sha256=compact_link["receipt_sha256"],
                bindings=str(original.relative_to(common.ROOT)),
                bindings_sha256=compact_link["files"][original.name],
            ),
            frozen_corpus=dict(
                path=str(original_ref.relative_to(common.ROOT)), sha256=common.sha(original_ref)
            ),
            aggregator_sha256=common.sha(Path(__file__)),
            native_route_sources=dict(clock=native_links[common.CLOCK], anchors=anchors_link),
        ),
    )
    save_json(
        output / "roof-lock.json",
        dict(cases=sorted(refs), files={name: common.sha(output / name) for name in FILES}),
    )
    save_json(
        output / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id=CHART,
                    method=METHOD,
                    scope="roof",
                    cases="roof135",
                    title="Receiver recovery decisions on 135 matched roof recordings",
                    caption="Complete stored GLRT, same causal catalogue and same supplied tile. "
                    "The four original v5 options form the reference range. The cascade uses "
                    "archived routing. RF preflight replays saved late-stage decisions.",
                    seal="roof-lock.json",
                    provenance=list(FILES[1:]),
                    series=[
                        dict(
                            key=key,
                            label=label,
                            file=POSITION,
                            value=method,
                            **({"match": list(MATCH)} if key != "one" else {}),
                        )
                        for method, label, key in SERIES
                    ],
                )
            ],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPORT)
    build(local_output(parser.parse_args().output))
