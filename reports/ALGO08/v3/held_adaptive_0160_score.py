"""Verify and score the two sealed DS30-0160 saved publications offline."""

from contextlib import nullcontext
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT/"src"), str(ROOT)]

from held_adaptive_0160 import ARMS, RESULT_NAME, STAGED, binding, digest


LAYOUT_CONTROL = Path("/dev/shm/leo-v3-saved-0160-confirm-01")
LAYOUT_PIN = "050b3983b0ac83d25ec5eb964d4df97d083c5bdec7810eb27fe7008737126bc5"
ORIGINAL_AUDIT = Path("/dev/shm/leo-v3-saved-0160-audit.json")
ORIGINAL_PIN = "80c0658736c7e94ecdbbc56839171ccb10a0fa74880266f29c6dca8a61229038"


def read(path):
    return json.loads(path.read_bytes())


def verified(root, clock, worker_file, request, *, adaptive=False):
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from reports.ALGO08.v3.live_adaptive_grid_entry import check_sample, read_manifest, read_sidecar, research_layout
    from tools.pipeline_eval.qualification.paired_publication import evidence

    worker = read(root/worker_file)
    research = read(root/"joint-research-receipt.json")
    receipt = worker["receipt"]
    if (clock["exit_code"] or not worker["no_waveform"] or worker["handoffs"] != 1
            or worker["native_sha256"] != request["native_sha256"] or research["receipt"] != receipt):
        raise ValueError("Expected one successful publication of the original signed detection packet")
    run = receipt["run_id"]
    terminal_path = root/"fast-scan-automatic-work"/run/"terminal.json"
    terminal = read(terminal_path)
    packet, = terminal_path.parent.parent.glob("*/detections.json")
    research_complete = adaptive and receipt["decision"] == "complete"
    with research_layout(root) if research_complete else nullcontext():
        science = evidence(root, receipt, clock["started_unix_ns"], read_only=True)
        products = artifacts(root, receipt)
        store = FastStandardAnalysisStore(root)
        path = store.position_path(run) if receipt["decision"] == "complete" else None
        sample = store.position_grid(run) if receipt["decision"] == "complete" else None
    if (science["raw_authority"] != request["raw_authority"] or digest(packet) != request["native_sha256"]
            or terminal["native_sha256"] != "sha256:"+request["native_sha256"] or receipt["session_id"] != request["session"]):
        raise ValueError("Publication changed the signed recording, session or native detections")
    if research_complete:
        manifest = read_manifest(root, run)
        check_sample(read_sidecar(root, run, "sample"), manifest["publication"])
        if (root/"fast-scan-standard-v2").exists():
            raise ValueError("Adaptive presentation entered the installed standard publication namespace")
    if path is not None:
        for item in (path, sample):
            if item["binding"]["position_png_sha256"] != products["images"]["position"]["sha256"]:
                raise ValueError("Position sidecar points at a different navigable figure")
    return dict(clock=clock, worker=worker, science=science, terminal=terminal, products=products,
                path=path, sample=sample, rows=research["selected_rows"], trace=research)


def adaptive_quality(active):
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from reports.ALGO08.v3.live_adaptive_grid import quality

    if active["sample"] is None:
        return dict(scope="withheld")
    grid = active["sample"]
    details = dict(scope="exact evaluated locations, endpoints, bindings and decoded products",
                   locations=grid["evaluated_points"], full_layout=grid["reference_layout"]["candidates"],
                   exact_calls_by_arm=grid["objective_calls"], sample_cpu_s=grid["sample_cpu_s"],
                   sample_elapsed_s=grid["elapsed_seconds"])
    if not (LAYOUT_CONTROL/"result.json").is_file() or digest(LAYOUT_CONTROL/"result.json") != LAYOUT_PIN:
        return details | {"skipped_full_layout_reason": "prior standard-layout control unavailable"}
    prior = read(LAYOUT_CONTROL/"result.json")["candidate"]
    if (prior["terminal"] != active["terminal"] or prior["selected_rows"] != active["rows"]
            or prior["worker"]["solve"]["objective_replay"] != active["worker"]["solve"]["objective_replay"]):
        return details | {"skipped_full_layout_reason": "prior standard layout used different numerical fitted states"}
    run = prior["worker"]["receipt"]["run_id"]
    full = FastStandardAnalysisStore(LAYOUT_CONTROL/"cumulative").position_grid(run)
    try:
        accuracy = quality(grid, full)
    except ValueError as mismatch:
        return details | {"skipped_full_layout_reason": str(mismatch)}
    return details | dict(scope="exact matched standard-layout comparison", validation=accuracy, reference_seal=LAYOUT_PIN)


