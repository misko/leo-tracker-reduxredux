"""Publish archived v5 controls alongside the sealed ordinary clock donors."""

import json

from ..__main__ import read_predictions, references
from ..scoring import ARMS, ROLES, distance_km
from . import native_clock_donor as donor
from .clock_model_trial import REPORT as PREPARED
from .clock_model_trial import _gzip
from .full_v5_check import _sha
from .recording_to_v5 import save


def export():
    root = donor.REPORT
    lock = donor.iq.verify_lock(root)
    iq_lock = donor.iq.verify_lock(donor.iq.REPORT)
    prepared_lock = donor.iq.verify_lock(PREPARED / "timing")
    source_clock = json.loads((root / "plan.json").read_bytes())
    bindings = {row["id"]: row for row in source_clock["queries"]}
    ordinary = read_predictions(donor.iq.REPORT / "ordinary-secant-positions.jsonl.gz")
    rows = {"ordinary_v5_secant_fit": []}
    for ident, row in ordinary.items():
        public = bindings[ident]
        if any(row[k] != public[k] for k in ("native_sha256", "catalog_sha256", "tile")):
            raise ValueError(f"{ident} compact v5 is bound to different ordinary detector factors")
        rows["ordinary_v5_secant_fit"].append(dict(row, variant="ordinary_v5_secant_fit"))
    for role in ROLES:
        historical = read_predictions(PREPARED / "timing" / f"{role}.jsonl.gz")
        rows[role] = [historical[ident] for ident in donor.iq.CASES]
        if any(
            row["catalog_sha256"] != bindings[row["id"]]["catalog_sha256"]
            or row["tile"] != bindings[row["id"]]["tile"]
            or row["native_sha256"] == bindings[row["id"]]["native_sha256"]
            for row in rows[role]
        ):
            raise ValueError("capture-era comparison requires its genuine separate native factors")
    output = root / "archived-controls"
    output.mkdir()
    files = {}
    for variant, records in rows.items():
        path = output / f"{variant}.jsonl.gz"
        _gzip(path, records)
        files[path.name] = _sha(path)
    save(output / "prediction-lock.json", dict(
        cases=list(donor.iq.CASES), files=files, receiver_lock_sha256=lock,
        iq_archive_lock_sha256=iq_lock, capture_era_control_lock_sha256=prepared_lock,
    ))
    refs = {r["id"]: r for r in references("smoke", None)[1]}
    metrics = []
    for variant, records in rows.items():
        for row in records:
            ident, result = row["id"], row["result"]
            for arm in ARMS:
                value = result["arms"][arm]
                metrics.append(dict(
                    id=ident, variant=variant, arm=arm, status=result["status"],
                    error_km=distance_km(value["latlon"], refs[ident]["truth"]),
                    rf_rms_hz=value.get("rf_rms_hz"),
                    historical_worker_wall_s=row["worker_wall_s"],
                    native_sha256=row["native_sha256"],
                ))
    save(output / "scores.json", metrics)


if __name__ == "__main__":
    export()
