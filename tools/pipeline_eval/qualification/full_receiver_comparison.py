"""Build a matched full-roof comparison from the sealed receiver exports."""

import argparse
import json
from collections import Counter
from pathlib import Path

from .. import corpus
from ..__main__ import encoded, local_output, read_predictions, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution, thresholds
from . import (
    native_clock_full,
    native_joint_trial,
    native_lean_eval,
    secant_full,
    train_update_trial,
)
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

ROOT = corpus.REPO
SCREEN = secant_full.REPORT.parent
REPORT = SCREEN / "factors/full-comparison"
COMPACT = secant_full.METHOD
JOINT = native_joint_trial.METHOD
TRAIN = train_update_trial.train_update.METHOD
CLOCK = native_clock_full.METHOD
STUDIES = (
    (COMPACT, "Compact v5 secant", "one"),
    (JOINT, "Native joint orbits", "stock"),
    (TRAIN, "Native training update", "one_native_factors"),
    (CLOCK, "Native smooth clock", "all_visits"),
)
PREDICTIONS = "positions.jsonl.gz"
STAGES = {JOINT: "joint_backend", TRAIN: "fixed_owner_backend", CLOCK: "clock_backend"}


def sha(path):
    return secant_full.phase.digest(path)


def read(path):
    return json.loads(path.read_bytes())


def roster_matches(ids, expected, source):
    if len(ids) != len(expected) or set(ids) != set(expected):
        raise ValueError(f"{source} does not cover its entire bound roster")


def seal(folder, receipt_name, required):
    receipt = read(folder / receipt_name)
    files = receipt["files"]
    if not set(required) <= files.keys() or any(Path(name).name != name for name in files):
        raise ValueError(f"{receipt_name} does not seal the required local evidence")
    secant_full._verify_files(folder, files)
    return receipt


def require_fields(row, fields):
    for name, expected in fields.items():
        if row.get(name) != expected:
            raise ValueError(f"{row.get('id', 'source')} has a different {name}")


def full_roster(refs, inputs):
    if Counter(ref["group"] for ref in refs.values()) != {"DS26": 127, "DS29": 8}:
        raise ValueError("expected the frozen DS26 127 and DS29 eight roof recordings")
    return {key: inputs[key] for key in sorted(refs)}


def verify_roles(originals, refs, inputs, audit_archive):
    roster_matches(originals, inputs, "original v5 receipts")
    for ident, matched in originals.items():
        roster_matches(matched, ROLES, ident)
        if audit_archive:
            expected = secant_full.phase._original_v5_bindings(inputs[ident])
            if matched != expected:
                raise ValueError(f"{ident} original v5 execution no longer matches its seal")
        for role in ROLES:
            for fields in ("request_sha256", "execution_sha256"):
                digest = matched[role][fields].removeprefix("sha256:")
                if len(bytes.fromhex(digest)) != 32:
                    raise ValueError(f"{ident} original v5 {role} has an invalid digest")
            for arm in ARMS:
                ref = refs[ident]["reference"][role][arm]
                actual = distance_km(ref["latlon"], refs[ident]["truth"])
                if actual is None or abs(actual - ref["error_km"]) > 1e-6:
                    raise ValueError(f"{ident} original v5 {role} score changed")
        if audit_archive:
            from .native_joint_full_results import original_scores

            original_scores(ident, refs[ident], matched, refs[ident]["truth"])


