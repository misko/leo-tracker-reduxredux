"""Rebuild confirmation evidence from sealed antenna receiver studies."""

from math import comb
from pathlib import Path

from .. import whole_iq
from ..__main__ import save_json
from ..scoring import ARMS, ROLES, distance_km, distribution
from . import complete_detector_roster as fixed
from . import fresh_replay, partner_holdout, receiver_budget, staggered_benchmark
from . import one_lane_roster as one
from . import one_lane_roster_results as controls
from . import second_on_miss_roster as miss
from .fresh_replay_results import sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .partner_on_hit_results import CONTRASTS, HIT, METHODS, PRIMARY, STOCK, effects
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

BASE = fixed.SCREEN / "antenna-confirmation"
REPORT = BASE / "benchmark"
DISCOVERY = partner_holdout.trial.REPORT
VALIDATION = partner_holdout.REPORT
DIRECT = BASE / "on-hit-waveforms"
FRESH = BASE / "fresh-full"
FRESH_METHODS = {"fresh_full_dual_four": STOCK, "fresh_full_partner_on_hit": HIT}
RAW = "full saved I/Q"
STORED = "reconstructed antenna records"
VERDICT = ("add_hit_without_miss", "add_miss_with_hit")
SCHEMA = "antenna-confirmation/v1"
HELD_PIN = "2a20b40f97365d6f3ef9b5d22c078e6ea36b3ec508dfc5d0b54d966395cdd55f"


def read_member(directory, lock, name):
    return whole_iq.read(fixed.member(directory, lock, name))


def known():
    first = sealed(DISCOVERY, "prediction-lock.json", partner_holdout.DISCOVERY_PIN)
    validation = sealed(VALIDATION, "prediction-lock.json", HELD_PIN)
    design = read_member(VALIDATION, validation, "plan.json")
    held, all_ids = partner_holdout.split(validation["cases"], first["cases"])
    if held != design["cases"] or held != validation["holdout"] or all_ids != design["pooled"]:
        raise ValueError("the validation roster overlaps discovery or changed its frozen plan")
    past = fixed.select(
        rows_from(fixed.member(DISCOVERY, first, "predictions.jsonl.gz")), HIT, first["cases"]
    )
    new = fixed.select(
        rows_from(fixed.member(VALIDATION, validation, "holdout-predictions.jsonl.gz")), HIT, held
    )
    label = fixed.select(
        rows_from(fixed.member(VALIDATION, validation, "positions.jsonl.gz")), HIT, all_ids
    )
    if past | new != label:
        raise ValueError("the pooled file changed a sealed discovery or holdout fit")
    if any(
        any(new[job["id"]][key] != value for key, value in job.items())
        for job in design["schedule"]
    ):
        raise ValueError("the held result differs from its staged scientific inputs")
    groups = dict(discovery=first["cases"], validation=held, pooled=all_ids)
    single = sealed(one.REPORT, "prediction-lock.json", miss.SINGLE_PIN)
    second = sealed(miss.REPORT, "prediction-lock.json", partner_holdout.trial.MISS_PIN)
    source = read_member(one.REPORT, single, "plan.json")["groups"]
    stock = controls.released_stock(source)
    cell = {
        STOCK: stock,
        HIT: label,
        PRIMARY: fixed.select(
            rows_from(fixed.member(one.REPORT, single, "positions.jsonl.gz")), PRIMARY, all_ids
        ),
        miss.METHOD: fixed.select(
            rows_from(fixed.member(miss.REPORT, second, "positions.jsonl.gz")), miss.METHOD, all_ids
        ),
    }
    audit = read_member(VALIDATION, validation, "packet-audit.json")
    earlier = read_member(DISCOVERY, first, "packet-audit.json")
    if set(audit) != set(all_ids) or any(audit[i] != earlier[i] for i in groups["discovery"]):
        raise ValueError("the held packet audit changed the known discovery evidence")
    for ident in all_ids:
        validate_cells(ident, cell, audit[ident])
    manifest = {
        str(p.relative_to(fixed.SCREEN)): _sha(p)
        for p in (
            DISCOVERY / "prediction-lock.json",
            VALIDATION / "prediction-lock.json",
            one.REPORT / "prediction-lock.json",
            miss.REPORT / "prediction-lock.json",
            fixed.REPORT / "all-figure-lock.json",
            staggered_benchmark.FRESH / "prediction-lock.json",
        )
    }
    return groups, cell, audit, manifest


