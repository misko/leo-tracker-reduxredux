"""Pair fresh DS30 decisions with frozen per-arm outputs; stop on any unaccounted recording."""
import csv
import json
from pathlib import Path
import sys

import numpy as np
from tools.pipeline_eval.scoring import distance_km


def summarize(input_dir, destination):
    report = Path(__file__).resolve().parents[2] / "2026_11_21_ds30_full"
    old = {(r["case"], r["calibration"]): r for r in csv.DictReader((report/"recordings.csv").open())
           if r["method"] == "compact_two_scan"}
    # Frozen DS30 evaluation coordinates enter after the predictions have been written.
    ref = (37.849061591561885, -122.48574968092912)
    cases = sorted({key[0] for key in old})
    if len(cases) != 455:
        raise ValueError("Incomplete DS30 benchmark")
    rows = []
    for case in cases:
        prediction = json.loads((input_dir / (case + ".json")).read_bytes())
        assert prediction["case"] == case
        for arm, fit in prediction["arms"].items():
            previous = old[(case, arm)]
            assert previous["status"] == prediction["status"]
            ll = fit["latlon"]
            assert (ll is not None) == (previous["fix"] == "True")
            if ll is not None:
                assert ll == [float(previous[k]) for k in ("latitude", "longitude")]
                assert fit["rf_rms_hz"] == float(previous["frequency_rms_hz"])
            rows.append(dict(case=case, arm=arm, state=prediction["status"],
                latitude=ll[0] if ll else None, longitude=ll[1] if ll else None,
                position_error_km=distance_km(ll, ref), rf_rms_hz=fit.get("rf_rms_hz"),
                orbit_policy=prediction.get("orbit_policy"), evidence_checked=prediction["evidence_checked"]))
    assert len(rows) == 910
    with (destination / "ds30-replay.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    for arm in ("fitted_c", "c0"):
        fixed = [r for r in rows if r["arm"] == arm and r["state"] == "ok"]
        print(arm, len(fixed), np.percentile([r["position_error_km"] for r in fixed], [50,90,95,99]),
              np.median([r["rf_rms_hz"] for r in fixed]))


if __name__ == "__main__":
    summarize(*map(Path, sys.argv[1:]))
