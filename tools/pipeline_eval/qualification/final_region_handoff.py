"""Exercise the saved-I/Q position worker on authenticated original GLRT."""

import argparse
from pathlib import Path
from unittest.mock import patch

from .. import iq_service, original_receiver, whole_iq
from ..__main__ import local_output, save_json
from ..variants import final_region
from .final_region_trial import CPUS, REPORT, ROOT
from .full_v5_check import _sha
from .sequential_fix_results import REPORT as SEQUENTIAL
from .sequential_fix_results import sealed


def handoff(work, cpu, ident, condition):
    omitted = condition == "omitted"
    source = SEQUENTIAL / "omitted" if omitted else SEQUENTIAL
    offer = "east-30-km" if omitted else "east-15-km"
    plan, groups, _ = sealed(source)
    (rows,) = [rows for (key, label, _), rows in groups.items() if (key, label) == (ident, offer)]
    full = rows[-1]
    spec = plan["cases"][ident]
    case, original = whole_iq.binding(ident)
    if case["request"]["sha256"] != spec["original_request_sha256"]:
        raise ValueError("handoff original receiver job differs from the sealed recording")
    native = whole_iq.checked(Path(spec["native"]), full["recorded_native_sha256"])
    job = dict(original["job"], search_center=full["tile"]["center"])
    job["native_input"] = dict(path=str(native), sha256="sha256:" + _sha(native))
    work.mkdir(parents=True, exist_ok=False)
    receiver = original_receiver.CALIBRATION
    lock = dict(
        id=ident,
        original_request_sha256=case["request"]["sha256"],
        prior_fit_lock_sha256=_sha(source / "prediction-lock.json"),
        receiver=str(receiver),
        receiver_files=original_receiver.receiver_assets(receiver),
        interior_guard=original_receiver.interior_guard_sources(),
        sources={
            str(Path(module.__file__).relative_to(ROOT)): _sha(Path(module.__file__))
            for module in (original_receiver, whole_iq)
        },
    )
    save_json(work / "source-lock.json", lock)
    attempt = work / "position"
    path = attempt / "recording/request.json"
    save_json(path, dict(original, job=job))
    save_json(
        attempt / "raw.json",
        dict(native_sha256=job["native_input"]["sha256"], request_sha256=_sha(path)),
    )
    with patch.object(iq_service, "MODULE", original_receiver.MODULE):
        receipt = original_receiver.service(
            attempt, cpu, 180, "position", dict(receiver=str(receiver))
        )
    row = dict(lock=lock, service=receipt, tile=full["tile"], result=None)
    if iq_service.succeeded(receipt):
        expected = final_region.publish(full["result"], full["tile"], enabled=True)
        row["result"] = actual = whole_iq.read(attempt / "position.json")
        row["prior_numeric_parity"] = all(
            actual.get(key) == expected.get(key) for key in ("status", "reason", "arms")
        ) and all(
            actual["metrics"].get(key) == expected["metrics"].get(key)
            for key in ("exact_tile_margin_km", "c0_frequency_score", "fitted_c_frequency_score")
        )
    save_json(work / "receipt.json", row)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--report", type=local_output, default=REPORT)
    parser.add_argument("--cpu", type=int, choices=CPUS, required=True)
    parser.add_argument("--condition", choices=("omitted", "containing"), required=True)
    args = parser.parse_args()
    ident = "DS26-0237" if args.condition == "omitted" else "DS29-0082"
    result = handoff(args.work, args.cpu, ident, args.condition)
    save_json(args.report / f"handoff-{args.condition}.json", result)
    return int(not result.get("prior_numeric_parity"))


if __name__ == "__main__":
    raise SystemExit(main())