def score(root):
    from aperture_trial import write
    from prospective_0316_solver import owner_delta
    from triage_bounds import calibration_comparison

    enrollment = read(root/"binding.json")
    if enrollment["input"] != binding() or digest(ORIGINAL_AUDIT) != ORIGINAL_PIN:
        raise ValueError("Saved candidate enrollment or the original named publication audit changed")
    request = read(Path(enrollment["input"]["request"]))
    candidate_clock = read(root/"candidate-clock.json")
    control_clock = read(STAGED/"stock-clock.json")["timing"]
    if candidate_clock["exit_code"]:
        raise ValueError("The candidate failed through process exit. Preserve the clock and output separately.")
    runs = {"named": verified(STAGED/"stock", control_clock, "saved-0160-worker.json", request),
            "candidate": verified(root/"candidate", candidate_clock, RESULT_NAME, request, adaptive=True)}
    named, candidate = runs.values()
    prior = read(ORIGINAL_AUDIT)["runs"]["stock"]
    receipt_fields = ("run_id", "session_id", "window_count", "counts", "region", "decision", "terminal_sha256")
    if (not named["trace"]["stock_control"] or named["terminal"] != prior["terminal"]
            or any(k != "receipt" and v != prior["science"][k] for k, v in named["science"].items())
            or any(named["science"]["receipt"][k] != prior["science"]["receipt"][k] for k in receipt_fields)
            or len(named["products"]["images"]) != 8
            or named["sample"]["evaluated_points"] != 179 or named["trace"]["machine"] != candidate["trace"]["machine"]):
        raise ValueError("Named denominator must be its exact installed-v3 numerical and eight-image replay")
    if any(runs["named"]["worker"]["receipt"][key] != runs["candidate"]["worker"]["receipt"][key]
           for key in ("session_id", "window_count", "counts", "region")):
        raise ValueError("Submitted native rows, original offer or all-visit counts changed")
    activation = read(root/"candidate/activation.json")
    if not activation["causal_bytes_by_snapshot"]:
        raise ValueError("The active solver never consumed the authenticated causal catalogue")
    regional = candidate["trace"].get("early_regional", [])
    maps = adaptive_quality(candidate)
    owners = {arm: owner_delta(*(value["rows"].get(arm, []) for value in runs.values())) for arm in ARMS}
    geography = calibration_comparison({name: dict(arms=value["science"]["arms"]) for name, value in runs.items()}, "DS30-0160")
    speeds = {measure: control_clock[measure]/candidate_clock[measure] for measure in ("cpu_s", "elapsed_s")}
    result = dict(case=request["case"], trials=1, attached_recordings=0, stage_bytes=0, original_backing_bytes=0,
                  scope="signed named original 20 ms detector packet to verified publication and exit",
                  enrollment=enrollment, clock_sha256=digest(root/"candidate-clock.json"),
                  raw_authority=request["raw_authority"], prior_named_audit=ORIGINAL_PIN, activation=activation,
                  map=maps, owners=owners, geography=geography, regional=regional, speedup=speeds,
                  publications={name: {k: value[k] for k in ("clock", "worker", "science", "terminal", "products")}
                                for name, value in runs.items()})
    write(root/"result.json", result)


if __name__ == "__main__":
    score(Path(sys.argv[1]))
