"""Qualify the checked predictive precision option in one saved publication."""

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

import ds30_0359_composed_saved as composed


PROTOCOL = HERE / "ds30-0359-precision-saved-protocol.md"
CLEAN = Path("/dev/shm/leo-v3-0359-composed-saved-result01")
CLEAN_SHA = "8cf7d2053ae88597c390739990c849e33c755412d86303eafd7cae5170251166"
CLEAN_SEAL = "247585dfc40e81d87aebb7e255cb9465b8080e00fba46909ae3547a8125629e8"
FRESH = HERE / "measurements/ds30-0359-installed-control.json.gz"
FRESH_SHA = "f7cbe75f5c29343b9c9ddc0f5118c2db27d72673b9da6f8346aa17024c116200"


def controls():
    from empty_bootstrap import checked

    checked(CLEAN / "prediction-seal.json", CLEAN_SEAL)
    clean = json.loads(checked(CLEAN / "result.json", CLEAN_SHA))
    fresh = json.loads(gzip.decompress(checked(FRESH, FRESH_SHA)))
    if (not clean["qualified"] or not fresh["qualified"]
            or clean["admission"]["job_sha256"] != composed.JOB_PIN
            or fresh["admission"]["job_sha256"] != composed.JOB_PIN
            or clean["prediction_sha256"] != CLEAN_SEAL
            or fresh["candidate_clock"] != clean["clock"]):
        raise ValueError("The two sealed saved controls differ from the enrolled candidate and job")
    return clean, fresh


def source_pins():
    return {name: composed.digest(HERE / name) for name in (
        Path(__file__).name, PROTOCOL.name, "grid_predictive_precision.py", "optimized_grid.py",
    )}


def sources():
    controls()
    return composed.sources() | {
        "precision_sources": source_pins(),
        "clean_comparator_sha256": CLEAN_SHA,
        "fresh_installed_comparator_sha256": FRESH_SHA,
    }


def probe():
    from integrated_original_entry import PNG_LIBRARY, PNG_SHA
    from reports.ALGO08.v3 import ds30_0163_combined as original
    from verified_rgba import RgbaEvidence

    result = original.probe(job_root=composed.READY, admission_pin=composed.READY_PIN, job_pin=composed.JOB_PIN)
    verified = RgbaEvidence(PNG_LIBRARY, PNG_SHA, None, {}).ready
    print(json.dumps(result | {"precision_ready": verified and bool(source_pins())}))


def worker(root):
    from aperture_trial import write
    from grid_predictive_precision import guarded_predictor
    import optimized_grid

    book = composed.read(root / "admission.json")
    if book["precision_sources"] != source_pins():
        raise ValueError("The optional grid source changed after admission")
    counts = Counter()
    evaluate = guarded_predictor(optimized_grid.reduced_predictive, counts)
    with patch.object(optimized_grid, "reduced_predictive", evaluate):
        composed.worker(root)
    write(root / "predictive-precision.json", dict(counts))