def validate_cells(ident, cell, audit):
    four = cell[STOCK][ident]
    for key in METHODS:
        row = cell[key][ident]
        fixed.same_capture(four, row)
        recorded = row["result"]["metrics"].get("observations")
        if recorded is not None and recorded != audit["observations"][key]:
            raise ValueError(f"{ident} solver observations disagree with the gated support")
        if key != STOCK and row["stock_native_sha256"] != four["native_sha256"]:
            raise ValueError(f"{ident} receiver cells used different stock native input")
    if (
        audit["archive"]["native_sha256"] != four["native_sha256"]
        or audit["one_lane_native_sha256"] != cell[PRIMARY][ident]["native_sha256"]
        or audit["second_on_miss_native_sha256"] != cell[miss.METHOD][ident]["native_sha256"]
    ):
        raise ValueError(f"{ident} mixed physical factor lineage")
    valid, primary = audit["valid_visits"], audit["primary_hits"]
    if audit["calls"] != dict(
        zip(METHODS, (valid, valid + primary, 2 * valid - primary, 2 * valid), strict=True)
    ):
        raise ValueError(f"{ident} inconsistent factorial receiver call census")


def known_references(out, ids):
    authority, original = staggered_benchmark.fresh_references()
    _, fresh = staggered_benchmark.export_references(out, "known", ids, authority, original)
    _, old = held_references(None, [i for i in ids if i not in fresh])
    for row in original:
        for arm in ARMS:
            fresh[row["id"]]["reference"][row["method"]][arm]["rf_rms_hz"] = row["result"]["arms"][
                arm
            ].get("rf_rms_hz")
    return {r["id"]: r for r in old} | fresh


def terminal_scope(directory, mapping, plan):
    path = directory / "prediction-lock.json"
    if not path.is_file():
        return None
    lock = sealed(directory, path.name)
    if set(lock["cases"]) != set(plan["cases"]):
        raise ValueError(f"{directory.name} terminal replay changed its frozen geometry roster")
    source = read_member(directory, lock, "source-lock.json")
    if source != plan:
        raise ValueError(f"{directory.name} prediction does not bind the current source")
    rows = rows_from(fixed.member(directory, lock, "positions.jsonl.gz"))
    positions = {
        key: {
            ident: dict(row, method=key, source_method=original)
            for ident, row in fixed.select(rows, original, sorted(plan["cases"])).items()
        }
        for original, key in mapping.items()
    }
    for table in positions.values():
        for ident, row in table.items():
            expected = source["cases"][ident]
            fields = ("capture_native_sha256", "request_sha256", "catalog_sha256", "tile")
            if tuple(row[k] for k in fixed.BINDINGS) != tuple(expected[k] for k in fields):
                raise ValueError(
                    f"{ident} changed its raw capture, causal request, or offered tile"
                )
    return lock, positions, read_member(directory, lock, "resources.json")


def exact_sign(values):
    lower = sum(v < 0 for v in values)
    higher = sum(v > 0 for v in values)
    n = lower + higher
    p = min(1.0, 2 * sum(comb(n, k) for k in range(min(lower, higher) + 1)) / (2**n))
    return lower, higher, len(values) - n, p if n else None


