"""Apply the tested direct-IQ estimator to training-prefix dense acquisitions."""
import json
from pathlib import Path

import run_corrected_direct as direct

HERE = Path(__file__).resolve().parent
DENSE = Path("/srv/bulk/leo/experiments/scan-fw-32a202-phase-replay/acquisition-dense-v1")


def pairs():
    output = {}
    for selected in json.loads((direct.REPORT / "selection.json").read_text())["visits"]:
        visit = selected["visit_index"]
        probes = json.loads((DENSE / f"visit-{visit:06d}.corrected-dense.json").read_text())["product"]["probes"]
        best = {}
        for probe in probes:
            passing = [row for row in probe["candidates"] if row["passed_fractional_margin_gate"]]
            if passing:
                best[probe["probe_index"], probe["receiver_id"]] = min(passing, key=lambda row: (-row["fractional_margin"], row["candidate_rank"]))
        for index in range(3):
            if (index, 0) in best and (index, 1) in best:
                output[visit] = tuple({
                    "tracking_absolute_baseband_cfo_hz": best[index, rx]["fractional_tracking_cfo_hz"],
                    "candidate_rank": best[index, rx]["candidate_rank"],
                } for rx in (0, 1))
                break
    return output


if __name__ == "__main__":
    direct.HERE = HERE / "dense-direct"
    direct.HERE.mkdir(exist_ok=True)
    direct._candidate_pairs = pairs
    direct.main()
