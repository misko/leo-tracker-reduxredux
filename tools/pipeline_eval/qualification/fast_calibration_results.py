"""Score sealed detector-bias transfer and matched complete compact endpoints."""

import argparse
import csv
from collections import Counter
from pathlib import Path

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution, validate_result
from . import cascade_audit_trial as cascade
from . import fast_calibration_model as model
from . import fast_calibration_trial as trial
from . import one_lane_roster as roster
from . import scout_stage_figures as plot
from .fresh_replay_results import geographic, sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .screening_figures import generate
from .whole_pressure_trial import rows_from

STOCK = "fast_calibration_stock"
ORIGINAL = "fast_calibration_original"
CALIBRATED = "fast_calibration_corrected"
REVERSE = "fast_calibration_reverse"


def endpoint_rows(work, plan, rule):
    files, outcomes = [], []
    out = trial.REPORT
    source = sealed(cascade.REPORT, "endpoint-lock.json")
    parent_hold = whole_iq.read(
        whole_iq.checked(cascade.REPORT / "source-lock.json", source["files"]["source-lock.json"])
    )
    if parent_hold["release"] != plan["release"]:
        raise ValueError("archived fast and original controls used another compact release")
    refs = whole_iq.checked(
        cascade.REPORT / "endpoints.jsonl.gz", source["files"]["endpoints.jsonl.gz"]
    )
    controls = {(r["id"], r["condition"]): r for r in rows_from(refs)}
    for ident, meta in plan["inputs"].items():
        for mode, method, digest in (
            ("fast", STOCK, meta["archive"]["native_sha256"]),
            ("original", ORIGINAL, meta["binding"]["paired_capture_sha256"]),
        ):
            row = cascade.bind_control(controls[ident, mode], meta["binding"], mode, digest)
            outcomes.append(dict(row, method=method, cohort="held bias transfer"))
    for job in plan["jobs"]:
        ident, mode = job["id"], job["condition"]
        directory = work / ident / mode
        current = whole_iq.read(directory / "fit.json")
        if any(v != current[k] for k, v in job.items()):
            raise ValueError("held fit terminal differs from its frozen raw-only input")
        native = whole_iq.read(
            whole_iq.checked(directory / "recording/native.json", job["native_sha256"])
        )
        parent = roster.stock_document(plan["inputs"][ident]["archive"])
        expected, changed = model.apply(
            parent, rule["models"][rule["selected"]], 1 if mode == "corrected" else -1
        )
        if (
            encoded(native["source"]["probes"]) != encoded(expected["source"]["probes"])
            or changed != job["changed_candidates"]
            or any(
                native[k] != parent[k]
                for k in (
                    "schema_version",
                    "delivery_clocks",
                    "clock_anchor",
                    "last_sample_counter",
                )
            )
            or native["provenance"]["excluded_windows"] != parent["provenance"]["excluded_windows"]
        ):
            raise ValueError("the frozen correction changed physical support or candidate gates")
        whole_iq.checked(directory / "recording/request.json", job["prepared_request_sha256"])
        whole_iq.checked(directory / "service.log", current["log_sha256"])
        validate_result(current["result"])
        outcomes.append(dict(current, cohort="held bias transfer"))
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.name != "native.json":
                relative = str(Path("receipts") / path.relative_to(work))
                write(out / relative, path.read_bytes())
                files.append(relative)
    return outcomes, files, _sha(cascade.REPORT / "endpoint-lock.json")


def residual_detail(rows, chosen):
    stages = {
        "stock": [r["difference_hz"] for r in rows],
        "corrected": model.residual(rows, chosen),
        "reverse": model.residual(rows, chosen, -1),
    }
    return {
        method: dict(signed=distribution(values), absolute=distribution(list(map(abs, values))))
        for method, values in stages.items()
    }


def residuals(plan, rule):
    chosen = rule["models"][rule["selected"]]
    groups, archives, bindings, extensions, _ = roster.inventory()
    collected, proofs, details, stage = [], {}, {}, {}
    for ident in plan["cases"]:
        if plan["inputs"][ident] != dict(archive=archives[ident], binding=bindings[ident]):
            raise ValueError("held evaluation inputs changed after position freeze")
        case, _, fast = trial.fast(ident, archives, bindings, extensions)
        original = trial.original(case)
        rows, counts = model.pairs(ident, fast, original)
        collected.extend(rows)
        details[ident] = residual_detail(rows, chosen)
        proofs[ident] = dict(
            **counts,
            edge=fast["source"]["probes"][0]["edge"],
            scheduled_visits=fast["provenance"]["window_count"],
            valid_visits=fast["provenance"]["processed_windows"],
            literal_abs_epoch_samples=distribution(
                [abs(r["epoch_difference_samples"]) for r in rows]
            ),
        )
    for edge in (*trial.EDGES, "all"):
        picked = [r for r in collected if edge == "all" or r["edge"] == edge]
        stage[edge] = residual_detail(picked, chosen)
    return collected, proofs, details, stage


