"""Seal complete development waveforms, detector traces and same-request positions."""

import argparse
import gzip
from collections import Counter
from hashlib import sha256
from pathlib import Path

from .. import iq_service, whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution
from . import diagnostic_whole as trial
from . import frontier_whole_replay_results as traces
from . import screening_figures
from . import whole_band_results as measured
from . import whole_fftw_trial as held
from .exact_wide_iq_results import detector_rows, timing_rows
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from
from .wide_roster_results import same_receiver, whole_support

BRANCHES = {"control": trial.BASELINE, "candidate": trial.METHOD}
POSITION = "positions.jsonl.gz"
VISITS = "visits.jsonl.gz"
DEADLINES = "deadlines.csv"
PROBES = "probe-audit.json"
VISIT_COVERAGE = "visit-coverage.json"
HELD_FFTW_PIN = "808045eb0314e83b56a1b2c911a4c73942c5de5d2710ab1f614542493da4fbe9"
HELD_STOCK_PIN = "e46441f38312a61a4febff38c15d06a2a4bb53a3037ddcc84c1bc95f50d53671"
PHYSICAL_KEYS = ("catalog_sha256", "tile", "original_request_sha256", "paired_capture_sha256")


def stock_attempt(ident, seal, row, resource):
    if row["result"]["status"] != "ok" or not iq_service.succeeded(resource["service"]):
        raise ValueError("fixed stock control lacks its actual terminal result")
    native = f"native/control/{ident}.json.gz"
    archive = whole_iq.checked(trial.STOCK / native, seal["files"][native])
    if sha256(gzip.decompress(archive.read_bytes())).hexdigest() != row["native_sha256"]:
        raise ValueError("archived genuine stock native factors changed")
    receipt = resource["service"]
    binding = receipt["binding"]
    path = Path(binding["attempt"])
    whole_iq.checked(path / "plan.json", binding["plan_sha256"])
    whole_iq.checked(path / "service.log", receipt["log_sha256"])
    whole_iq.checked(path / "recording/native.json", row["native_sha256"])
    first = whole_iq.read(path / "raw.json")
    if first["native_sha256"].removeprefix("sha256:") != row["native_sha256"] or any(
        first[key] != resource[key] for key in (*measured.COMMON, "counts", "input_manifest_sha256")
    ):
        raise ValueError("stock scratch differs from the authenticated complete trace")
    return dict(row, method=trial.BASELINE, cohort="development diagnostic"), path


def matched_physical(stock, candidate, scheduled):
    if stock["detector_sha256"] == candidate["detector_sha256"]:
        raise ValueError("candidate service reused the stock detector")
    measured.pair_geometry(stock, candidate)
    if stock["input_manifest_sha256"] != candidate["input_manifest_sha256"]:
        raise ValueError("candidate and stock replayed different frozen waveform manifests")
    for row in (stock, candidate):
        whole_support(row, scheduled, scheduled["clock_authority"])


def passing(candidates):
    return Counter(
        traces.fingerprint({k: v for k, v in row.items() if k != "candidate_rank"})
        for row in candidates
        if row["passed_fractional_margin_gate"]
    )


def retention(stock, candidate):
    for left, right in zip(stock, candidate, strict=True):
        kept, proposed = [], []
        for old, new in zip(left["probes"], right["probes"], strict=True):
            before, after = passing(old["candidates"]), passing(new["candidates"])
            retained = sum((before & after).values())
            kept.append(retained)
            proposed.append(sum(after.values()) - retained)
        yield dict(
            visit=left["visit"],
            retained_stock_gates=kept,
            new_gate_payloads=proposed,
        )


