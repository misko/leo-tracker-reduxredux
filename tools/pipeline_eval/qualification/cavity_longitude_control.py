"""Recheck the original coordinate path on the two already sealed dateline requests."""

import argparse
from pathlib import Path

from ..__main__ import local_output, save_json
from . import cavity_longitude_trial as trial
from . import cavity_payload_transfer as transfer
from .fresh_scenes import _read, _sha

REPORT = trial.REPORT
LOCK = "control-lock.json"


def run(work):
    input_lock = _read(REPORT / "input-lock.json")
    path = work / "requests.json"
    if _sha(path) != input_lock["requests_sha256"]:
        raise ValueError("the longitude comparison requests changed")
    package = transfer.bound_packages(transfer.RELEASE)["small"]
    original = _read(REPORT.with_name("cavity-payload") / "package.json")
    if package != original:
        raise ValueError("the comparator is not the published original small package")
    lock = dict(
        input_lock_sha256=_sha(REPORT / "input-lock.json"),
        base_sha256=package["archive_sha256"],
        observer_sha256=_sha(transfer.OBSERVER),
        sources={p.name: _sha(p) for p in (Path(__file__), Path(transfer.__file__))},
        cpu=7,
        cases=["positive", "far-omitted"],
    )
    save_json(REPORT / LOCK, lock)
    rows = []
    for row, native, config, archive, inventory in _read(path)[:2]:
        native, config, archive = map(Path, (native, config, archive))
        if (
            (_sha(native), _sha(config)) != (row["native_sha256"], row["track_config_sha256"])
            or trial.snapshots(archive) != input_lock["archives"][str(archive)]
        ):
            raise ValueError("original package would read a changed input")
        job = row, native, config, archive, inventory
        rows.append(transfer.capped(work, transfer.RELEASE, job, "small", lock["cpu"]))
    save_json(
        REPORT / "control-predictions.json",
        dict(lock_sha256=_sha(REPORT / LOCK), rows=rows),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    run(local_output(parser.parse_args().work))
