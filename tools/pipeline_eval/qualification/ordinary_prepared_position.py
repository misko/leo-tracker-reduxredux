"""Recompute held native candidates, splice, and refit both clock calibration arms."""

import argparse
import gzip
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from ..__main__ import encoded, local_output, save_json, write
from ..variants import iq_stream
from . import ordinary_front_position
from . import ordinary_prepared_eval as detector
from .full_v5_check import NATIVE_LIBRARY, _sha
from .pilot_kernel_eval import _digest

REPORT = detector.REPORT
METHOD = "ordinary_prepared_position"
CONTROL = "ordinary_prepared_capture_control"
BOUNDARY = "Twelve held prepared-GLRT visits plus authenticated ordinary factor archive"
TEMPLATES = Path("/srv/bulk/leo-dev/20261119-ordinary-glrt")


def position(case, work, cpu):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    measured_path = REPORT / f"{case}.json.gz"
    lock = json.loads((REPORT / "prediction-lock.json").read_bytes())
    if _sha(measured_path) != lock["files"][measured_path.name]:
        raise ValueError("Prepared input receipt no longer matches the sealed detector trial")
    measured = json.loads(gzip.decompress(measured_path.read_bytes()))
    library = work / "host" / NATIVE_LIBRARY.name
    if _sha(library) != measured["libraries"]["ordinary_prepared"]:
        raise ValueError("Prepared detector library differs from the measured build")
    templates = TEMPLATES / f"{case}-arm-input"
    exact, control = (
        np.fromfile(templates / f"{name}.c128", dtype="<c16") for name in ("exact", "control")
    )
    table = {
        "rows": [],
        "controls": measured["controls"],
        "executable_sha256": {METHOD: _sha(library)},
    }
    with NativeShortWindow(
        str(library), exact, control, sample_rate_hz=10_000_000, fractional_epoch=True
    ) as context:
        for row in measured["rows"]:
            entry = {k: row[k] for k in ("segment", "sequence", "status", "visit", "iq_sha256")}
            if row["status"] == "processed":
                path = work / f"{case}-inputs" / f"{row['segment']}-{row['sequence']}.ci16"
                samples, iq, _, _ = detector.load_ci16(path, mapped=True)
                payload = context.analyze(samples)
                if (
                    not row["exact"]
                    or iq != row["iq_sha256"]
                    or (_digest(encoded(payload)) != row["archive_payload_sha256"])
                ):
                    raise ValueError("Fresh candidate payload does not match its held measurement")
                entry.update(exact=True, payloads={METHOD: payload})
            table["rows"].append(entry)
    adapter = work / "position-inputs"
    adapter.mkdir(exist_ok=True)
    write(adapter / f"{case}-host.json.gz", gzip.compress(encoded(table), mtime=0))
    paths = (
        Path(__file__),
        Path(ordinary_front_position.__file__),
        measured_path,
        REPORT / "source-lock.json",
        templates / "exact.c128",
        templates / "control.c128",
    )
    inventory = {str(p): _sha(p) for p in paths}
    seam = SimpleNamespace(SCHEDULE=detector.archive.SCHEDULE, sources=lambda: inventory)
    with (
        patch.multiple(
            ordinary_front_position,
            REPORT=adapter,
            METHOD=METHOD,
            CONTROL=CONTROL,
            BOUNDARY=BOUNDARY,
            ordinary_front_eval=seam,
        ),
        patch.object(iq_stream, "MAX_CHUNK_PREFIX", detector.archive.CHUNK_PREFIX),
    ):
        ordinary_front_position.position(case, work, cpu)
    receipt_path = work / f"{case}-position.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt["source_hashes"] = inventory
    save_json(receipt_path, receipt)


def package(work):
    cases = detector.CASES
    receipts = {case: json.loads((work / f"{case}-position.json").read_bytes()) for case in cases}
    for field, name in (("trial", "positions.jsonl.gz"), ("stock", "control-positions.jsonl.gz")):
        rows = b"".join(encoded(r[field]) + b"\n" for r in receipts.values())
        write(REPORT / name, gzip.compress(rows, mtime=0))
    save_json(REPORT / "position-receipts.json", receipts)
    path = REPORT / "prediction-lock.json"
    lock = json.loads(path.read_bytes())
    names = (
        "figures.json",
        "positions.jsonl.gz",
        "control-positions.jsonl.gz",
        "position-receipts.json",
    )
    lock["files"].update({name: _sha(REPORT / name) for name in names})
    save_json(path, lock)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", required=True, type=Path)
    cli.add_argument("--case", choices=detector.CASES)
    cli.add_argument("--cpu", type=int, default=16)
    args = cli.parse_args()
    work = local_output(args.work)
    if args.case:
        position(args.case, work, args.cpu)
    else:
        package(work)
