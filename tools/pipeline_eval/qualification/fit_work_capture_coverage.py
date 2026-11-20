"""Confirm actual constrained calls on authenticated capture-era factors."""

import argparse
import os
from pathlib import Path

from ..__main__ import local_output, read_predictions, save_json
from . import fit_work_coverage as coverage
from . import fit_work_trial as trial
from .cavity_pressure_results import scientific_payload

CASE = "DS26-0052"
COMMON = trial.COMMON
ARCHIVE = trial.REPORT.parent.parent / "inference/aligned-confirmation"
FILE = "stock-cavity-positions.jsonl.gz"


def run(work, out):
    if os.sched_getaffinity(0) != {coverage.CPU} or os.nice(0) < 10:
        raise ValueError("branch confirmation must use CPU 13 at nice 10")
    COMMON.seal(ARCHIVE, "prediction-lock.json", (FILE,))
    row = read_predictions(ARCHIVE / FILE)[CASE]
    if row["result"]["status"] != "ok" or not row["result"]["metrics"]["cavity_offered"]:
        raise ValueError("prior compact source does not establish an offered cavity")
    case, request, bound = trial.pressure.direct.input_case("capture-era-" + CASE)
    if (
        request["job"]["evaluation_reference"] is not None
        or row["native_sha256"].removeprefix("sha256:") != bound["native_sha256"]
        or row["catalog_sha256"] != bound["catalog_sha256"]
        or row["tile"] != bound["tile"]
    ):
        raise ValueError("capture-era offered branch has a different native, catalogue or offer")
    binding = dict(
        bound,
        native=case["native_path"],
        request=case["request_path"],
        request_sha256=COMMON.sha(Path(case["request_path"])),
    )
    plan_file = work / "plan.json"
    source = COMMON.read(plan_file)
    out.mkdir(exist_ok=False, parents=True)
    save_json(
        out / "plan.json",
        dict(
            case=binding,
            selection="Authenticated prior compact cavity offer and recorded cavity timing",
            archived_cavity_wall_s=row["result"]["metrics"]["stage_s"]["cavity"],
            prior_prediction_sha256=COMMON.sha(ARCHIVE / FILE),
            parent_plan_sha256=COMMON.sha(plan_file),
            package_sha256=COMMON.sha(work / "candidate-lock.json"),
            launcher_sha256=COMMON.sha(Path(coverage.__file__)),
            monitor_sha256=COMMON.sha(Path(coverage.fit_work_count.__file__)),
            cpu=coverage.CPU,
            cap_bytes=536870912,
            limit_s=trial.LIMIT,
            swap_bytes=0,
        ),
    )
    stock = coverage.capture(work, trial.STOCK, out / "stock", binding, source)
    save_json(out / "stock.json", stock)
    print(CASE, "stock constrained calls:", len(stock["selected_refits"] or []), flush=True)
    candidate = (
        coverage.capture(work, trial.CANDIDATE, out / "candidate", binding, source)
        if stock["selected_refits"]
        else None
    )
    exact = None
    if candidate:
        save_json(out / "candidate.json", candidate)
        if all(x.get("result") and x["result"]["status"] == "ok" for x in (stock, candidate)):
            exact = scientific_payload(stock["result"]) == scientific_payload(candidate["result"])
    save_json(
        out / "comparison.json",
        dict(case=CASE, stock=stock, candidate=candidate, exact_scientific_payload=exact),
    )
    print(CASE, "exact endpoint parity:", exact, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--case", default=CASE, choices=(CASE, "DS29-0357", "DS26-0072"))
    a = p.parse_args()
    CASE = a.case
    run(a.work.resolve(), local_output(a.out))