def compact_predictions(inputs, refs, *, audit_archive=False):
    folder = secant_full.REPORT
    name = f"{COMPACT}.jsonl.gz"
    stock_name = f"{secant_full.STOCK}.jsonl.gz"
    receipt = seal(
        folder, "receipt.json", (name, stock_name, "plan.json", "original-v5-inputs.json")
    )
    plan = read(folder / "plan.json")
    roster_matches(receipt["cases"], inputs, "compact receipt")
    roster_matches(plan["cases"], inputs, "compact plan")
    source = secant_full.secant.frozen_sources()
    require_fields(
        receipt, dict(sources=source, scientific_source=secant_full.phase.v5_lean.SOURCE_SHA256)
    )
    require_fields(plan, dict(source_sha256=source, protocol_sha256=sha(folder / "PROTOCOL.md")))
    prior = {}
    timing, confirmation = secant_full.secant.TIMING, secant_full.secant.REPORT
    for key, location, stem, filename in (
        ("prior_timing", timing, "prediction-lock.json", "secant-positions.jsonl.gz"),
        ("prior_confirmation", confirmation, "receipt.json", name),
    ):
        if receipt["prior_seals"][key] != sha(location / stem):
            raise ValueError(f"{key} archive differs from the compact seal")
        sources = seal(location, stem, (filename,))
        results = read_predictions(location / filename)
        roster_matches(results, sources["cases"], key)
        prior[key] = results
    prior_ids = {ident: kind for kind, rows in prior.items() for ident in rows}
    fresh = set(plan["fresh_cases"])
    if (
        {key: len(rows) for key, rows in prior.items()}
        != {"prior_timing": 6, "prior_confirmation": 8}
        or len(prior_ids) != 14
        or prior_ids != plan["prior_cases"]
        or fresh & prior_ids.keys()
        or fresh | prior_ids.keys() != inputs.keys()
        or len(fresh) != 121
        or len(plan["fresh_cases"]) != len(fresh)
        or not 0 < receipt["run"]["wall_s"] <= receipt["max_replay_wall_s"]
        or receipt["run"]["attempted"] != len(fresh)
        or receipt["run"]["fresh_statuses"] != {"ok": 121}
    ):
        raise ValueError("the five-refresh compact run differs from its recorded budget or roster")

    rows = read_predictions(folder / name)
    stock = read_predictions(folder / stock_name)
    roster_matches(rows, inputs, "compact positions")
    roster_matches(stock, inputs, "compact request control")
    for ident, row in rows.items():
        item = inputs[ident]
        binding = dict(
            native_sha256=item["native"]["sha256"],
            catalog_sha256=item["catalog"]["sha256"],
            frozen_request_sha256=item["request"]["sha256"],
            tile=item["regions"][0],
        )
        require_fields(row, dict(binding, method=COMPACT, source_sha256=source))
        require_fields(stock[ident], dict(binding, method=secant_full.STOCK))
        require_fields(
            row, {key: stock[ident][key] for key in ("input_sha256", "resolved_request_sha256")}
        )
        kind = prior_ids.get(ident, "fresh_full_panel")
        require_fields(row, dict(source=kind))
        if ident in prior_ids:
            saved = prior[kind][ident]
            require_fields(
                row, dict(result=saved["result"], prior_input_sha256=saved["input_sha256"])
            )
        elif not 0 < row["worker_wall_s"] <= row["deadline_s"] <= receipt["deadline_s"]:
            raise ValueError(f"{ident} lacks its measured compact worker interval")
        else:
            require_fields(row, dict(implementation_sha256=plan["cli_implementation_sha256"]))
        metrics = row["result"]["metrics"]
        if (
            row["result"]["status"] != "ok"
            or set(row["result"]["arms"]) != set(ARMS)
            or not metrics["initial_phase_refresh_counts"]
            or set(metrics["initial_phase_refresh_counts"]) != {5}
            or metrics["kernel_sha256"] != source["orbit_projector.c"]
            or metrics["position_optimizer"]["calls"] < 1
            or not {"native_preparation", "initial", "conservative", "family", "signed", "cavity"}
            <= metrics["stage_s"].keys()
        ):
            raise ValueError(f"{ident} is missing the measured five-refresh compact stages")
    originals = read(folder / "original-v5-inputs.json")
    verify_roles(originals, refs, inputs, audit_archive)
    return rows, ledger_entry(folder, name, "receipt.json", receipt)