def gate_stability(stock, candidate, control, scout):
    changes = traces.compare_probes(control, scout)
    match = list(retention(stock, candidate))
    for row, retained, new in zip(scout, control, match, strict=True):
        row.update({k: v for k, v in new.items() if k != "visit"})
        for original, run in zip(retained["probes"], row["probes"], strict=True):
            run["stock_positive"] = original["winner_sha256"] is not None
    retained = sum(sum(row["retained_stock_gates"]) for row in match)
    return dict(
        changes,
        stock_positive_probes_still_positive=(
            changes["stock_positive_probes"] - changes["lost_positive_probes"]
        ),
        stock_positive_probes_with_identical_gate=sum(
            n > 0 for row in match for n in row["retained_stock_gates"]
        ),
        stock_gated_candidates_retained=retained,
        stock_gated_candidates_removed=changes["stock_gated_candidates"] - retained,
        candidate_gate_new_payloads=changes["candidate_gated_candidates"] - retained,
    )


def trace_bundle(ident, role, path, resource):
    data = detector_rows(path)
    if data is None:
        return None
    visits, calls, _ = data
    if (
        len(calls) != resource["dual_calls"]
        or distribution([1000 * t["wall_s"] for t in calls]) != resource["detector_call_wall_ms"]
        or distribution([1000 * t["cpu_s"] for t in calls]) != resource["detector_call_cpu_ms"]
    ):
        raise ValueError("call trace differs from the measured archive")
    return visits, list(traces.trace_rows(ident, role, data))


def seal(work, out):
    if (out / "prediction-lock.json").exists():
        raise FileExistsError("diagnostic predictions already sealed")
    plan = trial.source(work)
    stock_lock, _ = trial.stock_sources()
    stock_positions = rows_from(
        whole_iq.checked(trial.STOCK / POSITION, stock_lock["files"][POSITION])
    )
    previous = {r["id"]: r for r in stock_positions if r["method"] == "wide-cfo-stride_control"}
    archive = whole_iq.read(
        whole_iq.checked(trial.STOCK / "resources.json", stock_lock["files"]["resources.json"])
    )
    evidence, comparison, rows, visit_rows, files = {}, {}, [], [], []
    for ident, scheduled in plan["cases"].items():
        control = archive[ident]["control"]
        stock_row, stock_path = stock_attempt(ident, stock_lock, previous[ident], control)
        candidate_row, candidate, native = measured.attempt(
            work, ident, "candidate", plan, method=trial.METHOD
        )
        if any(candidate_row[k] != stock_row[k] for k in PHYSICAL_KEYS):
            raise ValueError(
                "paired position handoffs did not use the same declared tile or request"
            )
        evidence[ident] = dict(control=control, candidate=candidate)
        rows.extend((stock_row, candidate_row))
        prior_visits, prior_trace = trace_bundle(ident, "control", stock_path, control)
        visit_rows.extend(prior_trace)
        case = comparison[ident] = dict(stock_complete=True, candidate_complete=native is not None)
        if native is not None:
            matched_physical(control, candidate, scheduled)
            path = work / ident / "candidate"
            actual_visits, actual_trace = trace_bundle(ident, "candidate", path, candidate)
            case.update(gate_stability(prior_visits, actual_visits, prior_trace, actual_trace))
            case["scout"] = traces.scout_trace(path, actual_trace)
            visit_rows.extend(actual_trace)
            name = f"native/{ident}.json.gz"
            write(out / name, gzip.compress(native.read_bytes(), mtime=0))
            files.append(name)
        service_log = work / ident / "candidate/service.log"
        if service_log.is_file():
            whole_iq.checked(service_log, candidate["service"]["log_sha256"])
            name = f"{ident}.service.log"
            write(out / name, service_log.read_bytes())
            files.append(name)
    traces.protect_resources(evidence)
    pack(out / POSITION, rows)
    pack(out / VISITS, visit_rows)
    save_json(out / "resources.json", evidence)
    save_json(out / PROBES, comparison)
    files.extend((POSITION, VISITS, PROBES, "resources.json", "source-lock.json", "PROTOCOL.md"))
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=list(plan["cases"]),
            files={name: _sha(out / name) for name in files},
        ),
    )


