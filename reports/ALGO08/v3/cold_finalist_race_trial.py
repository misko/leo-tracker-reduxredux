"""Run and compare the frozen complete, short physical, and southern saved solves."""

import argparse
from functools import partial
import gzip
from hashlib import sha256
import json
from pathlib import Path

from cold_finalist_race import ENDPOINT_SHA, OPTIMIZER_SHA, refine
from full_family_amortized_trial import equality, read, run, write


HERE = Path(__file__).resolve().parent
CASES = ("DS30-0008", "DS30-0016", "south-containing")
MODES = ("control", "race")
BASES = {
    "full-family-amortized.json.gz": "f2cf9e3546bd91273d03ba87b8c5fee54e4b80f25f3bb69f5ea2a700b8612ca3",
    "full-family-south.json.gz": "71533f2c235f05b18d91876b0f8ba822af08612d244c6df9545064fc2f67db98",
}


def saved_control(case, mode, output):
    run(case, "control", output, paid_south=case == "south-containing", single_attempt=True,
        refine_cold=partial(refine, mode))


def terminal_choice(row):
    if not row["chosen"]:
        return None
    winner, = row["chosen"]
    details = winner["details"]
    keys = ("branch", "east_north_km", "latlon", "catalogue")
    return dict(node=winner["node_sha256"], point=winner["point"], phases=winner["phases"],
                score=details["scores"][details["branch"]-1], **{key: details[key] for key in keys})


def scientific_identity(row):
    identity = dict(row["identity"])
    if "selection" in identity:
        identity["selection"] = {k: v for k, v in identity["selection"].items() if k != "selection_cpu_s"}
    return identity


def compare_pair(control, race):
    checks = equality(control, race)
    del checks["chosen"]
    checks["same_input"] = scientific_identity(control) == scientific_identity(race)
    checks["winner"] = terminal_choice(control) == terminal_choice(race)
    base = control["chosen"][0]["details"]
    tested = (race["chosen"][0]["details"] if race["chosen"] else
              dict(routing="outer_fallback", overlap=[], prefix=[], completed=[]))

    def completed(details):
        return {x["branch"]: {k: v for k, v in x.items() if k != "cpu_ns"} for x in details["completed"]}

    checks["overlap"] = tested["overlap"] == base["overlap"]
    control_fits = completed(base)
    checks["all_completed_fits"] = bool(tested["completed"]) and all(
        control_fits.get(branch) == item for branch, item in completed(tested).items())
    cpu = {item["branch"]: item["cpu_ns"]/1e9 for item in base["completed"]}
    prefix = {item["branch"]: item["cpu_ns"]/1e9 for item in tested["prefix"]}
    completed_race = {item["branch"]: item["cpu_ns"]/1e9 for item in tested["completed"]}
    winner = base["branch"]
    oracle_s = sum(seconds for branch, seconds in cpu.items() if branch != winner)
    clocks = {mode: {"cpu_s": row["cpu_s"], "elapsed_s": row["elapsed_s"],
                     "cold": row["attempts"][0].get("cold_clocks"), "rank": row["ranks"][0]["clocks"],
                     "grid": row["attempts"][0].get("standard_evidence_clocks")}
              for mode, row in zip(MODES, (control, race), strict=True)}
    return dict(exact=checks, outcomes=clocks, control_finalist_cpu_s=cpu, race_prefix_cpu_s=prefix,
                race_continued_cpu_s=completed_race, race_routing=tested["routing"],
                gaps=tested.get("gaps"), winner=winner, oracle_finalist_cpu_s=oracle_s,
                measured_solve_cpu_saved=control["cpu_s"]-race["cpu_s"],
                oracle_solve_speedup=control["cpu_s"]/(control["cpu_s"]-oracle_s))


def compare(directory, summary, full):
    bases = {}
    for name, expected in BASES.items():
        path = HERE / "measurements" / name
        if sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Historical control digest changed: {name}")
        with gzip.open(path, "rt") as stream:
            bases[name] = json.load(stream)
    paths = {case: {mode: directory / f"{case}-{mode}.json" for mode in MODES} for case in CASES}
    runs = {case: {mode: read(path) for mode, path in modes.items()} for case, modes in paths.items()}
    results = {}
    for case, pair in runs.items():
        if case == "south-containing":
            archived = bases["full-family-south.json.gz"][case]
        else:
            archived = bases["full-family-amortized.json.gz"]["runs"][case]["control"]
        current = pair["control"]
        old_checks = equality(archived, current)
        del old_checks["chosen"]
        old_checks["winner"] = terminal_choice(archived) == terminal_choice(current)
        old_checks["all_finalist_scores"] = (archived["chosen"][0]["details"]["scores"]
                                            == current["chosen"][0]["details"]["scores"])
        old_checks["same_input"] = scientific_identity(archived) == scientific_identity(current)
        results[case] = dict(compare_pair(current, pair["race"]), historical_control=old_checks)
    validation = {p.name: sha256(p.read_bytes()).hexdigest() for modes in paths.values() for p in modes.values()}
    sources = {name: sha256((HERE / name).read_bytes()).hexdigest()
               for name in ("cold-finalist-race-protocol.md", "cold_finalist_race.py", "cold_finalist_race_trial.py")}
    receipt = dict(cases=results, runs_sha256=validation, historical_sha256=BASES, source_sha256=sources,
                   active_optimizer_sha256=OPTIMIZER_SHA, endpoint_wrapper_sha256=ENDPOINT_SHA)
    write(summary, receipt)
    with full.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(runs=runs, **receipt), separators=(",", ":"),
                                             allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    trial = actions.add_parser("run")
    trial.add_argument("case", choices=CASES)
    trial.add_argument("mode", choices=MODES)
    trial.add_argument("output", type=Path)
    compare_args = actions.add_parser("compare")
    for name in ("directory", "summary", "full"):
        compare_args.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    (saved_control if args.pop("action") == "run" else compare)(**args)
