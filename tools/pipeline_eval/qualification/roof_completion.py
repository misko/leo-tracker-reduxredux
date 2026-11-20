"""Rescore the complete DS26 roof cohort from the sealed compact and smooth-clock outputs."""

import argparse
import csv
import gzip
import io
import re
from collections import Counter
from pathlib import Path

from .. import corpus
from ..__main__ import encoded, local_output, read_predictions, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution, thresholds
from .compact_roof_selection import audit_result as audit_compact
from .full_receiver_comparison import read, require_fields, roster_matches, seal, sha
from .prefix_figures import csv_file

SCREEN = corpus.REPO / "reports/2026_11_19_receiver_screening"
STUDY = Path("redesign/roof-selection")
REPORT = SCREEN / STUDY / "comparison"
METHOD = "ds26_roof_completion"
COMPACT = "v5_secant_fit"
NATIVE = "ds26_selection_native_clock"
PARENT = "native_joint_clock_model"
POSITIONS = "positions.jsonl.gz"
PREDICTION_LOCK = "prediction-lock.json"
COMPACT_ARCHIVE = f"{COMPACT}.jsonl.gz"
ORIGINALS = "reports/2026_11_18_v5_blind_comparison/sample-errors.csv"
ORIGINAL_EXPORT = STUDY / "comparison/original-score-source.csv.gz"
PRIOR_COMPACT = (
    ("prior_timing", "position-fit", PREDICTION_LOCK, "secant-positions.jsonl.gz"),
    ("prior_confirmation", "secant-confirmation", "receipt.json", COMPACT_ARCHIVE),
)
RF_KIND = {
    COMPACT: "compact secant cavity conditional RMS",
    NATIVE: "smooth clock arm-fit RMS",
    **dict.fromkeys(ROLES, "archived original v5 report RMS"),
}
STATES = ("published", "withheld", "failed", "timed_out", "unavailable", "unattempted", "missing")


def digest(value):
    return corpus._sha(encoded(value))


def check_digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("invalid SHA-256 binding")


def locked_rows(folder, filename, receipt, cases):
    rows = read_predictions(folder / filename)
    roster_matches(receipt["cases"], cases, str(folder / filename) + " seal")
    roster_matches(rows, cases, str(folder / filename))
    return rows


def input_binding(row, item, method):
    (tile,) = item["regions"]
    require_fields(row, dict(id=item["id"], method=method, tile=tile))
    result = row["result"]
    arms = result.get("arms", {})
    roster_matches(arms, ARMS, f"{item['id']} / {method} arms")
    if result["status"] in ("failed", "timed_out", "unavailable", "missing") and any(
        arm.get("forced_latlon") is not None for arm in arms.values()
    ):
        raise ValueError(f"{item['id']} has a numerical estimate without an observed fit")
    if reason := item.get("unavailable"):
        require_fields(row, dict(input_sha256=None, native_sha256=None, catalog_sha256=None))
        require_fields(result, dict(status="unavailable", reason=reason))
        return
    require_fields(
        row, dict(native_sha256=item["native"]["sha256"], catalog_sha256=item["catalog"]["sha256"])
    )
    if method == COMPACT:
        require_fields(row, dict(frozen_request_sha256=item["request"]["sha256"]))
    check_digest(row["input_sha256"])


def compact_common(screen, cases, inputs):
    folder = screen / "secant-full"
    receipt = seal(
        folder, PREDICTION_LOCK, (COMPACT_ARCHIVE, "orbit_projector.jsonl.gz", "plan.json")
    )
    release = seal(folder, "receipt.json", (PREDICTION_LOCK, "original-v5-inputs.json"))
    plan = read(folder / "plan.json")
    roster_matches(release["cases"], cases, "full 135 compact receipt")
    roster_matches(plan["cases"], cases, "full 135 compact plan")
    require_fields(plan, dict(source_sha256=release["sources"]))
    rows = locked_rows(folder, COMPACT_ARCHIVE, receipt, cases)
    same_boundary = locked_rows(folder, "orbit_projector.jsonl.gz", receipt, cases)
    prior = {}
    for label, study, name, archive in PRIOR_COMPACT:
        source = screen.with_name("2026_11_19_receiver_convergence") / study
        if sha(source / name) != release["prior_seals"][label]:
            raise ValueError(f"the compact {label} receipt has changed")
        locked = seal(source, name, (archive,))
        chosen = [ident for ident in cases if plan["prior_cases"].get(ident) == label]
        prior.update(locked_rows(source, archive, locked, chosen))
    roster_matches(
        [*plan["fresh_cases"], *plan["prior_cases"]], cases, "compact prior/fresh partition"
    )
    for ident, row in rows.items():
        input_binding(row, inputs[ident], COMPACT)
        require_fields(
            row,
            dict(
                source=plan["prior_cases"].get(ident, "fresh_full_panel"),
                source_sha256=plan["source_sha256"],
            ),
        )
        require_fields(
            same_boundary[ident],
            {key: row[key] for key in ("input_sha256", "resolved_request_sha256", "tile")},
        )
        if archived := prior.get(ident):
            require_fields(
                row,
                dict(result=archived["result"], prior_input_sha256=archived["input_sha256"]),
            )
    original = read(folder / "original-v5-inputs.json")
    roster_matches(original, cases, "full 135 original request and execution audit")
    return rows, original