def native_sources(joint, train, clock):
    legacy = SCREEN / "inference"
    source = joint["source"]
    joint_deployment = legacy / "native-lean/deployment.json"
    records = {
        "deployment": joint_deployment,
        "joint": legacy / "joint-orbits/source-lock.json",
        "native": legacy / "native-lean/source-lock.json",
        "protocol": legacy / "native-joint/PROTOCOL.md",
        "runner": Path(native_joint_trial.__file__),
        "wrapper": native_joint_trial.WORKER,
    }
    require_fields(source, {key: sha(path) for key, path in records.items()})
    secant_full._verify_files(ROOT, read(records["joint"])["files"])
    dep = read(joint_deployment)["files"]
    for name, meta in dep.items():
        if name == "/worker/main.py":
            path = native_lean_eval.WORKER
        elif name.startswith("/source/"):
            path = ROOT / "src" / name.removeprefix("/source/")
        else:
            path = ROOT / name.removeprefix("/worker/")
        if sha(path) != meta["sha256"]:
            raise ValueError(f"native deployed source changed: {path}")
    require_fields(
        train["sources"],
        dict(
            native=source,
            solver=sha(Path(train_update_trial.train_update.__file__)),
            worker=sha(train_update_trial.WORKER),
            supervisor=sha(Path(train_update_trial.__file__)),
            protocol=sha(train_update_trial.REPORT / "PROTOCOL.md"),
            parent_roster=sha(native_clock_full.panel.REPORT / "roster.json"),
        ),
    )
    require_fields(
        clock["source"],
        dict(
            source,
            clock_solver=sha(Path(native_clock_full.joint_clock_model.__file__)),
            clock_selector=sha(native_clock_full.WORKER),
        ),
    )
    require_fields(
        clock,
        dict(
            native_joint_lock_sha256=sha(native_clock_full.panel.REPORT / "prediction-lock.json"),
            protocol_sha256=sha(native_clock_full.REPORT / "PROTOCOL.md"),
            runner_sha256=sha(Path(native_clock_full.__file__)),
        ),
    )
    require_fields(
        joint,
        dict(
            compact_reference_receipt_sha256=sha(secant_full.REPORT / "receipt.json"),
            protocol_sha256=sha(native_clock_full.panel.REPORT / "PROTOCOL.md"),
            runner_sha256=sha(Path(native_clock_full.panel.__file__)),
        ),
    )


def native_roof(plan, records, inputs, method, *, matched=None):
    jobs = plan["cases"]
    roof = [job for job in jobs if job["cohort"] == "roof"]
    roster_matches([job["id"] for job in roof], inputs, method)
    roster_matches([job["id"] for job in jobs], records, method)
    selected = {}
    for job in roof:
        ident = job["id"]
        item = inputs[ident]
        packet, _ = native_lean_eval.request(item, "native")
        require_fields(job, dict(recording=ident, packet=packet))
        row = records[ident]
        require_fields(
            row,
            dict(
                id=ident,
                recording=ident,
                cohort="roof",
                method=method,
                tile=packet["offer"],
                input_sha256=corpus._sha(encoded(packet)),
                native_sha256=item["native"]["sha256"],
                catalog_sha256=item["catalog"]["sha256"],
                address_space_limit_mib=512,
            ),
        )
        status, metrics = row["result"]["status"], row["result"]["metrics"]
        if (
            status not in ("ok", "withheld")
            or set(row["result"]["arms"]) != set(ARMS)
            or not row.get("observation_sha256")
            or not 0 < row["proc_memory_kib"]["VmPeak"] <= 512 * 1024
            or not {"archive_and_peak_selection", "graph", STAGES[method]} <= row["stages"].keys()
            or (method == TRAIN and metrics.get("association_passes") != 3)
            or (method == CLOCK and metrics.get("fixed_assignment_clock") is not True)
        ):
            raise ValueError(f"{ident} does not attest its measured native boundary")
        if matched is not None:
            require_fields(row, dict(observation_sha256=matched[ident]["observation_sha256"]))
        selected[ident] = row
    return selected


def ledger_entry(folder, filename, lock_name, lock):
    plan = read(folder / "plan.json")
    return dict(
        prediction=str((folder / filename).relative_to(ROOT)),
        sha256=lock["files"][filename],
        receipt=str((folder / lock_name).relative_to(ROOT)),
        receipt_sha256=sha(folder / lock_name),
        files=lock["files"],
        plan=str((folder / "plan.json").relative_to(ROOT)),
        replay=lock.get("run", {k: lock[k] for k in ("wall_s", "statuses") if k in lock}),
        caps={k: plan[k] for k in plan if k.endswith("_s") and k != "priority_wall_s"},
    )