def geographic(rows, references):
    scores = []
    for row in rows:
        case, result = references[row["id"]], row["result"]
        for arm in ARMS:
            endpoint = result["arms"][arm]
            error = distance_km(case["truth"], endpoint["latlon"])
            original = case["reference"]["baseline"][arm]["error_km"]
            scores.append(
                dict(
                    id=row["id"],
                    method=row["method"],
                    arm=arm,
                    status=result["status"],
                    cohort=row["cohort"],
                    reason=result.get("reason"),
                    error_km=error,
                    within_5pct=(error is not None and error <= 1.05 * original),
                    within_10pct=(error is not None and error <= 1.10 * original),
                    conditional_rms_hz=endpoint.get("rf_rms_hz"),
                    frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                    **{f"{name}_km": case["reference"][name][arm]["error_km"] for name in ROLES},
                )
            )
    return scores


def pinned_study(folder, pin):
    lock = whole_iq.read(whole_iq.checked(folder / "prediction-lock.json", pin))
    for name, digest in lock["files"].items():
        whole_iq.checked(folder / name, digest)
    fields = "source-lock.json", "resources.json", POSITION
    plan, resources = (whole_iq.read(folder / name) for name in fields[:2])
    return lock, plan, resources, rows_from(folder / fields[2])


def held_pair(diagnostic):
    fftw, fftw_plan, fftw_resources, fftw_positions = pinned_study(held.REPORT, HELD_FFTW_PIN)
    stock, stock_plan, stock_resources, stock_positions = pinned_study(
        held.prior.REPORT, HELD_STOCK_PIN
    )
    if set(fftw["cases"]) != set(stock["cases"]) or set(fftw["cases"]) != set(held.CASES):
        raise ValueError("held whole-waveform trial changed the independent roster")
    _, primary_stock = trial.stock_sources()
    for plan in (fftw_plan, stock_plan):
        same_receiver(plan["receiver_files"], diagnostic, Path(plan["receiver"]))
        if plan["native_sources"] != diagnostic["native_sources"] or (
            plan["memory_max"],
            plan["swap_max"],
        ) != (diagnostic["memory_max"], diagnostic["swap_max"]):
            raise ValueError("held and diagnostic numerical service scientific inputs changed")
    for role in ("candidate", "scout"):
        if fftw_plan["detectors"][role]["sha256"] != diagnostic["detectors"][role]["sha256"]:
            raise ValueError("held native scout or hinted GLRT binary changed")
    stock_sha = diagnostic["detectors"]["control"]["sha256"]
    if (
        stock_plan["detectors"]["control"]["sha256"] != stock_sha
        or primary_stock["programs"] != stock_plan["programs"]
    ):
        raise ValueError("stock native detector or archived raw decoder changed across cohorts")
    for name, checksum in trial.whole_fftw_runtime.source_identity().items():
        if (
            diagnostic["programs"].get(name) != checksum
            or fftw_plan["programs"].get(name) != checksum
        ):
            raise ValueError("held and diagnostic FFTW native/source runtime closures differ")
    found_stock = {
        r["id"]: r for r in stock_positions if r["method"] == "frontier-whole-iq_control"
    }
    found_fftw = {r["id"]: r for r in fftw_positions if r["method"] == held.METHOD}
    if set(found_stock) != set(held.CASES) or set(found_fftw) != set(held.CASES):
        raise ValueError("held predictions differ from the sealed attempt roster")
    rows = []
    hashes = {}
    for ident in fftw["cases"]:
        s, c = found_stock[ident], found_fftw[ident]
        if any(s[key] != c[key] for key in PHYSICAL_KEYS) or s["mode"] != c["mode"]:
            raise ValueError("held phase-release positions did not use the same recorded request")
        previous = stock_resources[ident]["control"]
        candidate = fftw_resources[ident]["fftw"]
        scheduled = fftw_plan["cases"][ident]
        if (
            previous["detector_sha256"] != stock_sha
            or candidate["detector_sha256"] != diagnostic["detectors"]["candidate"]["sha256"]
            or any(
                stock_plan["cases"][ident][key] != scheduled[key]
                for key in ("request_sha256", "clock_authority", "recording", "orbit_snapshots")
            )
        ):
            raise ValueError("held runtime and request provenance differ")
        matched_physical(previous, candidate, scheduled)
        rows.extend(
            (
                dict(s, method=trial.BASELINE, cohort="manifest-selected held"),
                dict(c, method=trial.METHOD, cohort="manifest-selected held"),
            )
        )
        hashes[ident] = dict(
            stock_native_sha256=s["native_sha256"],
            fftw_native_sha256=c["native_sha256"],
            input_manifest_sha256=previous["input_manifest_sha256"],
            **{k: previous[k] for k in measured.COMMON},
        )
    return rows, dict(held_fftw=HELD_FFTW_PIN, held_stock=HELD_STOCK_PIN, held_cases=hashes)