def compact_excluded(folder, cases, inputs, frozen):
    lock = seal(folder, PREDICTION_LOCK, (POSITIONS, "roster.json", "run-receipt.json"))
    score_lock = seal(folder, "score-lock.json", ("original-role-bindings.json",))
    roster_matches(score_lock["cases"], cases, "excluded compact original score lock")
    require_fields(
        score_lock,
        dict(
            prediction_lock_sha256=sha(folder / PREDICTION_LOCK),
            frozen_scores_sha256=frozen["scores.csv"],
            frozen_targets_sha256=frozen["targets.jsonl"],
        ),
    )
    plan = read(folder / "roster.json")
    require_fields(
        plan,
        dict(
            cases=cases,
            frozen_inputs_sha256=frozen["inputs.jsonl"],
            frozen_panels_sha256=frozen["panels.json"],
            wall_cap_s=720,
            worker_cap_s=195,
        ),
    )
    rows = locked_rows(folder, POSITIONS, lock, cases)
    bindings = plan["bindings"]
    roster_matches(bindings, cases, "compact excluded input bindings")
    run = read(folder / "run-receipt.json")
    require_fields(
        run,
        dict(
            scheduled=len(cases),
            claimed=len(run["claims"]),
            eligible=sum(bound["eligible"] for bound in bindings.values()),
            attempted=sum(row["attempted"] is True for row in rows.values()),
            worker_returned=sum(row["worker_returned"] for row in rows.values()),
            status_counts=dict(Counter(row["result"]["status"] for row in rows.values())),
            sources=dict(Counter(row["source"] for row in rows.values())),
        ),
    )
    roster_matches(
        run["claims"],
        [ident for ident, row in rows.items() if row["attempted"] is not False],
        "compact first-budget claimed roster",
    )
    for ident, row in rows.items():
        input_binding(row, inputs[ident], COMPACT)
        audit_compact(row, plan)
        status = row["result"]["status"]
        if status in ("ok", "withheld", "failed", "timed_out"):
            require_fields(
                row,
                dict(
                    attempted=True,
                    worker_returned=status in ("ok", "withheld"),
                    cpu=run["claims"][ident]["cpu"],
                    deadline_s=plan["worker_cap_s"],
                ),
            )
        else:
            require_fields(
                row,
                dict(
                    attempted=None if row["source"] == "unconfirmed_claim" else False,
                    worker_returned=False,
                ),
            )
    return rows, read(folder / "original-role-bindings.json")


