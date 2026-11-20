"""Attach the sealed same-ordinary-factor compact v5 control to the clock-chain figure."""

import argparse
import json
from pathlib import Path

from ..__main__ import local_output, read_predictions, save_json
from . import clock_chain_trial as chain
from .full_v5_check import _sha

SOLVER = chain.REPORT.with_name("solver-memory")
CONTROL_FILE = "same-ordinary-v5.jsonl.gz"


def bind_control(capture, control):
    keys = ("id", "native_sha256", "catalog_sha256", "tile")
    setup = control["method"], control["detector"], control["mode"]
    if any(capture[key] != control[key] for key in keys) or setup != (
        "history_stream_prep",
        "ordinary",
        "matched-tile",
    ):
        raise ValueError("Compact v5 control uses different ordinary factors or causal authority")
    return dict(control, position_error_km=chain._errors(control["id"], control["result"]))


def publish(report):
    if (report / "figure-lock.json").exists():
        raise ValueError("The selected report already contains a sealed figure comparison")
    chain_sha = chain.iq_joint_trial.verify_lock(report)
    solver_sha = chain.iq_joint_trial.verify_lock(SOLVER)
    product = json.loads((report / "stage-receipts.json").read_bytes())
    controls = read_predictions(SOLVER / "control-positions.jsonl.gz")
    rows = [bind_control(product[case], controls[case]) for case in chain.CASES]
    chain._gzip(report / CONTROL_FILE, rows)
    original = json.loads((report / "prediction-lock.json").read_bytes())
    files = original["files"] | {
        CONTROL_FILE: _sha(report / CONTROL_FILE),
        "prediction-lock.json": chain_sha,
    }
    lock = dict(
        cases=list(chain.CASES),
        files=files,
        compact_control_parent_lock_sha256=solver_sha,
        compact_control_parent_product_sha256=_sha(SOLVER / "control-positions.jsonl.gz"),
    )
    save_json(report / "figure-lock.json", lock)
    if not (report / "figures.json").exists():
        descriptor = json.loads((chain.REPORT / "figures.json").read_bytes())
        if not all(row["scope"]["fresh_ordinary_raw"] for row in product.values()):
            descriptor["charts"][0]["caption"] = (
                "The fresh clock-offset fits use authenticated complete ordinary factors. "
                "The stage receipts identify which recordings were freshly replayed and which "
                "used the earlier complete ordinary product. The compact v5 comparison shares "
                "the ordinary factors, catalogue and tile. The four original v5 options use "
                "the capture-era factors."
            )
        save_json(report / "figures.json", descriptor)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    publish(local_output(parser.parse_args().report))
