"""Pool the four complete optimized IQ measurements with their matched ordinary endpoints."""

import argparse
from pathlib import Path

from ..__main__ import local_output, read_predictions, save_json
from .full_receiver_comparison import SCREEN, require_fields, roster_matches, seal, sha
from .phase_support_results import pack

PANELS = (
    ("streamlined/whole-fractional", ("DS26-0036", "DS29-0082"), "whole_cavity"),
    ("next/full-held-pair", ("DS26-0237", "DS29-0174"), "held_stock_factor_cavity"),
)


def matched(candidate, control, control_method):
    require_fields(control, dict(method=control_method, mode="matched-tile"))
    require_fields(
        candidate,
        dict(
            id=control["id"],
            method="whole_fractional",
            mode=control["mode"],
            tile=control["tile"],
            catalog_sha256=control["catalog_sha256"],
            origin_native_sha256=control["native_sha256"],
        ),
    )
    if candidate["result"]["status"] != control["result"]["status"]:
        return False
    return all(
        candidate["result"]["arms"][arm].get(key) == control["result"]["arms"][arm].get(key)
        for arm in ("c0", "fitted_c")
        for key in ("latlon", "rf_rms_hz")
    )


def publish(out):
    rows, controls, evidence = [], [], {}
    for folder, ids, control_method in PANELS:
        source = SCREEN / folder
        names = (
            "positions.jsonl.gz",
            "control-positions.jsonl.gz",
            "comparison.json",
            "stages.json.gz",
        )
        lock = seal(source, "prediction-lock.json", names)
        require_fields(lock, dict(source_lock_sha256=sha(source / "source-lock.json")))
        candidate, stock = [read_predictions(source / name) for name in names[:2]]
        roster_matches(candidate, ids, folder)
        roster_matches(stock, ids, folder)
        for ident in ids:
            equal = matched(candidate[ident], stock[ident], control_method)
            evidence[ident] = dict(
                study=folder,
                source_lock=lock["source_lock_sha256"],
                exact_arms=equal,
                prediction_lock=sha(source / "prediction-lock.json"),
                control_boundary=control_method,
                control_native_sha256=stock[ident]["native_sha256"],
            )
            rows.append(candidate[ident])
            controls.append(
                dict(
                    stock[ident], measured_method=control_method, method="ordinary_factor_endpoint"
                )
            )
    out.mkdir(exist_ok=True, parents=True)
    pack(out / "positions.jsonl.gz", rows)
    pack(out / "controls.jsonl.gz", controls)
    save_json(out / "comparison.json", evidence)
    files = ("positions.jsonl.gz", "controls.jsonl.gz", "comparison.json")
    save_json(
        out / "figure-lock.json", dict(cases=list(evidence), files={n: sha(out / n) for n in files})
    )
    save_json(
        out / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="full-iq-four",
                    method="whole_fractional",
                    scope="roof",
                    cases=list(evidence),
                    title="Complete saved IQ through position on four recordings",
                    caption=(
                        "Two original and two hash-selected recordings. "
                        "Ordinary controls use the same native inputs. "
                        "Original v5 options used capture-era factors. One physical roof."
                    ),
                    seal="figure-lock.json",
                    provenance=["comparison.json"],
                    series=[
                        dict(
                            key="one",
                            label="Optimized full IQ",
                            file=files[0],
                            value="whole_fractional",
                            native_authority="ordinary",
                            native_field="origin_native_sha256",
                        ),
                        dict(
                            key="stock",
                            label="Ordinary control",
                            file=files[1],
                            value="ordinary_factor_endpoint",
                            native_authority="ordinary",
                            match=["tile", "catalog_sha256", "mode"],
                        ),
                    ],
                )
            ],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=SCREEN / "next/complete-four")
    publish(local_output(parser.parse_args().out))
