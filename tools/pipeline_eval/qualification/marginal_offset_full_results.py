"""Score full fixed-offset replay with publication and common-fix denominators."""

import argparse
import math
from collections import Counter
from pathlib import Path

from ..__main__ import local_output, save_json
from ..scoring import ARMS, distance_km, distribution
from . import marginal_offset_full as trial
from . import screening_figures as figures
from .marginal_offset_results import _rows, score
from .phase_confirmation import _read, digest
from .prefix_figures import csv_file
from .secant_full import _verify_files

METHODS = (trial.small.variant.METHOD, trial.small.variant.STOCK)
THRESHOLDS = (0.25, 0.5, 1, 2, 5, 10)
COMPLETE = {"ok", "withheld"}
PANELS = {
    "roof": ("Marginal offsets on all 135 roof recordings", {"scope": "roof"}),
    "unseen": (
        "Marginal offsets on 125 new roof recordings",
        {"scope": "roof", "membership": "unseen"},
    ),
    "diagnostic": (
        "Marginal offsets on four prior diagnostic cases",
        {"scope": "roof", "membership": "diagnostic"},
    ),
    "prior-salted": (
        "Marginal offsets on six prior salted cases",
        {"scope": "roof", "membership": "confirmation"},
    ),
    "omitted": ("Marginal offsets on nine historical omissions", {"scope": "omitted"}),
}


def matches(row, condition):
    return all(row[key] == value for key, value in condition.items())


def quantile_with_nonpublications(errors, attempts, probability):
    """Use null for a quantile which no finite error threshold can reach."""
    rank = math.ceil(attempts * probability)
    return errors[rank - 1] if 0 < rank <= len(errors) else None


def describe(rows):
    def values(key):
        return [row[key] for row in rows if row[key] is not None]

    errors, attempted = sorted(values("error_km")), len(rows)
    within = {f"{k:g}": sum(v <= k for v in errors) for k in THRESHOLDS}
    return dict(
        attempted=attempted,
        statuses=dict(Counter(row["status"] for row in rows)),
        reasons=dict(Counter(row["reason"] or "published" for row in rows)),
        published=len(errors),
        published_error_km=distribution(errors),
        forced_error_km=distribution(values("forced_error_km")),
        all_attempts_within_km=within,
        all_attempts_fraction_within_km={
            k: v / attempted if attempted else None for k, v in within.items()
        },
        all_attempts_error_km={
            key: quantile_with_nonpublications(errors, attempted, p)
            for key, p in (("p50", 0.5), ("p95", 0.95), ("worst", 1.0))
        },
        frequency={
            key: distribution(values(key))
            for key in (
                "final_raw_rms_hz",
                "held_raw_rms_hz",
                "held_marginal_loss_per_point",
                "held_relative_logdet_per_point",
                "held_quadratic_and_phase_prior_per_point",
            )
        },
        geometry_radius_km=distribution(values("geometry_radius_km")),
    )


def compare(pairs):
    common, scores = [], []
    outcomes = Counter()
    for first, second in pairs:
        a, b = first["error_km"], second["error_km"]
        if a is not None and b is not None:
            common.append(first["id"])
            scores.append((a, b))
            outcomes["both"] += 1
        elif a is not None:
            outcomes["offset_only"] += 1
        elif b is not None:
            outcomes["zero_only"] += 1
        else:
            outcomes["neither"] += 1
    return dict(
        matched_publication_counts=dict(outcomes),
        common_fix_ids=common,
        common_fix_error_km={
            method: distribution([pair[m] for pair in scores]) for m, method in enumerate(METHODS)
        },
        common_fix_paired_error_delta_km=distribution([a - b for a, b in scores]),
        all_attempts={
            method: describe([pair[m] for pair in pairs]) for m, method in enumerate(METHODS)
        },
    )