def native_results(screen, cases, common, excluded, inputs, frozen, original_score_sha):
    folder = screen / STUDY / "native"
    lock = seal(
        folder,
        "all159-figure-lock.json",
        (POSITIONS, "fresh-lock.json", "original-v5-audit.json", "analysis-sources.json"),
    )
    rows = locked_rows(folder, POSITIONS, lock, cases)
    exclusion = seal(folder, "excluded32-figure-lock.json", ("excluded-positions.jsonl.gz",))
    if locked_rows(folder, "excluded-positions.jsonl.gz", exclusion, excluded) != {
        ident: rows[ident] for ident in excluded
    }:
        raise ValueError("the native excluded export differs from the full normalized archive")
    fresh = seal(folder, "fresh-lock.json", ("fresh-positions.jsonl.gz", "plan.json"))
    raw = locked_rows(folder, "fresh-positions.jsonl.gz", fresh, excluded)
    require_fields(
        fresh,
        dict(
            attempted=sum(r["worker_attempted"] is True for r in raw.values()),
            statuses=dict(Counter(r["result"]["status"] for r in raw.values())),
        ),
    )
    plan = read(folder / "plan.json")
    parent = screen / "factors/native-clock-full"
    parent_lock = seal(parent, PREDICTION_LOCK, (POSITIONS, "plan.json"))
    parent_plan = read(parent / "plan.json")
    old = locked_rows(parent, POSITIONS, parent_lock, [q["id"] for q in parent_plan["cases"]])
    parent_sha = sha(parent / PREDICTION_LOCK)
    require_fields(
        plan,
        dict(
            all159=cases,
            common127=common,
            input_inventory_sha256=frozen["inputs.jsonl"],
            panel_inventory_sha256=frozen["panels.json"],
            parent_prediction_lock_sha256=parent_sha,
            source=parent_plan["source"],
        ),
    )
    jobs = {q["id"]: q for q in plan["jobs"]}
    archived_jobs = {q["id"]: q for q in parent_plan["cases"] if q["cohort"] == "roof"}
    roster_matches(jobs, excluded, "native excluded fresh plan")
    for ident, row in rows.items():
        input_binding(row, inputs[ident], NATIVE)
        new = ident in jobs
        prediction = raw[ident] if new else old[ident]
        job = jobs[ident] if new else archived_jobs[ident]
        packet = job.get("packet")
        require_fields(
            prediction, dict(method=PARENT, input_sha256=digest(packet) if packet else None)
        )
        if packet is not None and (
            packet["native"]["sha256"] != row["native_sha256"]
            or packet["catalogue"]["sha256"] != row["catalog_sha256"]
            or packet["offer"] != row["tile"]
        ):
            raise ValueError(f"{ident} native packet differs from the original offer")
        expected = dict(
            prediction,
            method=NATIVE,
            parent_method=PARENT,
            cohort="excluded32" if new else "common127",
            measurement="fresh_excluded32" if new else "sealed_common127",
            worker_attempted=prediction.get("worker_attempted", True),
        )
        if row != expected:
            raise ValueError(f"{ident} native normalized result differs from its worker receipt")
    analysis = read(folder / "analysis-sources.json")
    require_fields(
        analysis,
        dict(
            archived_parent_prediction_lock_sha256=parent_sha,
            frozen_fixture={
                k: frozen[k] for k in ("inputs.jsonl", "panels.json", "scores.csv", "targets.jsonl")
            },
            original_score_source=ORIGINALS,
            original_score_source_sha256=original_score_sha,
        ),
    )
    return rows, read(folder / "original-v5-audit.json")


def original_scores(screen):
    proof = read(corpus.FROZEN / "provenance.json")
    raw = gzip.decompress((screen / ORIGINAL_EXPORT).read_bytes())
    if corpus._sha(raw) != proof["sources"][ORIGINALS]:
        raise ValueError("original score snapshot differs from frozen source provenance")
    return raw


def verify_originals(raw, refs, native, common, excluded):
    historical = {}
    for row in csv.DictReader(io.StringIO(raw.decode())):
        if not row["query_id"] and row["case"] in refs and row["method"] in ROLES:
            key = (row["case"], row["method"], row["arm"])
            if key in historical:
                raise ValueError(f"duplicate original receiver result {key}")
            historical[key] = row
    roster_matches(
        native, [ident for ident in refs if ident.startswith("DS26-")], "native originals"
    )
    roster_matches(excluded, native.keys() - common.keys(), "excluded compact originals")
    roster_matches(
        historical, [(i, r, a) for i in refs for r in ROLES for a in ARMS], "historical endpoints"
    )
    for ident, ref in refs.items():
        bindings = (common if ident in common else excluded)[ident]
        other = native.get(ident, {})
        roster_matches(bindings, ROLES, f"{ident} original roles")
        if ident in native:
            roster_matches(other, ROLES, f"{ident} independent original role audit")
        for role, binding in bindings.items():
            request, execution = binding["request_sha256"], binding["execution_sha256"]
            for value in (request.removeprefix("sha256:"), execution):
                check_digest(value)
            if other:
                require_fields(
                    other[role], dict(request_sha256=request, execution_sha256=execution)
                )
            if ident in excluded:
                require_fields(binding, dict(archive_status=other[role]["status"]))
            for arm in ARMS:
                old, endpoint = historical[ident, role, arm], ref["reference"][role][arm]
                point = (
                    [float(old[key]) for key in ("latitude_deg", "longitude_deg")]
                    if old["latitude_deg"]
                    else None
                )
                require_fields(old, dict(worker_request_sha256=request, status=endpoint["status"]))
                if other:
                    require_fields(old, dict(worker_status=other[role]["status"]))
                gap = distance_km(point, ref["truth"])
                if (
                    point != endpoint["latlon"]
                    or (gap is None) != (endpoint["error_km"] is None)
                    or (gap is not None and abs(gap - endpoint["error_km"]) > 1e-6)
                ):
                    raise ValueError(f"{ident}/{role}/{arm} differs from the frozen original score")