def holm(pvalues):
    """Correct the declared family, including tests without eligible pairs."""
    ordered = sorted((p, i) for i, p in enumerate(pvalues) if p is not None)
    output = [None] * len(pvalues)
    previous = 0.0
    for rank, (p, index) in enumerate(ordered):
        previous = min(1.0, max(previous, (len(pvalues) - rank) * p))
        output[index] = previous
    return output


def contrasts(scoped_scores, groups):
    data, verdicts = [], []
    for stage in ("discovery", "validation", "pooled"):
        selected = {(r["id"], r["method"], r["arm"]): r for r in scoped_scores[stage]}
        for arm in ARMS:
            for metric in ("error_km", "rf_rms_hz"):
                for ident in groups[stage]:
                    values = [selected[ident, method, arm][metric] for method in METHODS]
                    data.append(
                        dict(
                            scope=stage,
                            id=ident,
                            arm=arm,
                            measure=metric,
                            **dict(zip(METHODS, values, strict=True)),
                            **effects(*values),
                        )
                    )
                for term in CONTRASTS:
                    values = [
                        r[term]
                        for r in data
                        if r["scope"] == stage
                        and r["arm"] == arm
                        and r["measure"] == metric
                        and r[term] is not None
                    ]
                    lower, higher, ties, p = exact_sign(values)
                    tested = stage == "validation" and metric == "error_km" and term in VERDICT
                    verdicts.append(
                        dict(
                            scope=stage,
                            arm=arm,
                            measure=metric,
                            contrast=term,
                            scheduled=len(groups[stage]),
                            paired=len(values),
                            improvements=lower,
                            losses=higher,
                            ties=ties,
                            median_change=distribution(values)["p50"],
                            exact_sign_p=p if tested else None,
                            holm_p=None,
                            test_family="held geography" if tested else None,
                        )
                    )
    registered = [r for r in verdicts if r["test_family"]]
    for r, adjusted in zip(registered, holm([r["exact_sign_p"] for r in registered]), strict=True):
        r["holm_p"] = adjusted
    for row in verdicts:
        row["passes_adjusted_005"] = row["holm_p"] <= 0.05 if row["holm_p"] is not None else None
    return data, verdicts, registered


def tolerance_pairs(rows, methods, scope):
    prior = {(r["id"], r["arm"], r["method"]): r for r in rows}
    data = []
    for (ident, arm, method), candidate in prior.items():
        if method != HIT:
            continue
        for control in (m for m in methods if m != HIT):
            old = prior[ident, arm, control]
            base = candidate["baseline_km"]
            if base != old["baseline_km"]:
                raise ValueError("paired methods used different no-repair v5 references")
            a, b = candidate["error_km"], old["error_km"]
            for pct in (5, 10):
                okay = None if base is None else a is not None and a <= (1 + pct / 100) * base
                other = None if base is None else b is not None and b <= (1 + pct / 100) * base
                category = {
                    (True, True): "both",
                    (True, False): "on_hit_only",
                    (False, True): "control_only",
                    (False, False): "neither",
                }.get((okay, other), "reference_unavailable")
                data.append(
                    dict(
                        scope=scope,
                        id=ident,
                        arm=arm,
                        pct=pct,
                        comparator=control,
                        original_no_repair_km=base,
                        on_hit_status=candidate["status"],
                        control_status=old["status"],
                        on_hit_km=a,
                        control_km=b,
                        on_hit_meets_original=okay,
                        control_meets_original=other,
                        paired_outcome=category,
                        on_hit_meets_control=None
                        if b is None
                        else a is not None and a <= (1 + pct / 100) * b,
                        on_hit_within_symmetric_control_pct=None
                        if b is None or a is None
                        else (1 - pct / 100) * b <= a <= (1 + pct / 100) * b,
                    )
                )
    return data