def audit(a, b):
    if a["scope"] != b["scope"] or a["membership"] != b["membership"]:
        raise ValueError(f"{a['id']} differs from its frozen cohort")
    keys = (*trial.small.BINDINGS[:3], "tile")
    if any(a[key] != b[key] for key in keys):
        raise ValueError(f"{a['id']} used an unmatched mixture of native inputs")
    if any(row["result"]["status"] not in COMPLETE for row in (a, b)):
        return False
    if not a.get("observation_sha256") or a["observation_sha256"] != b["observation_sha256"]:
        raise ValueError(f"{a['id']} changed the frozen Graph")
    if a["cpu"] != b["cpu"]:
        raise ValueError(f"{a['id']} pair used differing CPU affinity")
    selections = [r["result"]["metrics"]["offset_study"] for r in (a, b)]
    if any(selections[0].get(k) != selections[1].get(k) for k in trial.small.OWNERSHIP):
        raise ValueError(f"{a['id']} changed held, training or final ownership")
    if any(s.get("final_c0_ownership") != s.get("final_fitted_c_ownership") for s in selections):
        raise ValueError(f"{a['id']} changed its owners or aliases across calibration settings")
    return True


def annotate(row, truth, arm, audited):
    result = score(row, truth, arm)
    held = row["result"]["metrics"].get("held_by_arm", {}).get(arm, {})
    return dict(
        result,
        scope=row["scope"],
        membership=row["membership"],
        dataset=row["recording"].split("-", maxsplit=1)[0],
        pair_graph_owner_match=audited,
        held_relative_logdet_per_point=held.get("held_relative_logdet_per_point"),
        held_quadratic_and_phase_prior_per_point=held.get(
            "held_quadratic_and_phase_prior_per_point"
        ),
        worker_cpu_s=row.get("worker", {}).get("cpu_s"),
        worker_wall_s=row.get("worker_wall_s"),
    )


def prior_replication(pairs):
    earlier = trial.small.REPORT
    receipt = _read(earlier / "prediction-lock.json")
    _verify_files(earlier, receipt["files"])
    expected = [_rows(earlier / name) for name in trial.small.FILES]
    same_decision = 0
    deltas = []
    for ident in receipt["cases"]:
        for now, archive in zip(pairs[ident], expected, strict=True):
            reference = archive[ident]
            if any(now.get(key) != reference.get(key) for key in trial.small.BINDINGS):
                raise ValueError(f"{ident} fresh replay differs from the earlier input binding")
            a, b = now["result"], reference["result"]
            same_decision += (a["status"], a["reason"]) == (b["status"], b["reason"])
            deltas.extend(
                distance_km(
                    a["arms"][arm].get("forced_latlon"), b["arms"][arm].get("forced_latlon")
                )
                for arm in ARMS
            )
    return dict(
        cases=len(receipt["cases"]),
        decision_matches=same_decision,
        scorable_arms=sum(d is not None for d in deltas),
        largest_endpoint_shift_km=max((d for d in deltas if d is not None), default=None),
    )


