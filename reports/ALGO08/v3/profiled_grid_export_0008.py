"""Evaluate the one pre-enrolled DS30-0008 saved likelihood operand."""

import ctypes as ct
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from . import profiled_grid_export_check as check


ROOT = check.ROOT.with_name("dense-likelihood-capture-0008")
SAMPLE = "sample-00.npz"
SHAPE = (3574, 243)
PINS = {
    "capture.json": "9861025ec7b0ee0ddeadab2fc161d4b8f2261e0f0cae5395b23aa3fa15ec3996",
    SAMPLE: "f3a614740f3b3c0618315604041e1d4d2bdadfa6c9902f7199a2c93331fce602",
    "history_position.py": "00e349de1a25ac62fb287f970a005737675b5f2e6d45273baa9c914e8a7918f0",
    "marginal.py": "c80ac51249578e8a2c6c6a13a04aaa22a168353b2c758155858106b91507b609",
    check.ORIGINAL.name: check.PINS[check.ORIGINAL.name],
    check.POSTERIOR.name: check.PINS[check.POSTERIOR.name],
}


def checked(path):
    data = path.read_bytes()
    if sha256(data).hexdigest() != PINS[path.name]:
        raise ValueError(f"Unexpected bytes for the pinned physical operand: {path}")
    return data


def calibration(design):
    # The first four hardware columns identify two intercept slots per radio.
    # Column 8 is radio 1's first smooth component for fixed zero, hence zero
    # on radio 2. A nonzero radio 2 entry requires the inserted RF component.
    hardware = design[:, :4] != 0
    if not np.all(np.count_nonzero(hardware, axis=1) == 1):
        raise ValueError("Expected the released radio intercept layout")
    rx2 = np.any(hardware[:, 2:], axis=1)
    supported = int(np.count_nonzero(design[rx2, 8]))
    return dict(arm="fitted_c" if supported else "unclassified", radio2_rows=int(rx2.sum()),
                radio2_nonzero_column8=supported, radio1_rows=int((~rx2).sum()))


def inputs():
    for name in ("history_position.py", "marginal.py"):
        checked(check.RELEASE/"src/leo/analysis/localization_v3"/name)
    checked(check.ORIGINAL)
    checked(check.POSTERIOR)
    capture = json.loads(checked(ROOT/"capture.json"))
    meta = capture["samples"][SAMPLE]
    if (meta["caller"], meta["outcome"]) != ("history_position", "activated"):
        raise ValueError("Original capture does not describe the enrolled native callback")
    args, options = check.operands(checked(ROOT/SAMPLE), SHAPE)
    return args, options, calibration(args[1]), meta


def verify():
    args, options, arm, meta = inputs()
    stock = ct.CDLL(str(check.POSTERIOR)).nb_run_posterior
    with TemporaryDirectory(prefix="physical-profiled-grid-0008-") as temp:
        binary = Path(temp)/"profiled.so"
        pin = check.build(binary, prefix_proof=True)
        result = check.check_case(stock, binary, pin, args, options, "activated", proof=True)
    return dict(case="DS30-0008", inputs=PINS, sample=SAMPLE, capture=meta, calibration=arm,
                native_sha256=pin, result=result, timed=False, full_grid=False)


def authorized_result(path, expected, binary_pin):
    source = Path(path).read_bytes()
    if sha256(source).hexdigest() != expected:
        raise ValueError("The frozen physical correctness result changed")
    data = json.loads(source)
    if (data["case"] != "DS30-0008" or data["sample"] != SAMPLE or data["inputs"] != PINS
            or data["native_sha256"] != binary_pin or data["timed"] or data["full_grid"]
            or not data["result"]["near_equivalence_gate"]
            or data["result"]["applied"] != {"attempted": 1, "profiled_completed": 1}):
        raise ValueError("Require the successful frozen physical correctness result")
    return data


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True, allow_nan=False))
