"""Recompute ac11's frozen retained region with the staged production modules.

The reference coordinate is never loaded. This checks numerical port parity,
not independent validation or a new cohort statistic.
"""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from leo.application.hard60_retained_calibration import recovered_region
from leo.application.regional_position_runner import json_value

HERE = Path(__file__).resolve().parent
RESEARCH = Path("/home/mouse9911/gits/leo-hard60-default")
ITER107 = RESEARCH / "reports/2026_10_09_position_error_iter107"
LABEL = "POST18-NEWER-20261009-051"
SESSION = "scan-fw-ac11ac00c0676d1b"


def extract(path, query):
    return json.loads(subprocess.check_output(["jq", "-c", query, str(path)]))


def main():
    source = Path(sys.argv[1]).resolve(strict=True)
    staged = source.parents[1]
    assert staged.parent == Path("/opt/leo-b7") and source == staged / "worker/src"
    assert Path(
        __import__("leo.application.hard60_retained_calibration", fromlist=["x"]).__file__
    ).is_relative_to(source)
    sys.path.insert(0, str(ITER107))
    import cohort  # noqa: PLC0415

    plan = json.loads((ITER107 / "source-plan.json").read_text())
    member = next(row for row in plan["members"] if row["member"]["session_id"] == SESSION)
    case = cohort.load_member(member)
    candidate = ITER107 / "results" / LABEL / "candidate.json"
    trigger = extract(candidate, ".inventory.candidates[0]")
    assert trigger["key"] == "point:-47.5:-62.5"
    assert trigger["source_passes"] == ["baseline", "sep25", "sep50"]
    input_trigger = dict(
        basin=trigger["key"],
        original=trigger["original"],
        identity=trigger["identity"],
    )
    calls = []

    def stage(key, budget, operation):
        begun = time.monotonic()
        try:
            value = dict(result=json_value(operation()), reason=None)
        except (ValueError, TimeoutError) as error:
            value = dict(result=None, reason=f"{type(error).__name__}: {error}")
        calls.append(dict(key=key, budget_s=budget, elapsed_s=time.monotonic() - begun))
        return value

    recovered = recovered_region(
        case["observations"], case["bank"], case["prior"], input_trigger, stage
    )
    expected = extract(candidate, '.regions[.operational["fitted-c"].region_source]')
    assert recovered["recovery"]["result"]["status"] == "qualified"
    assert len(recovered["finals"]) == len(expected["finals"]) == 6
    comparisons = []
    for arm in ("zero-c", "fitted-c"):
        for start in ("association", "zero-timing", "own-continuation"):
            actual = next(r for r in recovered["finals"] if r["arm"] == arm and r["start"] == start)
            prior = next(r for r in expected["finals"] if r["arm"] == arm and r["start"] == start)
            a, b = actual["fit"], prior["fit"]
            assert a["converged"] == b["converged"]
            score_delta = float(a["objective"] - b["objective"])
            vector_delta = float(np.max(np.abs(np.asarray(a["vector"]) - b["vector"])))
            assert abs(score_delta) <= 1e-5 and vector_delta <= 1e-6
            comparisons.append(
                dict(
                    arm=arm,
                    start=start,
                    converged=a["converged"],
                    objective_delta=score_delta,
                    maximum_vector_delta=vector_delta,
                )
            )
    with candidate.open("rb") as handle:
        candidate_digest = "sha256:" + hashlib.file_digest(handle, "sha256").hexdigest()
    result = dict(
        status="passed",
        session_id=SESSION,
        stage=str(staged),
        stage_revision=json.loads((staged / "stage.json").read_text())["revision"],
        frozen_candidate_sha256=candidate_digest,
        trigger_basin=trigger["key"],
        calibration_status=recovered["recovery"]["result"]["status"],
        calls=calls,
        comparisons=comparisons,
        maximum_score_delta=max(abs(x["objective_delta"]) for x in comparisons),
        maximum_vector_delta=max(x["maximum_vector_delta"] for x in comparisons),
        note="Position reference and error absent from the numerical parity driver",
    )
    output = HERE / "parity.json"
    if output.exists():
        raise FileExistsError(output)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {k: result[k] for k in ("status", "maximum_score_delta", "maximum_vector_delta")}
        )
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: parity.py STAGED_WORKER_SRC")
    main()