def measurements(screen):
    all_ids, frozen = corpus._selection("ds26-all159")
    common, _ = corpus._selection("ds26-common127")
    excluded, _ = corpus._selection("ds26-excluded32")
    index = corpus._index(corpus._read_frozen("inputs.jsonl", frozen))
    refs = {ref["id"]: ref for ref in corpus.references("ds26-all159")}
    ds29 = {ref["id"]: ref for ref in corpus.references("roof16") if ref["group"] == "DS29"}
    if (
        (len(all_ids), len(common), len(excluded), len(ds29)) != (159, 127, 32, 8)
        or set(common) & set(excluded)
        or set(common) | set(excluded) != refs.keys()
        or [ident for ident in all_ids if index[ident].get("unavailable")] != ["DS26-0172"]
    ):
        raise ValueError("unexpected canonical DS26 roof decomposition")
    previous, common_originals = compact_common(screen, [*common, *ds29], index)
    compact, excluded_originals = compact_excluded(
        screen / STUDY / "compact", excluded, index, frozen
    )
    originals = original_scores(screen)
    native, native_originals = native_results(
        screen, all_ids, common, excluded, index, frozen, corpus._sha(originals)
    )
    verify_originals(originals, refs | ds29, native_originals, common_originals, excluded_originals)
    combined = previous | compact
    return (
        refs,
        {ident: combined[ident] for ident in all_ids},
        native,
        dict(all159=all_ids, excluded32=excluded, common127=common),
    )


def outcome(raw_status, attempted, point):
    if point is not None:
        return "published"
    if raw_status == "ok":
        return "withheld"
    if raw_status == "missing" and attempted is False:
        return "unattempted"
    return raw_status


def add_only(initial, supplemental):
    waiting = [
        ident
        for ident, row in initial.items()
        if row.get("attempted") is False
        and row.get("source") == "not_launched"
        and row["result"]["status"] == "missing"
    ]
    roster_matches(supplemental, waiting, "add-only supplemental compact cohort")
    combined = dict(initial)
    for ident, followup in supplemental.items():
        first = initial[ident]
        require_fields(
            followup,
            {
                key: first[key]
                for key in (
                    "id",
                    "method",
                    "mode",
                    "input_sha256",
                    "native_sha256",
                    "catalog_sha256",
                    "frozen_request_sha256",
                    "tile",
                )
            },
        )
        if followup["result"]["status"] in ("unavailable", "missing"):
            raise ValueError(f"{ident} has no actual supplemental worker outcome")
        require_fields(followup, dict(attempted=True, deadline_s=195))
        roster_matches(followup["result"]["arms"], ARMS, f"{ident} supplemental arms")
        combined[ident] = dict(followup, supplemental_attempt=True)
    return combined


