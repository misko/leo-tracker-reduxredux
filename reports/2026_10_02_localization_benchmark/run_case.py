import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from bundle import Data
from models import run_models
from selection import MODEL_NAMES, ROOT


def serializable(value):
    if isinstance(value, np.ndarray):
        return serializable(value.tolist())
    if isinstance(value, np.generic):
        return serializable(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(item) for item in value]
    return value


def save_atomic(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(serializable(value), indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    args = parser.parse_args()
    selection = json.loads((ROOT / "selection.json").read_text())
    if args.session_id not in [selection["original_sample"], *selection["selected"]]:
        parser.error("Session must belong to frozen benchmark")
    directory = ROOT / "scans" / args.session_id
    data = Data(directory)
    started = time.monotonic()
    receipt = {
        "session_id": args.session_id,
        "expected_models": list(MODEL_NAMES),
        "dataset": "original_sample" if args.session_id == selection["original_sample"] else "DS11",
        "input_sha256": {
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ("bundle.json", "bundle.npz")
        },
        "source_sha256": {
            str(path.relative_to(ROOT.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
            for source in (
                ROOT,
                ROOT.parent / "2026_10_02_coherent_localization",
                ROOT.parent / "2026_10_02_full_curve_glrt",
                ROOT.parent / "2026_10_02_shared_rx_position",
            )
            for path in sorted(source.glob("*.py"))
        },
        "models": {},
        "status": "running",
        "scope": (
            "single scan, all-data conditional fits; no reference coordinates passed to models"
        ),
    }

    def checkpoint(results):
        receipt["models"] = results
        receipt["elapsed_s"] = time.monotonic() - started
        save_atomic(directory / "fits.json", receipt)
        print(
            json.dumps(
                {
                    "session_id": args.session_id,
                    "models_finished": len(results),
                    "elapsed_s": receipt["elapsed_s"],
                }
            ),
            flush=True,
        )

    checkpoint({})
    results = run_models(data, checkpoint=checkpoint)
    if set(results) != set(MODEL_NAMES):
        raise RuntimeError(
            f"Missing or unexpected model receipts: {set(results) ^ set(MODEL_NAMES)}"
        )
    receipt["status"] = "finished"
    checkpoint(results)


if __name__ == "__main__":
    main()
