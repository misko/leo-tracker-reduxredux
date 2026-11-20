"""Replay the preselected disjoint panel from its canonical JSON seal."""

import argparse
import json
from pathlib import Path

from ..__main__ import ROOT, save_json
from . import differential_pilot_eval as study
from . import oracle_start
from .full_v5_check import _load_case, _sha


def held_plan(work, primary):
    filename = work / "confirmation-lock.json"
    sealed = json.loads(filename.read_bytes())
    authority = oracle_start.EXISTING / "prediction-lock.json"
    if sealed["authority_sha256"] != _sha(authority):
        raise ValueError("Confirmation's wide control changed")
    if set(sealed["cases"]) != set(study.CASES):
        raise ValueError("Confirmation recordings differ from preregistration")
    for case, selected in sealed["cases"].items():
        if _sha(work / f"{case}.json.gz") != sealed["primary"][case]:
            raise ValueError("Primary raw result changed")
        earliest = max(r["visit"] for r in primary["cases"][case]) + 1
        visits = {r["visit"] for r in selected}
        if (
            len(selected) > 2
            or len(selected) != len(visits)
            or any(
                r["case"] != case or r["visit"] < earliest or r["kind"] != "miss" for r in selected
            )
        ):
            raise ValueError("Confirmation drifted beyond its disjoint interval")
    return filename, sealed


def resume(work):
    primary, libraries = study.bind(work)
    path, sealed = held_plan(work, primary)
    source = Path(__file__)
    receipt = dict(
        plan_sha256=_sha(path),
        source=str(source.relative_to(ROOT)),
        source_sha256=_sha(source),
        receiver_id_format="json_list",
    )
    execution = work / "confirmation-execution.json"
    if execution.exists():
        if json.loads(execution.read_bytes()) != receipt:
            raise ValueError("Confirmation continuation code changed")
    else:
        save_json(execution, receipt)
    for case, rows in sealed["cases"].items():
        if rows and not (work / f"{case}-confirmation.json.gz").exists():
            study.replay(_load_case(case), rows, libraries, work, suffix="-confirmation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=study.WORK)
    resume(parser.parse_args().work)