def completion(screen, initial, cases):
    folder = screen / STUDY / "completion"
    receipt = seal(folder, PREDICTION_LOCK, (POSITIONS, "roster.json"))
    original = screen / STUDY / "compact"
    original_sha = sha(original / PREDICTION_LOCK)
    binding = dict(original_prediction_lock_sha256=original_sha)
    require_fields(receipt, binding)
    prior_plan = read(original / "roster.json")
    plan = read(folder / "roster.json")
    subset = {ident: initial[ident] for ident in cases}
    queued = [
        ident for ident in prior_plan["order"] if subset[ident].get("source") == "not_launched"
    ]
    scheduled = sorted(queued)
    require_fields(
        plan,
        dict(
            binding,
            cases=scheduled,
            order=queued,
            bindings={ident: prior_plan["bindings"][ident] for ident in scheduled},
            **{key: prior_plan[key] for key in ("worker_cap_s", "compact_sources", "cli_digest")},
        ),
    )
    roster_matches(plan["assignments"], scheduled, "supplement worker assignments")
    supplemental = locked_rows(folder, POSITIONS, receipt, scheduled)
    for ident, row in supplemental.items():
        audit_compact(row, plan)
        require_fields(
            row,
            dict(
                source="fresh_complement_completion",
                cpu=plan["assignments"][ident],
                worker_returned=row["result"]["status"] in ("ok", "withheld"),
            ),
        )
    revised = add_only(subset, supplemental)
    combined_file = "all32-positions.jsonl.gz"
    combined_receipt = seal(folder, "all32-prediction-lock.json", (combined_file,))
    require_fields(
        combined_receipt,
        dict(binding, supplement_prediction_lock_sha256=sha(folder / PREDICTION_LOCK)),
    )
    archived = locked_rows(folder, combined_file, combined_receipt, cases)
    for ident, measured in revised.items():
        if archived[ident] != {
            key: value for key, value in measured.items() if key != "supplemental_attempt"
        }:
            raise ValueError(f"{ident} completion archive disagrees with its add-only join")
    return initial | revised


def performance_rows(refs, compact, native, cohorts):
    excluded = set(cohorts["excluded32"])
    for ident, ref in refs.items():
        cohort = "excluded32" if ident in excluded else "common127"
        for method, archive in ((COMPACT, compact), (NATIVE, native), *((r, None) for r in ROLES)):
            for arm in ARMS:
                if archive is None:
                    endpoint = ref["reference"][method][arm]
                    status = endpoint["status"]
                    attempted = status != "missing"
                    source = "archived_original_v5"
                    measurement = source
                    reason = "no_native_run" if ident == "DS26-0172" else None
                    held, worker = None, endpoint["wall_s"]
                else:
                    row = archive[ident]
                    result = row["result"]
                    endpoint = result["arms"][arm]
                    status = result["status"]
                    attempted = (
                        row["attempted"]
                        if archive is compact and cohort == "excluded32"
                        else True
                        if archive is compact
                        else row["worker_attempted"]
                    )
                    source = row.get("source", row.get("measurement"))
                    measurement = (
                        "supplemental_excluded32"
                        if row.get("supplemental_attempt")
                        else "initial_budget_excluded32"
                        if archive is compact and cohort == "excluded32"
                        else row.get("measurement", "sealed_common127")
                    )
                    reason = result.get("reason")
                    held = (
                        result["metrics"].get("held_by_arm", {}).get(arm, {}).get("held_rf_rms_hz")
                    )
                    worker = row.get("worker_wall_s")
                    if worker is None and source in ("prior_timing", "prior_confirmation"):
                        worker = row.get(f"{source}_worker_wall_s")
                point = endpoint["latlon"]
                forced = endpoint.get("forced_latlon")
                state = outcome(status, attempted, point)
                if archive is None and ident == "DS26-0172":
                    state = "unavailable"
                yield dict(
                    id=ident,
                    cohort=cohort,
                    method=method,
                    arm=arm,
                    source=source,
                    measurement=measurement,
                    attempted=attempted,
                    source_status=status,
                    outcome=state,
                    reason=reason,
                    lat_deg=point[0] if point else None,
                    lon_deg=point[1] if point else None,
                    error_km=distance_km(point, ref["truth"]),
                    forced_lat_deg=forced[0] if forced else None,
                    forced_lon_deg=forced[1] if forced else None,
                    forced_error_km=distance_km(forced, ref["truth"]),
                    rf_rms_kind=RF_KIND[method],
                    rf_rms_hz=endpoint.get("rf_rms_hz"),
                    held_rf_rms_hz=held,
                    worker_wall_s=worker,
                )


def paired(candidate, control, candidate_states=(), control_states=()):
    pairs = list(zip(candidate, control, strict=True))
    both = [(a, b) for a, b in pairs if a is not None and b is not None]
    result = dict(
        both_fix=len(both),
        candidate_rescue=sum(a is not None and b is None for a, b in pairs),
        candidate_loss=sum(a is None and b is not None for a, b in pairs),
        neither_fix=sum(a is None and b is None for a, b in pairs),
        candidate_within_10pct=sum(a <= 1.1 * b for a, b in both),
        control_within_10pct=sum(b <= 1.1 * a for a, b in both),
        candidate_at_least_10pct_better=sum(a < b and a <= 0.9 * b for a, b in both),
        control_at_least_10pct_better=sum(b < a and b <= 0.9 * a for a, b in both),
        candidate_common_fix_error_km=distribution(a for a, _ in both),
        control_common_fix_error_km=distribution(b for _, b in both),
    )
    if candidate_states and control_states:
        result["rescue_control_outcomes"] = dict(
            Counter(
                state
                for (a, b), state in zip(pairs, control_states, strict=True)
                if a is not None and b is None
            )
        )
        result["loss_candidate_outcomes"] = dict(
            Counter(
                state
                for (a, b), state in zip(pairs, candidate_states, strict=True)
                if a is None and b is not None
            )
        )
    return result