def tolerance_summary(rows):
    groups = {}
    for row in rows:
        key = tuple(row[k] for k in ("scope", "arm", "pct", "comparator"))
        counts = groups.setdefault(
            key,
            dict.fromkeys(
                (
                    "both",
                    "on_hit_only",
                    "control_only",
                    "neither",
                    "reference_unavailable",
                ),
                0,
            ),
        )
        counts[row["paired_outcome"]] += 1
    return [
        dict(
            zip(("scope", "arm", "pct", "comparator"), key, strict=True),
            scheduled=sum(counts.values()),
            **counts,
        )
        for key, counts in sorted(groups.items())
    ]


def reference_rows(refs, ids):
    output = []
    for ident in ids:
        for method in ROLES:
            for arm in ARMS:
                endpoints = refs[ident]["reference"]
                fit = endpoints[method][arm]
                error = fit.get("error_km")
                baseline = endpoints["baseline"][arm].get("error_km")
                output.append(
                    dict(
                        id=ident,
                        method=method,
                        arm=arm,
                        status=fit["status"],
                        reason=fit.get("reason"),
                        error_km=error,
                        forced_error_km=None,
                        baseline_km=baseline,
                        within_5pct=error is not None
                        and baseline is not None
                        and error <= 1.05 * baseline,
                        within_10pct=error is not None
                        and baseline is not None
                        and error <= 1.10 * baseline,
                        rf_rms_hz=fit.get("rf_rms_hz"),
                        frequency_score=fit.get("frequency_score"),
                        **{
                            f"{key}_km": endpoints[key][arm].get("error_km")
                            for key in ROLES
                            if key != "baseline"
                        },
                    )
                )
    return output


def summary(rows, ids, scope):
    output = []
    for method, arm in sorted({(r["method"], r["arm"]) for r in rows}):
        group = [r for r in rows if (r["method"], r["arm"]) == (method, arm)]
        if len(group) != len(ids) or {r["id"] for r in group} != set(ids):
            raise ValueError("each displayed receiver must preserve the entire scope denominator")
        error = distribution(r["error_km"] for r in group)
        rf = distribution(r["rf_rms_hz"] for r in group)
        output.append(
            dict(
                scope=scope,
                method=method,
                arm=arm,
                scheduled=len(ids),
                published=error["n"],
                withheld=sum(r["status"] == "withheld" for r in group),
                timed_out=sum(r["status"] == "timed_out" for r in group),
                terminal_failed=sum(r["status"] == "failed" for r in group),
                reference_pending=sum(r["status"] == "reference_pending" for r in group),
                original_reference_available=sum(r["baseline_km"] is not None for r in group),
                within_5pct=sum(r["within_5pct"] for r in group),
                within_10pct=sum(r["within_10pct"] for r in group),
                median_km=error["p50"],
                p95_km=error["p95"],
                conditional_rf_n=rf["n"],
                median_rf_hz=rf["p50"],
                p95_rf_hz=rf["p95"],
            )
        )
    return output


def clock(scope, ident, method, planned=None, measured=None, position=None, calls=None):
    capture, fit = measured or {}, position or {}
    raw, assembly = capture.get("raw_s"), capture.get("assembly_s")
    visits, timely = capture.get("dual_calls"), capture.get("within_20ms")
    if timely is None:
        visits = None
    return dict(
        scope=scope,
        id=ident,
        method=method,
        acquisition_evidence=RAW if measured else STORED,
        planned_receiver_calls=planned,
        measured_receiver_calls=calls,
        complete_detector_calls=visits,
        wall_within_20ms=timely,
        detector_wall_p50_ms=capture.get("detector_call_wall_ms", {}).get("p50"),
        detector_wall_p95_ms=capture.get("detector_call_wall_ms", {}).get("p95"),
        detector_cpu_p50_ms=capture.get("detector_call_cpu_ms", {}).get("p50"),
        detector_cpu_p95_ms=capture.get("detector_call_cpu_ms", {}).get("p95"),
        call_clock_scope="complete decoded visit detector call" if visits is not None else None,
        acquisition_to_native_s=raw + assembly
        if raw is not None and assembly is not None
        else None,
        position_wall_s=capture.get("position_s", fit.get("wall_s")),
        position_cpu_s=fit.get("cpu_s"),
        full_service_s=capture.get("wall_s"),
        whole_service_cpu_s=capture.get("cpu_s"),
        charged_peak_bytes=capture.get("max_bytes", fit.get("peak_bytes")),
        terminal_wall_s=capture.get("wall_to_failure_s"),
    )