def chart(key, title, caption, cases, file, evidence, out):
    seal = f"{key}-figure-lock.json"
    save_json(
        out / seal,
        dict(
            cases=cases,
            files={n: _sha(out / n) for n in (file, *evidence)},
        ),
    )
    return dict(
        id=f"diagnostic-whole-fftw-{key}",
        method=trial.METHOD,
        scope="roof",
        cases="sealed",
        title=title,
        caption=caption,
        seal=seal,
        provenance=evidence,
        series=[
            dict(
                key="one",
                label="FFTW scout + hinted wide GLRT",
                file=file,
                value=trial.METHOD,
                native_field="paired_capture_sha256",
            ),
            dict(
                key="stock",
                label="Archived stock wide GLRT",
                file=file,
                value=trial.BASELINE,
                native_field="paired_capture_sha256",
                match=["catalog_sha256", "tile", "original_request_sha256", "mode"],
            ),
        ],
    )


def pooled_summary(scores):
    groups = {"development diagnostic", "manifest-selected held"}
    metrics = {}
    for key in sorted(groups | {"all"}):
        metrics[key] = {}
        for arm in ARMS:
            metrics[key][arm] = {}
            for method in BRANCHES.values():
                match = [
                    r
                    for r in scores
                    if r["arm"] == arm
                    and r["method"] == method
                    and (key == "all" or r["cohort"] == key)
                ]
                metrics[key][arm][method] = dict(
                    attempted=len(match),
                    published=sum(r["error_km"] is not None for r in match),
                    within_5pct=sum(r["within_5pct"] for r in match),
                    within_10pct=sum(r["within_10pct"] for r in match),
                    error_km=distribution([r["error_km"] for r in match]),
                )
    return metrics


def visit_coverage(processed):
    visits = {}
    for row in processed:
        visits.setdefault((row["id"], row["visit"]), {})[row["role"]] = row
    result = {}
    for (ident, _), pair in visits.items():
        counts = result.setdefault(ident, Counter())
        if set(pair) != set(BRANCHES):
            counts["unpaired_visits"] += 1
            continue
        stock, candidate = (pair[role] for role in BRANCHES)
        before, after = (
            any(probe["positive"] for probe in row["probes"]) for row in (stock, candidate)
        )
        counts["compared_valid_visits"] += 1
        counts["stock_positive_visits"] += before
        counts["scout_positive_visits"] += after
        counts["new_positive_visits"] += after and not before
        counts["lost_positive_visits"] += before and not after
        counts["visits_with_identical_stock_gate_retained"] += any(
            candidate["retained_stock_gates"]
        )
    return {ident: dict(counts) for ident, counts in result.items()}


