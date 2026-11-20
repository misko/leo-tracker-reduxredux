"""Repeat the predeclared roof parity on byte-identical local input copies."""

import argparse
import gzip
import json
import shutil
from pathlib import Path
from unittest.mock import patch

from . import v5_regional_reference as ref

LIMIT = 330


def local_input(source, destination, digest):
    ref.checked(source, digest)
    shutil.copyfile(source, destination)
    ref.checked(destination, digest)


def staged_roof(root):
    request, case = ref.roof_request()
    job = request["job"]
    work = root / "input"
    work.mkdir(parents=True, exist_ok=False)
    for name in ("native_input", "track_config"):
        data = job[name]
        destination = work / (name + ".json")
        local_input(Path(data["path"]), destination, data["sha256"])
        data["path"] = str(destination)

    original = Path(job["tle_root"])
    staged = work / "tle"
    entries = list(original.rglob("*.tle"))
    inventory = {path.name: path for path in entries}
    if len(inventory) != len(entries) or inventory.keys() != request["causal_snapshots"].keys():
        raise ValueError("original TLE archive membership changed")
    for name, digest in request["causal_snapshots"].items():
        source = inventory[name]
        if int(name.split("-", maxsplit=1)[0]) >= case["cutoff_utc_ns"]:
            raise ValueError("roof input contained a noncausal catalogue")
        destination = staged / source.relative_to(original)
        destination.parent.mkdir(parents=True, exist_ok=True)
        local_input(source, destination, digest)
    job["tle_root"] = str(staged)
    return request, case


def run(root):
    if root.is_relative_to("/mnt/qnap01"):
        raise ValueError("QNAP is read-only")
    report = ref.REPORT
    prior = ref.read(report / "roof-prediction.json")
    if prior["result"]["status"] != "timed_out":
        raise ValueError("the repeat is specific to the observed original deadline")
    request, case = staged_roof(root)
    retry = report / "roof-retry"
    retry.mkdir(exist_ok=False)
    plan = retry / "plan.json"
    ref.write(
        plan,
        dict(
            case=ref.ROOF,
            resources=dict(deadline_s=LIMIT, memory_bytes=ref.MEMORY, cpu=ref.CPU),
            previous_prediction_lock_sha256=ref.sha(report / "roof-prediction-lock.json"),
            earlier_archive_sha256=ref.sha(ref.ROOF_SOURCE),
            request_sha256=case["request"]["sha256"],
            native_sha256=case["native"]["sha256"],
            catalog_sha256=case["catalog"]["sha256"],
            adapter_sha256=ref.sha(Path(ref.__file__)),
            staged_launcher_sha256=ref.sha(Path(__file__)),
        ),
    )
    with patch.object(ref, "LIMIT", LIMIT):
        row = ref.run_request(request, root / "roof")
    prediction = retry / "prediction.json"
    ref.write(prediction, row)
    lock = retry / "prediction-lock.json"
    ref.write(lock, {path.name: ref.sha(path) for path in (plan, prediction)})
    ref.checked(ref.ROOF_SOURCE, ref.read(plan)["earlier_archive_sha256"])
    payload = gzip.decompress(ref.ROOF_SOURCE.read_bytes())
    (previous,) = (row for row in map(json.loads, payload.splitlines()) if row["id"] == ref.ROOF)
    ref.write(retry / "parity.json", ref.parity(row["result"], previous["result"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root.resolve())