def native_predictions(inputs):
    outputs, plans, receipts = {}, {}, {}
    for method, folder in (
        (JOINT, native_clock_full.panel.REPORT),
        (TRAIN, train_update_trial.REPORT),
        (CLOCK, native_clock_full.REPORT),
    ):
        receipt = seal(folder, "prediction-lock.json", (PREDICTIONS, "plan.json"))
        pack = read_predictions(folder / PREDICTIONS)
        roster_matches(receipt["cases"], pack, method)
        plan = read(folder / "plan.json")
        if method != JOINT and plan["cases"] != plans[JOINT]["cases"]:
            raise ValueError(f"{method} changes the bound native requests")
        run = receipt.get("run", receipt)
        cap = plan.get("wall_cap_s", plan.get("cap_s"))
        if not 0 < run["wall_s"] <= cap or run["statuses"] != Counter(
            row["result"]["status"] for row in pack.values()
        ):
            raise ValueError(f"{method} differs from its measured replay budget or status receipt")
        outputs[method] = native_roof(plan, pack, inputs, method, matched=outputs.get(JOINT))
        plans[method] = plan
        receipts[method] = ledger_entry(folder, PREDICTIONS, "prediction-lock.json", receipt)
    native_sources(*(plans[method] for method in (JOINT, TRAIN, CLOCK)))
    return outputs, receipts


def paired_threshold(candidate, reference, factor):
    return candidate is not None and reference is not None and candidate <= factor * reference


def score_rows(refs, methods):
    for method, records in methods.items():
        for ident, ref in refs.items():
            record = records[ident]
            for arm in ARMS:
                result = record["result"]
                point = result["arms"][arm]
                reference = ref["reference"]["baseline"][arm]["error_km"]
                error = distance_km(point["latlon"], ref["truth"])
                yield dict(
                    id=ident,
                    method=method,
                    dataset=ref["group"],
                    arm=arm,
                    status=result["status"],
                    reason=result.get("reason"),
                    error_km=error,
                    baseline_km=reference,
                    within_v5_5pct=paired_threshold(error, reference, 1.05),
                    within_v5_10pct=paired_threshold(error, reference, 1.10),
                    rms_hz=point.get("rf_rms_hz"),
                    wall_s=record.get("worker_wall_s"),
                    cpu_s=record.get("worker", {}).get("cpu_s"),
                    rss_kib=record.get("proc_memory_kib", {}).get("VmHWM"),
                    solver_wall_s=record.get("stages", {})
                    .get(STAGES.get(method), {})
                    .get("wall_s"),
                    compact_cavity_wall_s=result["metrics"].get("stage_s", {}).get("cavity"),
                    measurement=record.get("source", "fresh_native"),
                    **{
                        f"{role}_km": ref["reference"][role][arm]["error_km"]
                        for role in ROLES
                        if role != "baseline"
                    },
                )


def outcomes(rows, refs):
    output = []
    for dataset in ("all", "DS26", "DS29"):
        for method, _, _ in STUDIES:
            for arm in ARMS:
                group = [
                    r
                    for r in rows
                    if r["method"] == method
                    and r["arm"] == arm
                    and (dataset == "all" or r["dataset"] == dataset)
                ]
                errors = [r["error_km"] for r in group]
                paired = [
                    r for r in group if r["error_km"] is not None and r["baseline_km"] is not None
                ]
                output.append(
                    dict(
                        dataset=dataset,
                        method=method,
                        arm=arm,
                        attempts=len(group),
                        published=len(paired),
                        statuses=dict(Counter(r["status"] for r in group)),
                        within_km=thresholds(errors),
                        error_km=distribution(errors),
                        within_v5_5pct=sum(r["within_v5_5pct"] for r in group),
                        within_v5_10pct=sum(r["within_v5_10pct"] for r in group),
                        paired_error_delta_km=distribution(
                            r["error_km"] - r["baseline_km"] for r in paired
                        ),
                        conditional_rms_hz=distribution(r["rms_hz"] for r in group),
                        published_rms_hz=distribution(
                            r["rms_hz"] for r in group if r["error_km"] is not None
                        ),
                        original_v5={
                            role: distribution(
                                refs[r["id"]]["reference"][role][arm]["error_km"] for r in group
                            )
                            for role in ROLES
                        },
                        **{
                            key: distribution(r[key] for r in group)
                            for key in (
                                "wall_s",
                                "cpu_s",
                                "rss_kib",
                                "solver_wall_s",
                                "compact_cavity_wall_s",
                            )
                        },
                    )
                )
    return output