def score_summary(positions, score_rows):
    result = {}
    for method in (STOCK, ORIGINAL, CALIBRATED, REVERSE):
        result[method] = {}
        for arm in ARMS:
            data = [r for r in score_rows if (r["method"], r["arm"]) == (method, arm)]
            values = [r["error_km"] for r in data if r["error_km"] is not None]
            rms = [r["conditional_rms_hz"] for r in data if r["conditional_rms_hz"] is not None]
            result[method][arm] = dict(
                total=len(data),
                published=len(values),
                status=dict(Counter(r["status"] for r in data)),
                error_km=distribution(values),
                conditional_rms_hz=distribution(rms),
                within_5pct=sum(bool(r["within_5pct"]) for r in data),
                within_10pct=sum(bool(r["within_10pct"]) for r in data),
            )
    by_key = {(r["id"], r["method"], r["arm"]): r for r in score_rows}
    facts = {(r["id"], r["method"]): r["result"]["metrics"] for r in positions}
    paired = []
    for row in positions:
        if row["method"] not in (CALIBRATED, REVERSE):
            continue
        for arm in ARMS:
            ident, method = row["id"], row["method"]
            fast = by_key[ident, STOCK, arm]
            result_row = by_key[ident, method, arm]
            coords = [
                r["result"].get("arms", {}).get(arm, {}).get("latlon")
                for r in positions
                if r["id"] == ident and r["method"] in (STOCK, method)
            ]
            changed = distance_km(*coords)
            old_error, new_error = fast["error_km"], result_row["error_km"]
            change = (
                new_error - old_error if old_error is not None and new_error is not None else None
            )
            paired.append(
                dict(
                    id=ident,
                    method=method,
                    arm=arm,
                    stock_error_km=old_error,
                    calibrated_error_km=new_error,
                    geographic_delta_km=change,
                    pt_displacement_km=changed,
                    stock_rf_rms_hz=fast["conditional_rms_hz"],
                    calibrated_rf_rms_hz=result_row["conditional_rms_hz"],
                    stock_observations=facts[ident, STOCK].get("observations"),
                    calibrated_observations=facts[ident, method].get("observations"),
                    stock_tracks=facts[ident, STOCK].get("tracks"),
                    calibrated_tracks=facts[ident, method].get("tracks"),
                    status=result_row["status"],
                )
            )
    return result, paired


def resources(positions):
    path = whole_iq.checked(
        cascade.REPORT / "costs.csv",
        whole_iq.read(cascade.REPORT / "figure-lock.json")["files"]["costs.csv"],
    )
    with path.open(newline="") as stream:
        cost = {r["id"]: r for r in csv.DictReader(stream)}
    timing = cascade.fixed.SCREEN / "latency-and-support/complete-timing"
    raw_lock = whole_iq.read(timing / "prediction-lock.json")
    raw_path = whole_iq.checked(timing / "resources.csv", raw_lock["files"]["resources.csv"])
    with raw_path.open(newline="") as stream:
        stock = {r["id"]: r for r in csv.DictReader(stream) if r["method"] == cascade.fixed.FOUR}
    bases = {r["id"]: r for r in positions if r["method"] == STOCK}
    output = []
    for r in positions:
        if r["method"] not in (CALIBRATED, REVERSE):
            continue
        ident = r["id"]
        orig = cost[ident]
        raw = stock[ident]
        base = bases[ident]
        if (
            raw["native_sha256"] != base["native_sha256"]
            or raw["capture_sha256"] != base["paired_capture_sha256"]
            or raw["request_sha256"] != base["original_request_sha256"]
            or raw["full_raw_verified"] != "True"
        ):
            raise ValueError("archived fast acquisition timing has unmatched physical inputs")
        stats = r["position_resources"] or {}
        output.append(
            dict(
                id=ident,
                method=r["method"],
                fast_acquisition_cpu_s=orig["fast_detector_cpu_s"],
                fast_acquisition_measured=orig["fast_detector_measured"],
                fast_acquisition_wall_p50_ms=float(raw["detector_call_wall_p50_ms"]),
                fast_acquisition_wall_p95_ms=float(raw["detector_call_wall_p95_ms"]),
                original_acquisition_cpu_s=orig["original_detector_cpu_s"],
                original_acquisition_measured=orig["original_detector_measured"],
                stock_compact_cpu_s=orig["measured_fast_fit_cpu_s"],
                calibration_cpu_ms=r["calibration_cpu_ns"] / 1e6,
                compact_cpu_s=stats.get("cpu_s"),
                compact_wall_s=r["supervisor_wall_s"],
                changed_candidates=r["changed_candidates"],
            )
        )
    return output


