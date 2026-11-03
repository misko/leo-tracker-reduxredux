"""Consolidate matched cone effects and independently labeled geometry flags."""
import csv
import hashlib
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
OPTIONS = ("control", "cone050", "cone100")
ARMS = ("fitted-c", "zero-c")


def main():
    summary = dict(cases={}, selected=[], total_fits=0, primary_fits=0, polish_fits=0, total_fit_elapsed_s=0.)
    flags = []
    for case in ("1939", "2139"):
        d = json.loads((HERE / case / "polished.json").read_text())
        m = json.loads((HERE / "geometry" / f"markers-{case}.json").read_text())
        assert d["status"] == "complete" and d["relative_sigma_s"] == 1.
        for key, filename in (("protocol_sha256", "experiment.py"), ("objective_sha256", "cone_objective.py")):
            assert d[key] == "sha256:" + hashlib.sha256((HERE / filename).read_bytes()).hexdigest()
        expected = {(basin, option, arm) for basin in d["basins"] for option in OPTIONS for arm in ARMS}
        assert len(d["runs"]) == len(expected)
        assert {(r["basin"], r["option"], r["arm"]) for r in d["runs"]} == expected
        assert len(d["selections"]) == 6
        for run in d["runs"]:
            assert run["seed_sha256"] == d["basins"][run["basin"]]["seeds"][run["arm"]]["vector_sha256"]
            if run["arm"] == "zero-c":
                assert run["result"]["vector"][6] == 0
        assert len(d["polish_runs"]) == 6
        assert {(r["option"], r["arm"]) for r in d["polish_runs"]} == {(o, a) for o in OPTIONS for a in ARMS}
        for run in d["polish_runs"]:
            seed = next(r for r in d["primary_selections"] if r["option"] == run["option"] and r["arm"] == run["arm"])
            digest = "sha256:" + hashlib.sha256(struct.pack("<" + "d" * len(seed["vector"]), *seed["vector"])).hexdigest()
            assert run["seed_sha256"] == digest
            if run["arm"] == "zero-c":
                assert run["result"]["vector"][6] == 0
        for r in d["selections"]:
            assert r["feasible"]
            if r["arm"] == "zero-c":
                assert r["vector"][6] == 0
            assert r["selection_score"] == min(v["selection_score"] for v in d["candidates"] if v["option"] == r["option"] and v["arm"] == r["arm"])
            control = next(v for v in d["selections"] if v["option"] == "control" and v["arm"] == r["arm"])
            row = {key: value for key, value in r.items() if key != "vector"}
            row.update(case=case, control_error_m=control["horizontal_error_m"], error_change_m=r["horizontal_error_m"]-control["horizontal_error_m"])
            for scenario, label in (("reference-diagnostic:receive-time", "reference_raw"), ("selected:fitted-orbit-time", "selected_shifted")):
                values = m["scenarios"][r["option"] + ":" + r["arm"] + ":" + scenario]
                for key, value in values.items():
                    row[label + "_" + key] = value
                assert abs(values["signal_mass"] - r["signal_mass"]) < 1e-6
            if r["option"] == "control":
                assert abs(r["cone_score_adjustment"]) < 1e-8
                assert abs(r["data_nll"] - r["uniform_frequency_data_nll"]) < 1e-8
            summary["selected"].append(row)
        summary["cases"][case] = dict(nested_search_gaps=d["nested_search_gaps"], sigma_s=1.,
                                      nominal_fit_seconds=d["seconds_per_fit"], regions=d["basins"])
        summary["primary_fits"] += len(d["runs"])
        summary["polish_fits"] += len(d["polish_runs"])
        summary["total_fits"] += len(d["runs"]) + len(d["polish_runs"])
        summary["total_fit_elapsed_s"] += sum(r["result"]["elapsed_s"] for r in d["runs"] + d["polish_runs"])
        with (HERE / "geometry" / f"markers-{case}.csv").open() as file:
            flags.extend(csv.DictReader(file))
    assert summary["primary_fits"] == 60 and summary["polish_fits"] == 12 and summary["total_fits"] == 72
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for filename, rows in (("selected.csv", summary["selected"]), ("satellite_flags.csv", flags)):
        fields = list(dict.fromkeys(key for row in rows for key in row))
        with (HERE / filename).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    for r in summary["selected"]:
        print(r["case"], r["option"], r["arm"], "km", round(r["horizontal_error_m"] / 1000, 3),
              "converged", r["converged"], "boundary", r["boundary"],
              "opposite%", round(100*r["reference_raw_opposite_east_west_fraction"], 2),
              "outside%", round(100*r["reference_raw_outside_empirical_ellipse_fraction"], 2),
              "behind%", round(100*r["reference_raw_behind_nominal_boresight_fraction"], 3))
    print("fits", summary["total_fits"], "seconds", summary["total_fit_elapsed_s"], "flag rows", len(flags))


if __name__ == "__main__":
    main()
