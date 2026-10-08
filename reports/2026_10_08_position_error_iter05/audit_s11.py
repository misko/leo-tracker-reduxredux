"""Development-only multi-start audit; never changes the frozen validation candidate."""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026_10_08_position_error_iter04"))
sys.path.insert(0, str(HERE.parent / "2026_10_08_position_error_iter01"))
sys.path.insert(0, str(HERE.parent / "2026_10_08_hard60_bounded_recovery"))
from inputs import json_value, write_json  # noqa: E402
from joint_clock import JointClockObjective, fit  # noqa: E402
from probe import error_km, load  # noqa: E402


def main():
    path = HERE / "S11-multistart.json"
    if path.exists():
        raise FileExistsError(path)
    case, doc, base, seed = load("S11")
    selected = next(a["selected"] for a in doc["methods"][0]["arms"] if a["name"] == "fitted-c")
    correction = doc["diagnostics"]["calibrations"][selected["source_basin"]]["correction"]
    rows = []
    for east, north in [(0, 0), (5, 0), (-5, 0), (0, 5), (0, -5)]:
        start = seed.copy()
        start[:2] += [east, north]
        for arm in ("fitted-c", "zero-c"):
            model = JointClockObjective(base, correction["nodes_s"], correction["knots_hz"], 2)
            result = json_value(fit(model, start, arm=arm))
            result.update(
                arm=arm,
                start_offset_km=[east, north],
                error_km=error_km(case.prior, result["vector"], doc),
            )
            rows.append(result)
            print(
                arm,
                east,
                north,
                result["converged"],
                round(result["error_km"], 3),
                round(result["objective"], 4),
                flush=True,
            )
    write_json(
        path,
        dict(
            label="S11",
            session_id=doc["session_id"],
            candidates=rows,
            scope="development diagnostic, not a changed validation candidate",
        ),
    )


if __name__ == "__main__":
    main()
