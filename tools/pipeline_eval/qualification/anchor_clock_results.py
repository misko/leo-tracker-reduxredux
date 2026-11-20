"""Score the same-owner anchor clock and reproduce the independent linear control."""

import argparse
from collections import Counter
from pathlib import Path

from ..__main__ import read_predictions, save_json
from ..scoring import ARMS, distribution, thresholds, validate_result
from ..variants import anchor_clock
from . import anchor_clock_trial as trial
from . import native_joint_full_results as shared

phase = trial.base.phase
ARCHIVE = trial.REPORT.with_name("anchor-full")
LINEAR = "linear-positions.jsonl.gz"
PROSPECTIVE = "prospective-positions.jsonl.gz"
PAIR = ("input_sha256", "native_sha256", "catalog_sha256", "tile", "cohort", "recording")


def verify_archive(plan, candidate):
    path = ARCHIVE / "prediction-lock.json"
    lock = phase._read(path)
    trial.base.base.secant_full._verify_files(ARCHIVE, lock["files"])
    control_plan = phase._read(ARCHIVE / "plan.json")
    if (
        control_plan["source"]["fitter_sha256"] != plan["anchor_clock_source"]["anchor"]
        or control_plan["source"]["prepared_source_lock_sha256"]
        != plan["anchor_clock_source"]["anchor_prepared_source_lock"]
    ):
        raise ValueError("the independent linear archive used a different anchor source")
    archive = read_predictions(ARCHIVE / shared.PREDICTIONS)
    if set(archive) != set(candidate) or set(archive) != set(lock["cases"]):
        raise ValueError("native anchored-clock and historical control rosters differ")
    paired = {}
    for ident, row in candidate.items():
        old = archive[ident]
        if any(row[key] != old[key] for key in PAIR):
            raise ValueError(f"{ident} receiver controls do not share the same native query")
        inside = row.get("linear_result")
        if inside is None:
            continue
        validate_result(inside)
        if (
            row["observation_sha256"] != old.get("observation_sha256")
            or row["counts"] != old["counts"]
        ):
            raise ValueError(f"{ident} peak selection or Graph changed")
        actual = old["result"]
        if any(inside[key] != actual[key] for key in ("status", "reason", "arms")):
            raise ValueError(f"{ident} paired linear control differs from the standalone replay")
        model = "original_fixed_linear_c0_other_family_prefix"
        metrics, linear_metrics = row["result"]["metrics"], inside["metrics"]
        if (
            metrics["anchor_ownership"] != linear_metrics["anchor_ownership"]
            or metrics["anchor_held_model"] != model or linear_metrics["anchor_held_model"] != model
            or metrics.get("anchor_held_rms_hz") != linear_metrics.get("anchor_held_rms_hz")
        ):
            raise ValueError(f"{ident} changed fixed anchors or the original held gate")
        paired[ident] = inside
    return archive, paired, phase.digest(path)


def _scores(rows, candidate, archive, paired, truth, prospective):
    for row in rows:
        ident, arm = row["id"], row["arm"]
        current, historical = candidate[ident], archive[ident]
        result = historical["result"]
        comp = shared.geodata(historical, arm, truth[row["recording"]])
        model = current["result"]["metrics"]
        diagnostics = current.get("held_diagnostic", {}).get(arm, {})
        times = current.get("paired_final_fit_s", {})
        row.update(
            prospective=ident in prospective,
            exact_independent_linear_reproduction=ident in paired,
            anchor_tracks=model.get("anchor_tracks"),
            anchor_orbit_families=model.get("orbit_families"),
            original_anchor_gate_rf_rms_hz=model.get("anchor_held_rms_hz"),
            clock_held_rf_rms_hz=diagnostics.get("clock_rms_hz"),
            linear_held_rf_rms_hz=diagnostics.get("linear_rms_hz"),
            held_points=diagnostics.get("held_points"),
            held_tracks=diagnostics.get("held_tracks"),
            clock_final_fit_s=times.get("clock"),
            linear_final_fit_s=times.get("linear"),
            held_diagnostic_wall_s=current.get("held_diagnostic_wall_s"),
            linear_archive_status=result["status"],
            linear_replay_wall_s=historical["worker_wall_s"],
            **{f"linear_{k}": comp[k]
               for k in ("error_km", "conditional_rms_hz", "forced_error_km")},
        )


def compare(rows):
    output = []
    for cohort in ("roof", "prospective", "omitted"):
        for arm in ARMS:
            group = [
                r for r in rows if r["arm"] == arm and (
                    r["prospective"] if cohort == "prospective" else r["cohort"] == cohort
                )
            ]
            pairs = [
                (r["error_km"], r["linear_error_km"]) for r in group
                if r["error_km"] is not None and r["linear_error_km"] is not None
            ]
            deltas = {}
            for name, left, right in (
                ("in_sample_rf_hz", "conditional_rms_hz", "linear_conditional_rms_hz"),
                ("held_rf_hz", "clock_held_rf_rms_hz", "linear_held_rf_rms_hz"),
                ("final_fit_s", "clock_final_fit_s", "linear_final_fit_s"),
            ):
                values = [r[left] - r[right] for r in group if r[left] is not None
                          and r[right] is not None and (name != "final_fit_s" or r[left] > 0)]
                deltas[name] = dict(
                    lower=sum(v < 0 for v in values), distribution=distribution(values),
                )
            output.append(dict(
                cohort=cohort, arm=arm, scheduled=len(group),
                independent_linear_matches=sum(
                    r["exact_independent_linear_reproduction"] for r in group
                ),
                clock_within_km=thresholds([r["error_km"] for r in group]),
                linear_within_km=thresholds([r["linear_error_km"] for r in group]),
                clock_error_km=distribution(r["error_km"] for r in group),
                linear_error_km=distribution(r["linear_error_km"] for r in group),
                publication_pairs=dict(Counter(
                    f"{r['status']}/{r['linear_archive_status']}" for r in group
                )),
                paired_accuracy=phase._pair_summary(pairs),
                deltas=deltas,
            ))
    return output


