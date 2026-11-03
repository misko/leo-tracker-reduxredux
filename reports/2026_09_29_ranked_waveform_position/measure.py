import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PREVIOUS = HERE.parent / "2026_09_29_waveform_trajectory"
sys.path.insert(0, str(PREVIOUS))
from study import errors, fit, frames_for  # noqa: E402


def main():
    plan = json.loads((HERE / "plan.json").read_text())
    inventory = json.loads((HERE / "inventory.json").read_text())
    for doc in (plan, inventory):
        for path, digest in doc["hashes"].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    expected = {(r["unit_id"], r["receiver_id"]) for r in plan["selections"]}
    assert len(inventory["rows"]) == len(expected) == 72
    assert {(r["unit_id"], r["receiver_id"]) for r in inventory["rows"]} == expected
    rows = []
    for r in inventory["rows"]:
        result = {
            k: r[k]
            for k in (
                "unit_id",
                "panel_id",
                "receiver_id",
                "session_id",
                "track_id",
                "visit",
                "status",
            )
        }
        try:
            frames = frames_for(r)
            f = fit(frames, np.arange(20, 220))
            result.update(
                residual_frequency_hz=f,
                boundary=abs(f) >= 1499.999,
                cached_frame_nmse=errors(frames, 0).tolist(),
                refined_frame_nmse=errors(frames, f).tolist(),
            )
        except Exception as exc:
            result.update(status="failed", reason=f"{type(exc).__name__}: {exc}")
        rows.append(result)
    dependencies = json.loads((PREVIOUS / "results.json").read_text())["hashes"]
    files = [
        ROOT / p
        for p in dependencies
        if p.endswith((".py", ".mat")) or p.startswith("tests/fixtures/")
    ]
    files += [HERE / n for n in ("plan.json", "inventory.json", "measure.py", "PROTOCOL.md")]
    files += [ROOT / r["path"] for r in inventory["rows"] if r["status"] == "ok"]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    summary = {}
    for ds in ("DS7", "DS8", "DS9", "all"):
        selected = [r for r in rows if ds == "all" or r["panel_id"].startswith(ds)]
        valid = [r for r in selected if r["status"] == "ok"]
        gains = np.array(
            [np.mean(r["cached_frame_nmse"]) - np.mean(r["refined_frame_nmse"]) for r in valid]
        )
        summary[ds] = dict(
            planned=len(selected),
            returned=len(valid),
            improved=int(sum(gains > 1e-10)),
            mean_pilot_gain=float(np.mean(gains)) if valid else None,
            median_pilot_gain=float(np.median(gains)) if valid else None,
            boundaries=sum(r["boundary"] for r in valid),
            median_absolute_residual_hz=float(
                np.median([abs(r["residual_frequency_hz"]) for r in valid])
            )
            if valid
            else None,
            maximum_absolute_residual_hz=max(
                (abs(r["residual_frequency_hz"]) for r in valid), default=None
            ),
        )
    (HERE / "measurements.json").write_text(
        json.dumps(dict(hashes=hashes, rows=rows, summary=summary), indent=2, allow_nan=False)
        + "\n"
    )
    print(
        json.dumps(
            dict(
                planned=len(rows),
                returned=sum(r["status"] == "ok" for r in rows),
                boundaries=sum(r.get("boundary", False) for r in rows),
            )
        )
    )


if __name__ == "__main__":
    main()
