"""Isolate each causal regional catalogue before inference can open it."""

import json

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_inference_audit import ROOT, validate_elements


def run():
    source = json.loads(
        (ROOT / "reports/2026_10_18_dsx01_retention_localization/causal_tles.json").read_text()
    )
    for k in range(1, 6):
        case = f"DSX01-S0{k}"
        stem = (
            "2026_10_17_dsx01_polynomial_satellite_dive"
            if k == 1
            else "2026_10_17_robust_curve_reassociation"
        )
        folder = ROOT / "reports" / stem / "frozen_inputs" / case
        receipt = json.loads((folder / "receipt.json").read_text())
        with np.load(folder / "bank.npz") as bank:
            numbers = list(map(int, bank["norad"]))
        records = {str(n): source[case]["satellites"][str(n)] for n in numbers}
        for record in records.values():
            validate_elements(record, receipt["cutoff_utc_ns"])
        payload = dict(
            cutoff_utc_ns=receipt["cutoff_utc_ns"],
            origin_utc_ns=receipt["origin_utc_ns"],
            bank_sha256=receipt["bank_sha256"],
            satellites=records,
            later_scan_catalogues_excluded=True,
            candidate_selection="exactly the original regional bank, no association whitelist",
        )
        output = ROOT / "reports/2026_10_18_dsx01_clean_region" / case / "nominal_elements.json"
        if output.exists() and json.loads(output.read_text()) != json.loads(json.dumps(payload)):
            raise ValueError("existing isolated catalogue differs; preserve it")
        write(output, payload)
        print(case, len(records), flush=True)


if __name__ == "__main__":
    run()
