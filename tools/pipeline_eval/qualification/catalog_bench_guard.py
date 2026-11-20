"""Replay the historic fixed 25 km guard offer in a separate checksum control."""

import argparse
from pathlib import Path
from unittest.mock import patch

from .. import iq_service, whole_iq
from ..__main__ import local_output, save_json, write
from . import catalog_bench as trial
from . import catalog_bench_results as results
from .full_v5_check import _sha

IDENT = "DS26-0102"
REPORT = trial.REPORT / "guard-control"


def freeze(primary, work):
    primary_lock = whole_iq.checked(
        primary / "source-lock.json", _sha(trial.REPORT / "source-lock.json")
    )
    lock = whole_iq.read(primary_lock)
    (previous,) = (
        n for n in lock["exclusions"]["prior"] if "/original-schedule/track-preparation/" in n
    )
    earlier = whole_iq.checked(Path(previous), lock["exclusions"]["prior"][previous])
    prior = whole_iq.read(earlier)["cases"][IDENT]
    row = prior | {"cpu": trial.CPUS[1], "order": list(reversed(trial.BRANCHES))}
    if row["role"] != "shifted":
        raise ValueError("fixed guard control must retain the original shifted offer")
    source = whole_iq.checked(primary / "production-propagation.py", lock["production_sha256"])
    lock.update(
        cases={IDENT: row},
        sequence=[IDENT],
        primary_source_sha256=_sha(primary_lock),
        fixed_offer_sha256=_sha(earlier),
    )
    lock["research_files"][str(Path(__file__))] = _sha(Path(__file__))
    work.mkdir()
    write(work / source.name, source.read_bytes())
    save_json(work / "source-lock.json", lock)
    save_json(REPORT / "source-lock.json", lock)
    return row


def publish(work):
    lock = whole_iq.read(
        whole_iq.checked(work / "source-lock.json", _sha(REPORT / "source-lock.json"))
    )
    legs = {branch: results.receipt(work, lock, IDENT, branch) for branch in trial.BRANCHES}
    save_json(
        REPORT / "result.json",
        dict(
            legs=legs,
            audit=results.parity(legs),
            stage=[results.timing(leg) for leg in legs.values()],
        ),
    )
    results.lock_files(
        REPORT, "prediction-lock.json", ("source-lock.json", "result.json"), cases=[IDENT]
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("primary", type=local_output)
    parser.add_argument("work", type=local_output)
    args = parser.parse_args()
    row = freeze(args.primary, args.work)
    with patch.object(iq_service, "MODULE", trial.MODULE):
        for branch in row["order"]:
            trial.attempt(args.work, IDENT, row, branch)
    publish(args.work)