def summarize(rows, cohorts):
    indexed = {(r["id"], r["method"], r["arm"]): r for r in rows}
    summary = {}
    for cohort, cases in cohorts.items():
        section = dict(scheduled=len(cases), position={}, frequency={}, frequency_calibration={})
        for arm in ARMS:
            selected = {
                method: [indexed[ident, method, arm] for ident in cases]
                for method in (COMPACT, NATIVE, *ROLES)
            }
            errors = {
                method: [row["error_km"] for row in records] for method, records in selected.items()
            }
            section["position"][arm] = {}
            section["frequency"][arm] = {}
            for method, records in selected.items():
                counts = Counter(row["outcome"] for row in records)
                section["position"][arm][method] = dict(
                    outcomes={state: counts[state] for state in STATES},
                    sources=dict(Counter(row["source"] for row in records)),
                    attempted=sum(row["attempted"] is True for row in records),
                    returned_error_km=distribution(errors[method]),
                    all_attempts_within_km=thresholds(errors[method]),
                )
                section["frequency"][arm][method] = dict(
                    rf_rms_kind=RF_KIND[method],
                    reported_rf_rms_hz=distribution(row["rf_rms_hz"] for row in records),
                    held_rf_rms_hz=distribution(row["held_rf_rms_hz"] for row in records),
                )
            section["position"][arm]["paired"] = {
                f"{candidate}_vs_{control}": paired(
                    errors[candidate],
                    errors[control],
                    [row["outcome"] for row in selected[candidate]],
                    [row["outcome"] for row in selected[control]],
                )
                for candidate, controls in ((NATIVE, (COMPACT, *ROLES)), (COMPACT, ROLES))
                for control in controls
            }
        for method in (COMPACT, NATIVE, *ROLES):
            changes = {}
            for field in ("rf_rms_hz", "held_rf_rms_hz"):
                values = (tuple(indexed[i, method, arm][field] for arm in ARMS) for i in cases)
                changes[f"fitted_minus_zero_{field}"] = distribution(
                    fitted - zero
                    for zero, fitted in values
                    if zero is not None and fitted is not None
                )
            section["frequency_calibration"][method] = changes
        summary[cohort] = section
    return summary


def pack(path, rows):
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))