def held_ablation(rows):
    zero = {row["id"]: row for row in rows if row["arm"] == "c0"}
    paired = [(zero[r["id"]], r) for r in rows if r["cohort"] == "roof" and r["arm"] == "fitted_c"]
    output = {}
    for method in ("clock", "linear"):
        field = f"{method}_held_rf_rms_hz"
        changes = [
            b[field] - a[field] for a, b in paired
            if a[field] is not None and b[field] is not None
            and a["held_points"] == b["held_points"] and a["held_tracks"] == b["held_tracks"]
        ]
        output[method] = dict(
            n=len(changes), lower=sum(delta < 0 for delta in changes),
            fitted_minus_zero_hz=distribution(changes),
        )
    return output


def chart(output, row_sets, cases, lock, archive_digest, queries):
    candidate, archive = row_sets
    linear = [dict(row, method=anchor_clock.LINEAR) for row in archive.values()]
    linear_sha = shared.pack(output, LINEAR, linear)
    prospective = [candidate[i] for i in cases["prospective"]]
    prospective.extend(dict(archive[i], method=anchor_clock.LINEAR) for i in cases["prospective"])
    prospective_sha = shared.pack(output, PROSPECTIVE, prospective)
    specs = []
    for cohort, ids in cases.items():
        omitted = cohort == "omitted"
        reserved = cohort == "prospective"
        files = (
            {PROSPECTIVE: prospective_sha, "plan.json": lock["files"]["plan.json"]}
            if reserved else lock["files"] | {LINEAR: linear_sha}
        )
        series = []
        for method, key, label, path in (
            (anchor_clock.METHOD, "candidate" if omitted else "one",
             "Shared clock on fixed anchors", shared.PREDICTIONS),
            (anchor_clock.LINEAR, "stock", "Original anchored linear fit", LINEAR),
        ):
            item = dict(key=key, label=label, file=PROSPECTIVE if reserved else path, value=method)
            if not reserved:
                item["where"] = dict(cohort=cohort)
            if key == "stock":
                item["match"] = list(PAIR)
                if all("observation_sha256" in candidate[i] for i in ids):
                    item["match"].append("observation_sha256")
            if omitted:
                item["forced_label"] = f"{label} forced diagnostic"
            series.append(item)
        title = {
            "roof": "Shared clock on anchors across 135 roof recordings",
            "prospective": "Shared clock on six prospective anchor recordings",
            "omitted": "Anchored receiver with the correct tile omitted",
        }[cohort]
        spec = dict(
            id=f"native_anchor_clock-{cohort}", method=anchor_clock.METHOD, title=title,
            scope="transfer" if omitted else "roof", cases=ids,
            caption="Complete native Graph and identical anchored owners and aliases. The original "
            "fixed-linear held selection gate is shared. Any forced positions are diagnostic.",
            seal=f"{cohort}-figure-lock.json",
            source_lock=dict(file="plan.json", digest_key="plan_sha256"), series=series,
        )
        if omitted:
            spec["queries"] = "omitted-queries.json"
            save_json(output / spec["queries"], dict(queries=queries))
            files[spec["queries"]] = phase.digest(output / spec["queries"])
        save_json(output / spec["seal"], dict(
            cases=ids, files=files, plan_sha256=lock["files"]["plan.json"],
            independent_linear_archive_sha256=archive_digest,
        ))
        specs.append(spec)
    save_json(output / "figures.json", dict(version=1, charts=specs))


def score(work, bundle, output):
    shared.seal(
        work, bundle, output, prepare=trial.prepare, method=anchor_clock.METHOD,
        fail=trial.base.failed,
    )
    lock = phase._read(output / "prediction-lock.json")
    plan = phase._read(output / "plan.json")
    candidate = read_predictions(output / shared.PREDICTIONS)
    archive, paired, archive_digest = verify_archive(plan, candidate)
    rows, queries = shared.matched_score_rows(candidate, plan, solver_stage="anchor_pair_backend")
    truth = {
        r["id"]: r["truth"] for panel in ("ds26-common127", "roof16")
        for r in phase.corpus.references(panel)
    }
    _scores(rows, candidate, archive, paired, truth, plan["prospective"])
    shared.csv_file(output / "scores.csv", rows)
    groups = {
        k: [ident for ident, row in candidate.items() if row["cohort"] == k]
        for k in ("roof", "omitted")
    }
    groups["prospective"] = plan["prospective"]
    save_json(output / "summary.json", dict(
        replay=lock["run"], full=shared.summarize(rows), comparisons=compare(rows),
        c_ablation=shared.ablation(rows), independent_linear_matches=len(paired),
        held_c_ablation=held_ablation(rows), archive_sha256=archive_digest,
    ))
    chart(output, (candidate, archive), groups, lock, archive_digest, queries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=trial.WORK)
    parser.add_argument("--bundle", type=Path, default=trial.base.base.BUNDLE)
    parser.add_argument("--output", type=Path, default=trial.REPORT)
    args = parser.parse_args()
    score(args.work, args.bundle, args.output)