def overlap(raw, projected, ids, lock, audit, resources):
    rows, measures = [], []
    recorded = read_member(DIRECT, lock, "parity.json")
    for ident in ids:
        measured, planned = raw[HIT][ident], projected[HIT][ident]
        fixed.same_capture(measured, planned)
        true_input, ref = measured.get("native_sha256"), planned.get("native_sha256")
        proof = audit[ident]
        native_member = f"native/{ident}.json.gz"
        actual = None
        if native_member in lock["files"]:
            actual = digest_native(fixed.member(DIRECT, lock, native_member))
            if true_input != actual or recorded[ident]["native_sha256"] != actual:
                raise ValueError(f"{ident} measured native archive did not feed the recorded fix")
        a, b = (r["result"] for r in (measured, planned))
        for arm in ARMS:
            x, y = a["arms"][arm], b["arms"][arm]
            rows.append(
                dict(
                    schema="antenna-raw-position-parity/v1",
                    scope="direct_validation",
                    id=ident,
                    arm=arm,
                    native_replay_sha256=actual,
                    native_projection_sha256=ref,
                    exact_native_bytes=actual == ref if actual else None,
                    replay_status=a["status"],
                    projection_status=b["status"],
                    exact_position_and_rf=all(
                        x.get(k) == y.get(k) for k in ("latlon", "forced_latlon", "rf_rms_hz")
                    )
                    if a["status"] == b["status"] == "ok"
                    else None,
                    separation_km=distance_km(x.get("latlon"), y.get("latlon")),
                )
            )
        sample = resources[ident]
        planned_calls = proof["calls"][HIT]
        calls = recorded[ident].get("actual_receiver_calls")
        calls = sum(calls) if calls is not None else None
        if calls is not None and calls != planned_calls:
            raise ValueError(
                f"{ident} direct measured call census differs from the frozen projection"
            )
        measures.append(clock("direct_validation", ident, HIT, planned_calls, sample, calls=calls))
    return rows, measures


def fresh_measurements(lock, positions, resources, ids):
    proof = read_member(FRESH, lock, "parity.json")
    clocks, parity = [], []
    for ident in ids:
        item = proof[ident]
        for role, method, field in (
            ("control", STOCK, "dual_physical_receiver_calls"),
            ("candidate", HIT, "actual_physical_receiver_calls"),
        ):
            clocks.append(
                clock(
                    "fresh", ident, method, measured=resources[ident][role], calls=item.get(field)
                )
            )
        member = f"native/candidate/{ident}.json.gz"
        actual, projected = None, item.get("projected_native_sha256")
        if member in lock["files"]:
            actual = digest_native(fixed.member(FRESH, lock, member))
            if (
                actual != item["measured_native_sha256"]
                or actual != positions[HIT][ident]["native_sha256"]
            ):
                raise ValueError(f"{ident} fresh raw output differs from its published fit")
        for arm in ARMS:
            parity.append(
                dict(
                    schema="antenna-raw-position-parity/v1",
                    scope="fresh",
                    id=ident,
                    arm=arm,
                    native_replay_sha256=actual,
                    native_projection_sha256=projected,
                    exact_native_bytes=actual == projected if actual and projected else None,
                    replay_status=positions[HIT][ident]["result"]["status"],
                    projection_status=None,
                    exact_position_and_rf=None,
                    separation_km=None,
                )
            )
    return parity, clocks