def write_views(screen, output, refs, compact, native, cohorts, *, first_budget, initial_missing):
    rows = list(performance_rows(refs, compact, native, cohorts))
    summary = summarize(rows, cohorts)
    for cohort in ("all159", "excluded32"):
        summary[cohort]["compact_execution_scope"] = dict(
            initial_budget_unattempted=initial_missing,
            supplemental_attempts=0 if first_budget else initial_missing,
            per_worker_limit_s=195,
            original_total_wall_limit_s=720,
        )
    sources = (
        Path("secant-full") / PREDICTION_LOCK,
        Path("secant-full/receipt.json"),
        STUDY / "compact" / PREDICTION_LOCK,
        STUDY / "compact/score-lock.json",
        STUDY / "native/all159-figure-lock.json",
        STUDY / "native/excluded32-figure-lock.json",
        STUDY / "native/fresh-lock.json",
        Path("factors/native-clock-full") / PREDICTION_LOCK,
        *(
            Path("../2026_11_19_receiver_convergence") / study / lock
            for _, study, lock, _ in PRIOR_COMPACT
        ),
    )
    if not first_budget:
        sources += (
            STUDY / "completion" / PREDICTION_LOCK,
            STUDY / "completion/all32-prediction-lock.json",
        )
    save_json(
        output / "source-audit.json",
        dict(
            screening_seals={str(path): sha(screen / path) for path in sources},
            frozen_fixture=read(corpus.FROZEN / "provenance.json")["files"],
            original_score_sha256=read(corpus.FROZEN / "provenance.json")["sources"][ORIGINALS],
            original_score_archive=str(ORIGINAL_EXPORT),
            original_score_archive_sha256=sha(screen / ORIGINAL_EXPORT),
            original_role_receipts=dict(ds26=4 * len(refs), prior_ds29=4 * 8),
            initial_budget_unattempted=initial_missing,
            supplemental_attempts=0 if first_budget else initial_missing,
            restrictions=[
                "The historical common127 required fixes from all four original v5 policies. "
                "The excluded32 retains each policy's failures, timeouts or missing inputs.",
                "The comparison uses archived native factors and the original offered tile. "
                "Compact common127 and smooth-clock common127 reuse sealed numerical results.",
                "Each measurement has its native and causal catalogue authenticated independently. "
                "Compact and smooth clock use different solver packets and RF populations.",
                "The supplement adds only previously unlaunched recordings with the same "
                "195 s per-worker limit. First-budget failures and timeouts are retained.",
                "Host and historical results. Embedded performance is outside this comparison.",
            ],
        ),
    )
    csv_file(output / "scores.csv", rows)
    save_json(output / "summary.json", summary)
    figures = []
    for cohort, title in (
        ("all159", "Compact vs smooth clock · all 159"),
        ("excluded32", "Compact vs smooth clock · excluded 32"),
    ):
        cases = cohorts[cohort]
        evidence = ("source-audit.json", "summary.json", "scores.csv")
        series = []
        for key, role, archive, label in (
            ("one", COMPACT, compact, "Compact v5 secant"),
            ("stock", NATIVE, native, "Native smooth clock"),
        ):
            name = f"{cohort}-{key}.jsonl.gz"
            pack(output / name, (archive[i] for i in cases))
            series.append(dict(key=key, file=name, value=role, label=label))
        lock = f"{cohort}-figure-lock.json"
        names = (*evidence, *(entry["file"] for entry in series))
        save_json(output / lock, dict(cases=cases, files={n: sha(output / n) for n in names}))
        counts = summary[cohort]["position"]["c0"][COMPACT]["outcomes"]
        outcome_labels = (
            ("failed", "failed"),
            ("timed_out", "timed out"),
            ("unattempted", "unattempted"),
            ("missing", "missing receipts"),
            ("unavailable", "unavailable"),
        )
        limited = ", ".join(
            f"{counts[state]} {label}" for state, label in outcome_labels if counts[state]
        )
        provenance = (
            "Archived common 127 and fresh complement under fixed caps."
            if cohort == "all159"
            else "Frozen complement of the historical common 127."
        )
        if first_budget:
            title = (
                f"First compact budget · {cohort.removeprefix('all').removeprefix('excluded')} DS26"
            )
            provenance = "Initial 720 s compact budget. " + provenance
        else:
            provenance += f" Adds {initial_missing} previously unlaunched compact cases."
        figures.append(
            dict(
                id=f"{METHOD}-{'budget-' if first_budget else ''}{cohort}",
                method=METHOD,
                scope="roof",
                title=title,
                cases=f"ds26-{cohort}",
                seal=lock,
                series=series,
                provenance=list(evidence),
                caption=(
                    f"{provenance} Compact outcomes include {limited}. "
                    "DS26-0172 has no native input."
                ),
            )
        )
    save_json(output / "figures.json", dict(version=1, charts=figures))
    return summary


def publish(screen, output, *, initial_only=False):
    refs, compact, native, cohorts = measurements(screen)
    write(output / ORIGINAL_EXPORT.name, (screen / ORIGINAL_EXPORT).read_bytes())
    initial_missing = sum(
        compact[ident].get("source") == "not_launched" for ident in cohorts["excluded32"]
    )
    initial = write_views(
        screen,
        output / "budget",
        refs,
        compact,
        native,
        cohorts,
        first_budget=True,
        initial_missing=initial_missing,
    )
    if initial_only:
        return initial
    combined = completion(screen, compact, cohorts["excluded32"])
    return write_views(
        screen,
        output,
        refs,
        combined,
        native,
        cohorts,
        first_budget=False,
        initial_missing=initial_missing,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=SCREEN)
    parser.add_argument("--out", type=local_output, default=REPORT)
    parser.add_argument("--initial-only", action="store_true")
    args = parser.parse_args()
    publish(args.evidence_root, args.out, initial_only=args.initial_only)


if __name__ == "__main__":
    main()
