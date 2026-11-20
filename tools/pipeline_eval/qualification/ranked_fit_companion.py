"""One short DS29 pair after the primary reserve exhausted its wall deadline."""

import argparse
from pathlib import Path

from ..__main__ import local_output, save_json
from . import fit_work_trial as earlier
from . import ranked_fit_trial as trial

CASE, CPU = "DS29-0174", 12
COMMON = trial.COMMON


def run(base, reserve, out):
    ident = "DS29-0247"
    for folder in (base, reserve):
        record = folder / "runs" / ident / trial.CANDIDATE / "attempt.json"
        if COMMON.read(record)["result"]["status"] != "timed_out":
            raise ValueError("companion requires the original reserve and confirmation deadlines")
    receipt = COMMON.seal(earlier.REPORT, "receipt.json", ("resources.csv",))
    if CASE not in receipt["cases"]:
        raise ValueError("short companion is outside the prior authenticated timing study")
    retained = Path("/srv/bulk/leo-dev/fitwrk-run") / "runs" / CASE / earlier.STOCK / "attempt.json"
    previous = COMMON.read(retained)
    if previous["result"]["status"] != "ok" or not 0 < previous["wall_s"] <= 55:
        raise ValueError("archived stock does not support the predeclared short-runtime stratum")
    out.mkdir(exist_ok=False)
    for method in ("stock", "candidate"):
        (out / method).symlink_to(base / method, target_is_directory=True)
    plan = COMMON.read(base / "plan.json")
    cases = {CASE: CPU}
    order = [trial.CANDIDATE, trial.STOCK]
    save_json(
        out / "plan.json",
        plan
        | {
            "cases": {CASE: earlier.binding(CASE)},
            "cpus": cases,
            "order": {CASE: order},
            "companion": {
                "reason": "prior exact stock completed in the archived 0–55 second wall stratum",
                "prior_archive_sha256": COMMON.sha(earlier.REPORT / "resources.csv"),
                "prior_attempt_sha256": COMMON.sha(retained),
                "original_ranked_plan_sha256": COMMON.sha(base / "plan.json"),
                "runtime_source_seal_sha256": COMMON.sha(base / "candidate-lock.json"),
                "source_sha256": COMMON.sha(Path(__file__)),
            },
        },
    )
    candidate = COMMON.read(base / "candidate-lock.json")
    save_json(
        out / "candidate-lock.json",
        candidate | {"plan_sha256": COMMON.sha(out / "plan.json")},
    )
    trial.CASES[CASE] = CPU
    for method in order:
        trial.run(out, CASE, method)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("reserve", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    run(args.base.resolve(), args.reserve.resolve(), local_output(args.out))