def digest_native(path):
    import gzip
    from hashlib import sha256

    return sha256(gzip.decompress(path.read_bytes())).hexdigest()


def fresh_truth(ids, terminal):
    """Join official independent truth to terminal receiver positions and optional v5 roles."""
    (novel,) = [i for i in ids if i.startswith("DS29")]
    _, base = held_references(None, [i for i in ids if i != novel])
    labels = whole_iq.read(
        whole_iq.checked(fresh_replay.DS29 / "evaluation-references.json", fresh_replay.TRUTH_SHA)
    )
    location = labels[novel]
    truth = [location["latitude_deg"], location["longitude_deg"]]
    refs = {k: {a: dict(status="reference_pending", error_km=None) for a in ARMS} for k in ROLES}
    receipt = FRESH / "reference-prediction-lock.json"
    if receipt.is_file():
        seal = sealed(FRESH, receipt.name)
        rows = rows_from(fixed.member(FRESH, seal, "fresh-v5.jsonl.gz"))
        if sorted((r["id"], r["method"]) for r in rows) != sorted((novel, r) for r in ROLES):
            raise ValueError("fresh original numerical receipt changed its four-role roster")
        for row in rows:
            fixed.same_capture(terminal[STOCK][novel], row)
            if row["native_sha256"] != row["paired_capture_sha256"]:
                raise ValueError("fresh original v5 used a substituted native input")
            for arm in ARMS:
                result = row["result"]
                values = result["arms"][arm]
                point = values.get("latlon")
                state = result["status"]
                refs[row["method"]][arm] = dict(
                    values,
                    status="withheld" if state == "ok" and point is None else state,
                    error_km=distance_km(truth, point),
                    reason=result.get("reason"),
                )
    return {r["id"]: r for r in base} | {novel: dict(truth=truth, reference=refs)}


def chart_index(directories):
    items = []
    for directory in directories:
        path = directory / "figures.json"
        if path.is_file():
            descriptor = whole_iq.read(path)
            for chart in descriptor["charts"]:
                receipt = directory / chart["seal"]
                sealed(directory, receipt.name)
                items.append(
                    dict(
                        id=chart["id"],
                        descriptor=str(path.relative_to(fixed.SCREEN)),
                        descriptor_sha256=_sha(path),
                        seal=receipt.name,
                        seal_sha256=_sha(receipt),
                    )
                )
    return items


