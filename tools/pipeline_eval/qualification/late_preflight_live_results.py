"""Authenticate fresh worker files and compare against the sealed aligned receiver."""

import argparse
from pathlib import Path

from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import late_preflight_live as fresh
from . import late_preflight_trial as trial
from . import pruned_finish_eval as matched
from .broad_search_budget import _case, frozen_inputs
from .full_receiver_comparison import read, sha

DECISIONS = (
    "addition_status",
    "reassociation_targets",
    "reassociation_admitted",
    "reassociation_selected",
)
TIMES = (*trial.STAGES, "late_rf_preflight")


def compare(result, control):
    validate_result(result)
    validate_result(control)
    outcomes = {}
    for arm in ARMS:
        if result["status"] != "ok" or control["status"] != "ok":
            continue
        field = f"{arm}_conditional_rms_hz"
        one, two = (r["metrics"].get(field) for r in (result, control))
        outcomes[arm] = dict(
            endpoint_delta_km=distance_km(
                result["arms"][arm]["latlon"], control["arms"][arm]["latlon"]
            ),
            rf_delta_hz=None if one is None or two is None else one - two,
            candidate_conditional_rms_hz=one,
            original_conditional_rms_hz=two,
        )
    return outcomes


def source_matches(path, wanted):
    if sha(path) == wanted:
        return True
    if path == Path(fresh.__file__):
        historical = trial.REPORT / "live" / "initial-launcher.txt"
        return historical.is_file() and sha(historical) == wanted
    return False


def publish(work, output):
    inputs = frozen_inputs()
    bindings = {
        key: matched.execution_binding(inputs[key], _case(inputs[key])) for key in matched.KNOWN
    }
    controls = matched.historical_controls(bindings)
    rows = []
    for ident, cpu in fresh.ROSTER.items():
        folder = work / ident
        lock = read(folder / "run-lock.json")
        if (
            lock["inputs"] != bindings[ident]
            or lock["cpu"] != cpu
            or lock["aligned_lock_sha256"] != sha(matched.armijo_aligned_trial.SEAL)
            or lock["aligned_predictions_sha256"] != sha(matched.HISTORICAL / "positions.jsonl.gz")
            or any(
                not source_matches(Path(path), wanted) for path, wanted in lock["sources"].items()
            )
        ):
            raise ValueError(f"{ident} fresh run changed source, inputs or historical control")
        worker = folder / "worker"
        request = matched.aligned_confirmation._request_proof(
            _case(inputs[ident]), worker / "request.json"
        )
        if request["scientific_request_sha256"] != bindings[ident]["scientific_request_sha256"]:
            raise ValueError(f"{ident} fresh scientific request differs from its plan")
        target = worker / "result.json"
        result, control = read(target), controls[ident]["result"]
        metrics = result["metrics"]
        if result["status"] != "ok" or "late_rf_preflight" not in metrics:
            raise ValueError(f"{ident} fresh worker did not complete both-arm preflight inference")
        rows.append(
            dict(
                id=ident,
                cpu=cpu,
                native_binding=bindings[ident],
                request=request,
                lock=lock,
                raw_result_sha256=sha(target),
                result=result,
                control=control,
                matched_arm_differences=compare(result, control),
                candidate_decision={k: metrics.get(k) for k in DECISIONS},
                control_decision={k: control["metrics"].get(k) for k in DECISIONS},
                candidate_wall_s={k: metrics["stage_s"].get(k) for k in TIMES},
                control_wall_s={k: control["metrics"]["stage_s"].get(k) for k in TIMES},
            )
        )
        write(output / f"{ident}-run-lock.json", (folder / "run-lock.json").read_bytes())
        write(output / f"{ident}-worker-result.json", target.read_bytes())
    save_json(output / "comparison.json", rows)
    names = [
        "comparison.json",
        *(f"{ident}-{end}.json" for ident in fresh.ROSTER for end in ("run-lock", "worker-result")),
    ]
    if (output / "initial-launcher.txt").exists():
        names.append("initial-launcher.txt")
    save_json(
        output / "evidence-lock.json",
        dict(
            files={name: sha(output / name) for name in names},
            scoring_source_sha256=sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=trial.REPORT / "live")
    args = parser.parse_args()
    publish(args.input, local_output(args.output))