def make_charts(report, plan, lock, pairs, omissions):
    file_names = ("prediction-lock.json", "summary.json", "per-recording.csv")
    common = lock["files"] | {name: digest(report / name) for name in file_names}
    descriptors = []
    for group, (title, selector) in PANELS.items():
        cases = [q["id"] for q in plan if matches(q, selector)]
        roof = group != "omitted"
        match_keys = list(trial.small.BINDINGS[:3])
        if all(all(r.get("observation_sha256") for r in pairs[ident]) for ident in cases):
            match_keys.append("observation_sha256")
        candidate = dict(
            key="one" if roof else "candidate",
            label="Marginal offset · 1000 Hz",
            file=trial.small.FILES[0],
            value=METHODS[0],
            where=selector,
        )
        control = dict(
            key="stock",
            label="Fresh matched zero-offset fit",
            file=trial.small.FILES[1],
            value=METHODS[1],
            where=selector,
            match=match_keys,
        )
        spec = dict(
            id=f"marginal_full-{group}",
            method=METHODS[0],
            scope="roof" if roof else "transfer",
            title=title,
            cases=cases,
            seal=f"{group}-figure-lock.json",
            caption="Both models reuse the same Graph tracks, selected orbits and integer aliases.",
            series=[candidate, control],
            provenance=["summary.json", "source-lock.json"],
        )
        files = dict(common)
        if not roof:
            name = "omitted-queries.json"
            queries = []
            for ident in cases:
                one = pairs[ident][0]
                queries.append(
                    dict(
                        id=ident,
                        recording=one["recording"],
                        truth=omissions[ident]["truth"],
                        condition="unseen" if one["membership"] == "unseen" else "prior",
                        bindings={key: one[key] for key in match_keys},
                    )
                )
            save_json(report / name, dict(queries=queries))
            files[name] = digest(report / name)
            spec.update(
                queries=name,
                condition_labels=dict(
                    prior="Three prior offset-test omissions",
                    unseen="Six new offset-test omissions",
                ),
            )
        save_json(report / spec["seal"], dict(cases=cases, files=files))
        figures._chart(report, spec)
        descriptors.append(spec)
    save_json(report / "figures.json", dict(version=1, charts=descriptors))


def publish(report):
    report = local_output(report)
    lock = _read(report / "prediction-lock.json")
    _verify_files(report, lock["files"])
    plan = _read(report / "plan.json")["cases"]
    a, b = (_rows(report / name) for name in trial.small.FILES)
    if list(a) != list(b) or list(a) != lock["cases"] or list(a) != [q["id"] for q in plan]:
        raise ValueError("full predictions did not preserve the exact scheduled offers")
    refs, _ = figures.shared._frozen_roof()
    prior = trial.small.full.REPORT
    original = _read(prior / "omitted-figure-lock.json")
    _verify_files(prior, original["files"])
    omissions = {q["id"]: q for q in _read(prior / "omitted-queries.json")["queries"]}
    pairs = {ident: (a[ident], b[ident]) for ident in lock["cases"]}
    checked, rows = 0, {}
    for query in plan:
        ident = query["id"]
        pair = pairs[ident]
        audited = audit(*pair)
        checked += audited
        reference = refs[query["recording"]] if query["scope"] == "roof" else omissions[ident]
        if query["scope"] == "omitted" and any(
            r.get(k, v) != v for r in pair for k, v in reference["bindings"].items()
        ):
            raise ValueError(f"{ident} omitted query input differs from its score authority")
        rows[ident] = {
            arm: tuple(annotate(r, reference["truth"], arm, audited) for r in pair) for arm in ARMS
        }
    csv_file(
        report / "per-recording.csv",
        [r for arms in rows.values() for pair in arms.values() for r in pair],
    )
    selectors = {k: where for k, (_, where) in PANELS.items()}
    selectors.update(
        {
            f"unseen-{ds}": {"scope": "roof", "membership": "unseen", "dataset": ds}
            for ds in ("DS26", "DS29")
        }
    )
    selectors["omitted-prior"] = dict(scope="omitted", membership="omitted")
    selectors["omitted-unseen"] = dict(scope="omitted", membership="unseen")
    groups = {
        key: {
            arm: compare([arms[arm] for arms in rows.values() if matches(arms[arm][0], where)])
            for arm in ARMS
        }
        for key, where in selectors.items()
    }
    save_json(
        report / "summary.json",
        dict(
            scheduled_pairs=len(plan),
            complete_fresh_pairs=checked,
            pair_graph_owner_match=checked,
            prior_replication=prior_replication(pairs),
            all_attempt_quantiles="Null if a finite error threshold cannot reach the quantile",
            groups=groups,
        ),
    )
    make_charts(report, plan, lock, pairs, omissions)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=trial.REPORT, type=Path)
    publish(parser.parse_args().report)