def run(out):
    groups, cells, audit, manifest = known()
    refs = known_references(out, groups["pooled"])
    scoped, summaries, pairs, clocks, timings, references, budget = {}, [], [], [], [], [], []
    for label, ids in groups.items():
        panel = [cells[method][ident] for method in METHODS for ident in ids]
        scored = fixed.scored(panel, refs)
        scoped[label] = scored
        pairs.extend(tolerance_pairs(scored, METHODS, label))
        origin = reference_rows(refs, ids)
        references.extend(dict(scope=label, **r) for r in origin)
        summaries.extend(summary(scored + origin, ids, label))
        if label != "pooled":
            clocks.extend(
                clock(
                    label,
                    ident,
                    method,
                    audit[ident]["calls"][method],
                    position=cells[method][ident].get("position_resources"),
                )
                for method in METHODS
                for ident in ids
            )
    changes, verdict, tests = contrasts(scoped, groups)
    datasets, parity = (
        {label: dict(scheduled=ids, state="sealed") for label, ids in groups.items()},
        [],
    )
    for label, directory, mapping, terminal_needed in (
        ("direct_validation", DIRECT, {"partner_on_hit_whole": HIT}, groups["validation"]),
        ("fresh", FRESH, FRESH_METHODS, None),
    ):
        plan_path = directory / "source-lock.json"
        plan = whole_iq.read(plan_path)
        ids = sorted(plan["cases"])
        if terminal_needed is not None and not set(ids) <= set(terminal_needed):
            raise ValueError("the direct overlap is outside the validation roster")
        if terminal_needed is None and set(ids) & set(groups["pooled"]):
            raise ValueError("the fresh raw pair duplicates a previous factor recording")
        manifest[str(plan_path.relative_to(fixed.SCREEN))] = _sha(plan_path)
        terminal = terminal_scope(directory, mapping, plan)
        datasets[label] = dict(
            scheduled=ids, state="sealed" if terminal else "awaiting_prediction_seal"
        )
        if not terminal:
            continue
        lock, rows, resources = terminal
        path = directory / "prediction-lock.json"
        manifest[str(path.relative_to(fixed.SCREEN))] = _sha(path)
        if label == "direct_validation":
            proof, measured = overlap(rows, cells, ids, lock, audit, resources)
            local_refs = refs
        else:
            local_refs = fresh_truth(ids, rows)
            proof, measured = fresh_measurements(lock, rows, resources, ids)
            if (directory / "reference-prediction-lock.json").is_file():
                path = directory / "reference-prediction-lock.json"
                manifest[str(path.relative_to(fixed.SCREEN))] = _sha(path)
        parity.extend(proof)
        clocks.extend(measured)
        scored = fixed.scored([rows[m][i] for m in rows for i in ids], local_refs)
        scoped[label] = scored
        pairs.extend(tolerance_pairs(scored, rows, label))
        origin = reference_rows(local_refs, ids)
        references.extend(dict(scope=label, **r) for r in origin)
        summaries.extend(summary(scored + origin, ids, label))
        spans = {}
        for ident, attempts in resources.items():
            for attempt in (attempts,) if label == "direct_validation" else attempts.values():
                window = (attempt.get("counts") or {}).get("window_delivery_span_s")
                if window is not None and spans.setdefault(ident, window) != window:
                    raise ValueError("direct policies used different original delivery clocks")
        if set(spans) == set(ids):
            joined = receiver_budget.joined_rows(scored, measured, spans)
            timings.extend(dict(scope=label, **r) for r in joined)
            budget.extend(receiver_budget.summarize(joined, {label: ids}, rows))
    items = dict(
        scores=[dict(scope=stage, **row) for stage, records in scoped.items() for row in records],
        summary=summaries,
        tolerances=pairs,
        changes=changes,
        contrasts=verdict,
        clocks=clocks,
        **{
            "accuracy-and-time": timings,
            "budget-summary": budget,
            "tolerance-summary": tolerance_summary(pairs),
            "raw-position-parity": parity,
            "reference-scores": references,
        },
    )
    for name, rows in items.items():
        if rows:
            csv_file(out / f"{name}.csv", rows)
    save_json(out / "verdict.json", dict(schema=SCHEMA, alpha=0.05, tests=tests, scopes=datasets))
    save_json(
        out / "chart-index.json", dict(charts=chart_index((DISCOVERY, VALIDATION, DIRECT, FRESH)))
    )
    outputs = {f"{name}.csv": _sha(out / f"{name}.csv") for name, rows in items.items() if rows}
    outputs.update(
        {
            n: _sha(out / n)
            for n in (
                "verdict.json",
                "chart-index.json",
                "known-roof.json",
                "known-v5.jsonl.gz",
            )
        }
    )
    save_json(
        out / "benchmark-lock.json",
        dict(
            schema=SCHEMA,
            scopes=datasets,
            files=outputs,
            inputs=manifest,
            source_sha256=_sha(Path(__file__)),
            protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        ),
    )
    return tests, datasets


def show(result, out):
    tests, datasets = result
    for item in tests:
        probability = item["holm_p"]
        p = "n/a" if probability is None else f"{probability:.5g}"
        print(
            item["arm"],
            item["contrast"],
            f"{item['improvements']}/{item['paired']} improved",
            f"Holm p={p}",
        )
    for name, scope in datasets.items():
        print(name, len(scope["scheduled"]), scope["state"])
    print(out)