def plot_residual(out, stages):
    fig, axes = plot.canvas(
        "Signed CFO residuals on shared held pilots",
        "Six disjoint recordings · no position truth in model fitting",
        "The same literal pairs are evaluated in all three policies. "
        "Aliases and gate-only branches are counted separately.",
    )
    labels = ["Full fast", "Frozen correction", "Reverse sign"]
    for ax, edge in zip(axes, trial.EDGES, strict=True):
        stats = [stages[edge][k]["absolute"] for k in ("stock", "corrected", "reverse")]
        plot.paired(
            ax,
            labels,
            [(r["p50"], r["p95"]) for r in stats],
            title=f"{edge.capitalize()} edge",
            xlabel="Absolute signed CFO residual (Hz)",
        )
    plot.key(fig, "Median", "95th percentile")
    fig.savefig(out / "stage.png", dpi=165, facecolor="white")
    fig.savefig(out / "stage.pdf", facecolor="white", metadata={"CreationDate": None})
    plot.plt.close(fig)


def publish(work):
    plan, rule = trial.plan(work), trial.frozen_model(work)
    positions, files, reference_receipt = endpoint_rows(work, plan, rule)
    out = trial.REPORT
    pack(out / "positions.jsonl.gz", positions)
    assets = (
        "cohort-lock.json",
        "model-lock.json",
        "prediction-plan.json",
        "positions.jsonl.gz",
        "training-pairs.jsonl.gz",
        "PROTOCOL.md",
    )
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=plan["cases"],
            files={name: _sha(out / name) for name in (*assets, *files)},
            original_four_region_endpoint_sha256=reference_receipt,
            publisher_sha256=_sha(Path(__file__)),
        ),
    )
    held, counts, per_case, per_edge = residuals(plan, rule)
    pack(out / "held-pairs.jsonl.gz", held)
    _, sources = held_references(None, plan["cases"])
    refs = {r["id"]: r for r in sources}
    scores = geographic(positions, refs)
    csv_file(out / "scores.csv", scores)
    summary, paired = score_summary(positions, scores)
    csv_file(out / "paired.csv", paired)
    csv_file(out / "costs.csv", resources(positions))
    csv_file(
        out / "v5-controls.csv",
        [
            dict(
                id=ident,
                role=role,
                arm=arm,
                error_km=r["reference"][role][arm]["error_km"],
                conditional_rms_hz=r["reference"][role][arm].get("rf_rms_hz"),
            )
            for ident, r in refs.items()
            for role in ROLES
            for arm in ARMS
        ],
    )
    save_json(
        out / "audit.json",
        dict(
            counts=counts,
            residuals_by_case=per_case,
            residuals_by_edge=per_edge,
            position=summary,
        ),
    )
    csv_file(
        out / "stage.csv",
        [
            dict(
                edge=edge,
                policy=label,
                n=d["signed"]["n"],
                signed_median_hz=d["signed"]["p50"],
                absolute_median_hz=d["absolute"]["p50"],
                absolute_p95_hz=d["absolute"]["p95"],
            )
            for edge, modes in per_edge.items()
            for label, d in modes.items()
        ],
    )
    file = (
        "audit.json",
        "held-pairs.jsonl.gz",
        "scores.csv",
        "paired.csv",
        "costs.csv",
        "v5-controls.csv",
        "stage.csv",
    )
    save_json(
        out / "score-lock.json",
        dict(
            prediction_lock_sha256=_sha(out / "prediction-lock.json"),
            files={f: _sha(out / f) for f in file},
        ),
    )
    save_json(
        out / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="fast-calibration-position",
                    title="Position after shared-pilot CFO calibration",
                    method=CALIBRATED,
                    scope="roof",
                    cases="sealed",
                    seal="prediction-lock.json",
                    caption="A signed CFO correction from eight other sessions was applied "
                    "to complete held fast factors before normal compact rediscovery.",
                    provenance=["model-lock.json", "prediction-plan.json"],
                    series=[
                        dict(
                            key=key,
                            file="positions.jsonl.gz",
                            value=method,
                            label=title,
                            native_field="paired_capture_sha256",
                            match=cascade.fixed.BINDINGS,
                        )
                        for key, method, title in (
                            ("one", CALIBRATED, "Fast with frozen CFO correction"),
                            ("stock", STOCK, "Unchanged full fast"),
                            ("one_native_factors", ORIGINAL, "Full original factors"),
                        )
                    ],
                )
            ],
        ),
    )
    generate(out / "charts", evidence=out)
    plot_residual(out, per_edge)
    save_json(
        out / "stage-lock.json",
        dict(
            files={
                name: _sha(out / name)
                for name in ("stage.pdf", "stage.png", "stage.csv", "score-lock.json")
            }
        ),
    )
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="fast-calibration-residuals",
            title="Held signed CFO residual transfer",
            sample="Six sessions, matched literal gated winners",
            boundary="Archived four-region and original physical factors through CFO correction",
            note="All residual panels use the same literal pairs. Correction, acquisition and "
            "compact timing are separate measured boundaries.",
            seal="stage-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output, nargs="?", default=trial.WORK)
    publish(parser.parse_args().work)