def score(root):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    from ds30_0359_composed_score import grid_evidence
    from ds30_0359_predictive_score import image_identity
    from history_risk_cairo_physical import clean
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import inspect

    old, fresh = controls()
    seal = root / "prediction-seal.json"
    clock, admission = (composed.read(root / name) for name in ("routed/clock.json", "admission.json"))
    if composed.read(seal) != output_seal(root) or admission["precision_sources"] != source_pins():
        raise ValueError("The predictive precision experiment differs from its seal")
    costs = {}
    for metric in ("cpu_s", "elapsed_s"):
        def setup(book):
            smoke = book["smoke"].get("clock", book["smoke"])
            return book["setup"][metric] + smoke[metric]

        values = {
            label: dict(worker=worker_clock[metric], admission=setup(book))
            for label, worker_clock, book in (("fresh_installed", fresh["clock"], fresh["admission"]),
                                               ("clean", old["clock"], old["admission"]),
                                               ("precision", clock, admission))
        }
        for value in values.values():
            value["charged"] = value["worker"] + value["admission"]
        installed, original, candidate = (values[name] for name in ("fresh_installed", "clean", "precision"))
        costs[metric] = values | dict(
            original_savings=original["worker"] - candidate["worker"],
            installed_through_exit_ratio=installed["worker"] / candidate["worker"],
            installed_charged_ratio=installed["charged"] / candidate["charged"],
            through_exit_gap_to_half=candidate["worker"] - installed["worker"] / 2,
        )
    result = dict(case="DS30-0359", qualified=False, qualified_numerics=False, measured_children=1,
                  prediction_sha256=composed.digest(seal), clocks=clock, cost=costs, admission=admission,
                  waveform_reads=0, backing_archive_reads=0)
    if clock["exit_code"]:
        write(root / "result.json", result | {"status": "precision_worker_failed"})
        return

    reference = old["candidate"]
    directory = root / "routed/candidate"
    bound, req = load_job(composed.READY / "job.json", composed.JOB_PIN)
    receipt = composed.read(directory / "worker.json")["receipt"]
    current = inspect(directory, "0359-precision", receipt, clock, req, native_sha=req["native_sha256"],
                      windows=bound["issued"], admitted=bound["admitted"], audit_name="worker.json")
    original_run = reference["science"]["receipt"]["run_id"]
    ordinary = FastStandardAnalysisStore(CLEAN / "routed/candidate").position_grid(original_run)
    grid = FastStandardAnalysisStore(directory).position_grid(receipt["run_id"])
    comparison = grid_evidence(ordinary, grid)
    images = image_identity(reference["figures"], current["figures"])
    ports = composed.read(directory / "ports.json")
    prior_ports = composed.read(CLEAN / "routed/candidate/ports.json")
    telemetry = composed.read(root / "composition.json")
    counts = composed.read(root / "predictive-precision.json")
    predictive = telemetry["predictive"]
    checks = dict(
        terminal=current["terminal"] == reference["terminal"],
        both_calibrations=current["science"]["arms"] == reference["science"]["arms"],
        owners=current["selected_rows"] == reference["selected_rows"]
        and all(len(rows) == 3640 for rows in current["selected_rows"].values()),
        graph=clean(ports["graph"]) == clean(prior_ports["graph"])
        and current["worker"]["graph_proof"] == reference["worker"]["graph_proof"],
        path=current["sidecars"]["path"] == reference["sidecars"]["path"],
        original_authenticated_reads=ports["verified_tle"] == prior_ports["verified_tle"],
        complete_grid=grid["complete"] and grid["evaluated_points"] == 179
        and all(item["qualified"] for item in comparison.values()),
        figures=len(images) == 8 and all(images.values()),
        genuine_grid_operand_coverage=predictive.get("grid_calls") == 1
        and predictive.get("reduced_calls") == counts.get("precision", 0) + counts.get("incumbent", 0) == 356
        and not predictive.get("unsupported_binding") and not predictive.get("original_fallback_calls"),
    )
    science = all(checks.values())
    qualified = science and bool(counts.get("precision"))
    publication = composed.read(directory / "joint-research-receipt.json")
    write(root / "result.json", result | dict(
        qualified=qualified, qualified_numerics=science, checks=checks, grid=comparison,
        figures=images, predictor=counts, telemetry=telemetry,
        publication={name: publication[name] for name in ("publication_cpu_s", "publication_elapsed_s", "solve")},
        prediction_timers=receipt["posterior_grid_handoff"],
        reference_grid_kernel=reference["worker"]["receipt"]["posterior_grid_handoff"],
        reference_comparators=dict(clean_sha256=CLEAN_SHA, installed_sha256=FRESH_SHA),
    ))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "probe", "score"))
    cli.add_argument("root", type=Path, nargs="?")
    args = cli.parse_args()
    if args.action == "probe":
        probe()
    elif args.action == "worker":
        worker(args.root)
    elif args.action == "score":
        score(args.root)
    else:
        composed.launch(args.root, entry=Path(__file__), extra_sources=sources,
                        protocol=PROTOCOL, probe_marker="precision_ready")
