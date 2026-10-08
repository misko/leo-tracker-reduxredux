"""Oracle-only profiles of the frozen candidate's now-consumed newer failures."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter20"))
# isort: off
from newer import load_member  # noqa: E402
from dynamic_rf import DynamicRFObjective, fit  # noqa: E402
from inputs import json_value, write_json  # noqa: E402
from probe import error_km  # noqa: E402
# isort: on

from leo.analysis.hard60_score import Hard60Objective  # noqa: E402
from leo.application.hard60_runner import HARD60_SCORE  # noqa: E402
from leo.contracts.digests import canonical_digest  # noqa: E402

sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter09"))
spec = importlib.util.spec_from_file_location(
    "oracle_helpers", REPORTS / "2026_10_08_position_error_iter09/profile.py"
)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def run(label):
    protocol = json.loads((HERE / "protocol.json").read_text())
    for path, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / path).read_bytes()).hexdigest() == digest, path
    binding = protocol["cases"][label]
    previous = json.loads((REPORTS / binding["result"]).read_text())["result"]
    document = json.loads((REPORTS / binding["baseline"]).read_text())
    frozen = json.loads(
        (REPORTS / "2026_10_08_position_error_iter20/validation-protocol.json").read_text()
    )
    member = next(row for row in frozen["members"] if row["label"] == label)
    case = load_member(member)
    assert canonical_digest(case.document) == canonical_digest(document)
    assert previous["regional_sources"]["fitted-c"] == "baseline"
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    calibration = document["diagnostics"]["calibrations"][selected["source_basin"]]
    lookup = {int(number): i for i, number in enumerate(case.bank.numbers)}
    bank = case.bank.select([lookup[number] for number in previous["satellites"]])
    base = Hard60Objective(
        case.prepared.observations, bank, case.prior, HARD60_SCORE,
        receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]),
    )
    correction = calibration["correction"]
    model = DynamicRFObjective(base, correction["nodes_s"], correction["knots_hz"], 50)
    chosen = previous["stages"]["drift-50"]["fitted-c"]
    seed, clock = np.asarray(chosen["vector"]), np.asarray(chosen["clock_coefficients"])
    value, _, _, terms = model.evaluate_joint(seed, clock)
    np.testing.assert_allclose(value, chosen["objective"], atol=1e-6, rtol=0)
    assigned = bank.numbers[terms.responsibilities.argmax(axis=1)].copy()
    assigned[terms.responsibilities.max(axis=1) < 0.5] = 0
    groups = 2 * assigned + model.observations.receiver
    truth = helpers.reference_point(
        case.prior, document["reference_latitude_deg"],
        document["reference_longitude_deg"], seed[:2]
    )
    steps = int(np.ceil(np.linalg.norm(truth - seed[:2]) / 0.25))
    assert 1 <= steps <= 20
    rows = []
    for arm in ("fitted-c", "zero-c"):
        current = None
        for step in range(steps + 1):
            point = seed[:2] + (truth - seed[:2]) * step / steps
            start = seed.copy() if current is None else np.asarray(current["vector"]).copy()
            start[:2] = point
            clock_start = clock if current is None else current["clock_coefficients"]
            attempts = []
            for retry in range(3):
                row = json_value(fit(
                    model, start, arm=arm, fixed_position=True, clock_seed=clock_start
                ))
                row.update(arm=arm, step=step, retry=retry,
                           error_km=error_km(case.prior, row["vector"], document))
                row["decomposition"] = helpers.decompose(model, row, groups)
                if arm == "zero-c":
                    assert row["vector"][6] == 0 and row["rf_drift_coefficients"] == [0, 0]
                attempts.append(row)
                if row["converged"]:
                    break
                start, clock_start = row["vector"], row["clock_coefficients"]
            rows.append(dict(arm=arm, step=step, attempts=attempts))
            print(label, arm, step, steps, row["converged"], flush=True)
            if not row["converged"]:
                break
            current = row
        else:
            released = json_value(fit(
                model, current["vector"], arm=arm, clock_seed=current["clock_coefficients"]
            ))
            released.update(arm=arm, phase="reference-released",
                            error_km=error_km(case.prior, released["vector"], document))
            released["decomposition"] = helpers.decompose(model, released, groups)
            rows.append(released)
    write_json(HERE / "results" / f"{label}.json", dict(
        label=label, reference_use="Oracle-only diagnostic, never an operational initializer",
        fitted_selected=chosen, reference_point_km=truth, step_count=steps,
        groups={str(int(g)): dict(satellite=int(g // 2), receiver=int(g % 2),
                                 windows=int((groups == g).sum())) for g in np.unique(groups)},
        rows=rows,
    ))


if __name__ == "__main__":
    run(sys.argv[1])