def calibration(rows, refs, methods):
    output = {}
    for method, records in methods.items():
        by_arm = {
            arm: {r["id"]: r for r in rows if r["method"] == method and r["arm"] == arm}
            for arm in ARMS
        }
        c0, fit = (by_arm[a] for a in ARMS)
        paired = [
            i for i in refs if c0[i]["error_km"] is not None and fit[i]["error_km"] is not None
        ]
        rf = [i for i in refs if c0[i]["rms_hz"] is not None and fit[i]["rms_hz"] is not None]
        output[method] = dict(
            paired_published_error_delta_km=distribution(
                fit[i]["error_km"] - c0[i]["error_km"] for i in paired
            ),
            paired_published_coordinate_shift_km=distribution(
                distance_km(*(records[i]["result"]["arms"][a]["latlon"] for a in ARMS))
                for i in paired
            ),
            paired_conditional_rms_delta_hz=distribution(
                fit[i]["rms_hz"] - c0[i]["rms_hz"] for i in rf
            ),
            published_improved=sum(fit[i]["error_km"] < c0[i]["error_km"] for i in paired),
        )
    return output


def cross_receiver(rows, methods):
    keyed = {(r["method"], r["arm"], r["id"]): r for r in rows}
    pairs = []
    for method in (JOINT, TRAIN, CLOCK):
        controls = (COMPACT,) if method == JOINT else (COMPACT, JOINT)
        for control in controls:
            for arm in ARMS:
                a, b = (methods[name] for name in (method, control))
                common = [
                    ident
                    for ident in a
                    if a[ident]["result"]["arms"][arm]["latlon"] is not None
                    and b[ident]["result"]["arms"][arm]["latlon"] is not None
                ]
                pairs.append(
                    dict(
                        method=method,
                        control=control,
                        arm=arm,
                        common_fixes=len(common),
                        location_shift_km=distribution(
                            distance_km(
                                *(x[ident]["result"]["arms"][arm]["latlon"] for x in (a, b))
                            )
                            for ident in common
                        ),
                        paired_excess_error_km=distribution(
                            keyed[method, arm, ident]["error_km"]
                            - keyed[control, arm, ident]["error_km"]
                            for ident in common
                        ),
                    )
                )
    return pairs


def publish(output, refs, methods, ledger, audit_archive):
    files, series = {}, []
    for method, label, key in STUDIES:
        name = f"{method}.jsonl.gz"
        source = ledger[method]
        write(output / name, (ROOT / source["prediction"]).read_bytes())
        if sha(output / name) != source["sha256"]:
            raise ValueError(f"{method} archive changed after verification")
        files[name] = source["sha256"]
        spec = dict(key=key, label=label, file=name, value=method)
        if method != COMPACT:
            spec["where"] = {"cohort": "roof"}
            spec["match"] = ["native_sha256", "catalog_sha256", "tile"]
        series.append(spec)
    rows = list(score_rows(refs, methods))
    csv_file(output / "scores.csv", rows)
    save_json(
        output / "summary.json",
        dict(
            roof=dict(DS26=127, DS29=8),
            groups=outcomes(rows, refs),
            calibration=calibration(rows, refs, methods),
            cross_receiver=cross_receiver(rows, methods),
        ),
    )
    save_json(
        output / "sources.json",
        dict(
            methods=ledger,
            audited_original_executions=audit_archive,
            frozen_corpus_sha256=sha(corpus.FROZEN / "provenance.json"),
            aggregator_sha256=sha(Path(__file__)),
        ),
    )
    files.update({key: sha(output / key) for key in ("summary.json", "scores.csv", "sources.json")})
    save_json(output / "roof-lock.json", dict(cases=sorted(refs), files=files))
    save_json(
        output / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="full-receiver-comparison-roof135",
                    method="full_receiver_comparison",
                    scope="roof",
                    cases="roof135",
                    title="Full-roof position accuracy on 135 recordings",
                    caption=(
                        "Matched recordings, causal catalogues and supplied regions. Compact v5 "
                        "runs its full cavity workflow. The native receivers rebuild identical "
                        "anonymous Graph tracks for three different position fits."
                    ),
                    seal="roof-lock.json",
                    provenance=["sources.json", "summary.json", "scores.csv"],
                    series=series,
                )
            ],
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPORT)
    parser.add_argument("--audit-original-executions", action="store_true")
    args = parser.parse_args()
    frozen, inventory = _frozen_roof()
    inputs = full_roster(frozen, inventory)
    compact, compact_ledger = compact_predictions(
        inputs, frozen, audit_archive=args.audit_original_executions
    )
    methods, ledger = native_predictions(inputs)
    publish(
        local_output(args.output),
        frozen,
        dict(methods, **{COMPACT: compact}),
        dict(ledger, **{COMPACT: compact_ledger}),
        args.audit_original_executions,
    )


if __name__ == "__main__":
    main()