def score(out):
    lock = whole_iq.read(out / "prediction-lock.json")
    for name, digest in lock["files"].items():
        whole_iq.checked(out / name, digest)
    rows = rows_from(out / POSITION)
    resources = whole_iq.read(out / "resources.json")
    plan = whole_iq.read(out / "source-lock.json")
    _, references = held_references(None, lock["cases"])
    scores = geographic(rows, {r["id"]: r for r in references})
    csv_file(out / "scores.csv", scores)
    processed = [r for r in rows_from(out / VISITS) if r["status"] == "processed"]
    save_json(out / VISIT_COVERAGE, visit_coverage(processed))
    timing = timing_rows(resources, processed)
    for row in timing:
        item = resources[row["id"]][row["role"]]
        row["deadline_s"] = plan["limit_s" if row["role"] == "candidate" else "stock_limit_s"]
        row["wall_to_failure_s"] = item.get("wall_to_failure_s")
        row["cpu_to_failure_s"] = item.get("cpu_to_failure_s")
        row["charged_peak_to_failure_bytes"] = item.get("charged_peak_to_failure_bytes")
        row["deadline_service_s"] = item["service"].get("service_wall_s")
        native = [
            r["differential"]
            for r in processed
            if (r["id"] == row["id"] and r["role"] == row["role"] and "differential" in r)
        ]
        row["scout_cpu_s"] = sum(v["scout_cpu_ns"] for v in native) / 1e9 if native else None
    csv_file(out / DEADLINES, timing)
    traces.draw_resources(out, lock["cases"], timing, processed)
    evidence = [
        "prediction-lock.json",
        "resources.json",
        PROBES,
        VISIT_COVERAGE,
        DEADLINES,
        "scores.csv",
    ]
    charts = [
        chart(
            "development",
            "Native FFTW scout and wide GLRT on two complete diagnostic recordings",
            (
                "Both receivers use the same compact phase release and complete saved IQ. "
                "The two recordings contributed development windows. Four capture-era v5 "
                "position policies are shown. Archived stock ran under separate host load."
            ),
            lock["cases"],
            POSITION,
            evidence,
            out,
        )
    ]
    held_rows, authority = held_pair(plan)
    held_ids = sorted({r["id"] for r in held_rows})
    all_ids = sorted(set(lock["cases"]) | set(held_ids))
    _, all_refs = held_references(None, all_ids)
    combined = rows + held_rows
    combined_scores = geographic(combined, {r["id"]: r for r in all_refs})
    save_json(
        out / "pooled-source-authority.json",
        dict(
            authority,
            diagnostic_prediction_lock=_sha(out / "prediction-lock.json"),
            pooling_plan_sha256=_sha(out / "POOLED.md"),
            cohorts={
                "development diagnostic": lock["cases"],
                "manifest-selected held": held_ids,
            },
            detector_sha256={k: v["sha256"] for k, v in plan["detectors"].items()},
            source_closure=trial.whole_fftw_runtime.source_identity(),
        ),
    )
    csv_file(out / "pooled-scores.csv", combined_scores)
    save_json(out / "pooled-summary.json", pooled_summary(combined_scores))
    extra = [
        "POOLED.md",
        "pooled-source-authority.json",
        "pooled-scores.csv",
        "pooled-summary.json",
    ]
    for key, title, caption, batch, ids in (
        (
            "held",
            "Native FFTW scout on two manifest-selected held recordings",
            "Two manifest-selected recordings replayed with full recorded IQ. Both detectors "
            "feed identical compact phase-release code and use the original tile.",
            held_rows,
            held_ids,
        ),
        (
            "pooled",
            "Native FFTW scout on four complete recordings from one roof",
            "Development diagnostics DS26-0237 and DS29-0082 are pooled with manifest-selected "
            "held recordings DS26-0168 and DS29-0604. Four v5 capture-era policies shown. "
            "These are four recordings from one roof.",
            combined,
            all_ids,
        ),
    ):
        file = f"{key}-positions.jsonl.gz"
        pack(out / file, batch)
        charts.append(chart(key, title, caption, ids, file, [*evidence, *extra], out))
    save_json(out / "figures.json", dict(version=1, charts=charts))
    screening_figures.generate(out / "charts", evidence=out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("seal", "score"))
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    parser.add_argument(
        "--work", type=local_output, default=Path("/var/tmp/leo-diagnostic-whole-20261119")
    )
    args = parser.parse_args()
    if args.mode == "seal":
        seal(args.work, args.out)
    else:
        score(args.out)
