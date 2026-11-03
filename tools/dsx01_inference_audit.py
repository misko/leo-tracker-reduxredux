"""Fail-closed causal input checks for the DSX01 regional research tools.

Published diagnostic archives remain immutable. These checks authorize only
past element records; a record's old epoch alone never establishes causality.
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from sgp4.api import Satrec

from leo.sky.propagation import parse_element_sets

ROOT = Path(__file__).resolve().parents[1]
CENTER = (37.906, -122.545)
BOX_HALF_WIDTH_KM = 12.5
APPROVED_REPORT_INPUTS = {
    "receipt.json",
    "bank.npz",
    "curves.json",
    "glrt_scores.json",
    "measurements.json",
    "noise_features.json",
    "causal_tles.json",
    "previous.tle",
    "previous_receipt.json",
    "frame_coherent_calibration.json",
    "causal_forecast_inputs_strict.json",
}
APPROVED_OWN_INPUTS = {
    "atlas.json",
    "discovery.json",
    "atlas_progress.json",
    "causal_history.json",
    "result.json",
    "fresh_linear_nominations.json",
    "input_audit.json",
    "nominal_elements.json",
}


class InferenceReadGuard:
    """Reject diagnostic and saved-estimate files; retain a real read receipt."""

    def __init__(self, output_root):
        self.output_root = str(output_root)
        self.read_paths = set()

    def check_path(self, path):
        if not isinstance(path, (str, bytes)):
            return
        text = str(path)
        name = Path(text).name
        if str(ROOT / "reports") not in text:
            return
        own = text.startswith(self.output_root + "/")
        diagnostic = (
            "following" in text.lower()
            or "oracle_only" in text.lower()
            or name.startswith("position_and_gradient_summary")
            or name in {"gps_invariance.json", "README.md"}
        )
        forbidden = name in {
            "endpoints.json",
            "seed_bundle.json",
            "conditional_smooth_background.json",
        } or name.endswith("_center.json")
        approved = name in (APPROVED_OWN_INPUTS if own else APPROVED_REPORT_INPUTS)
        if diagnostic or (forbidden and not own) or not approved:
            raise ValueError(f"forbidden diagnostic or inherited estimate input: {text}")
        self.read_paths.add(text)

    def __call__(self, event, args):
        if event == "open":
            path, mode, _ = args
            if mode is not None and "r" in mode:
                self.check_path(path)

    def install(self):
        sys.addaudithook(self)


def causal_record(record, cutoff, *, epoch_key="element_epoch_utc_ns"):
    for key in (epoch_key, "collected_utc_ns"):
        if key not in record or not isinstance(record[key], int) or record[key] > cutoff:
            raise ValueError(f"missing or noncausal TLE {key}")
    return True


def element_epoch_ns(lines):
    sat = Satrec.twoline2rv(*lines)
    return int(round((sat.jdsatepoch - 2440587.5) * 86400e9 + sat.jdsatepochF * 86400e9))


def validate_elements(record, cutoff):
    causal_record(record["provenance"], cutoff)
    if element_epoch_ns(record["lines"]) > cutoff:
        raise ValueError("TLE bytes have a future element epoch")
    if (
        abs(element_epoch_ns(record["lines"]) - record["provenance"]["element_epoch_utc_ns"])
        > 100000
    ):
        raise ValueError("TLE bytes disagree with epoch provenance")


def load_isolated_catalogue(path, receipt, numbers):
    if not path.exists():
        raise ValueError("export isolated causal inputs with export_dsx01_isolated_elements.py")
    data = json.loads(path.read_text())
    for key in ("cutoff_utc_ns", "origin_utc_ns", "bank_sha256"):
        if data[key] != receipt[key]:
            raise ValueError("isolated causal catalogue belongs to another scan/bank")
    if set(map(int, data["satellites"])) != set(map(int, numbers)):
        raise ValueError("isolated catalogue must preserve the complete regional candidate bank")
    return data["satellites"]


def audit_scan_inputs(scan):
    receipt = scan.receipt
    cutoff = receipt["cutoff_utc_ns"]
    if cutoff > receipt["origin_utc_ns"] or receipt["reference_position_used"] is not False:
        raise ValueError("invalid causal cutoff or reference-position-dependent bank")
    expected = set(map(int, scan.norads))
    if len(expected) != len(scan.norads) or not expected <= set(map(int, scan.elements)):
        raise ValueError("candidate catalogue and causal elements differ")
    for record in scan.elements.values():
        validate_elements(record, cutoff)
    # Reconstruct the exact element text originally used to generate the bank.
    # The exporter follows bank order and preserves its original satellite name.
    text = "".join(
        f"0 {scan.elements[str(int(n))]['provenance']['name']}\n"
        + "\n".join(scan.elements[str(int(n))]["lines"])
        + "\n"
        for n in scan.norads
    )
    if hashlib.sha256(text.encode()).hexdigest() != receipt["latest_tle_sha256"]:
        raise ValueError("causal element bytes do not bind to the orbit-bank receipt")
    folder = ROOT / "reports/2026_10_18_dsx01_orbit_uncertainty/causal_inputs" / scan.case
    previous = json.loads((folder / "previous_receipt.json").read_text())
    path = folder / "previous.tle"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != previous["catalogue_sha256"] or digest != receipt["previous_tle_sha256"]:
        raise ValueError("previous element bytes do not match their causal provenance")
    for record in previous["sources"].values():
        causal_record(record, cutoff, epoch_key="epoch_utc_ns")
    previous_catalogue = parse_element_sets(path.read_text())
    if set(previous_catalogue.satellite_numbers) != set(map(int, previous["sources"])):
        raise ValueError("previous catalogue and provenance inventories differ")
    for number, epoch in zip(
        previous_catalogue.satellite_numbers, previous_catalogue.element_epoch_utc_ns(), strict=True
    ):
        if (
            epoch > cutoff
            or abs(int(epoch) - previous["sources"][str(number)]["epoch_utc_ns"]) > 100000
        ):
            raise ValueError("previous TLE bytes have a noncausal or mismatched epoch")
    return dict(
        case=scan.case,
        cutoff_utc_ns=cutoff,
        origin_utc_ns=receipt["origin_utc_ns"],
        candidate_count=len(expected),
        latest_max_collection_utc_ns=max(
            r["provenance"]["collected_utc_ns"] for r in scan.elements.values()
        ),
        latest_max_epoch_utc_ns=max(
            r["provenance"]["element_epoch_utc_ns"] for r in scan.elements.values()
        ),
        previous_count=len(previous["sources"]),
        latest_tle_sha256=receipt["latest_tle_sha256"],
        previous_tle_sha256=digest,
        previous_element_byte_epochs_validated=True,
        isolated_nominal_catalogue=str(scan.element_input_path),
        bank_sha256=receipt["bank_sha256"],
        candidate_filter="broad regional visibility, no identity whitelist or GPS coordinate",
        bank_region_center=receipt["regional_center"],
        bank_region_radius_km=receipt["radius_km"],
        search_region_center=CENTER,
        search_box_width_km=25,
        prior_scale_interpretation="engineering hypotheses, developed on DSX01",
    )


def validate_history(history, cutoff):
    allowed = {"name", "lines", "epoch", "collected_utc_ns", "snapshot_digest"}
    count = 0
    for records in history.values():
        for record in records:
            if set(record) - allowed:
                raise ValueError("unexpected field in inference-only TLE history")
            causal_record(record, cutoff, epoch_key="epoch")
            if element_epoch_ns(record["lines"]) > cutoff:
                raise ValueError("future epoch in history element bytes")
            count += 1
    return count


def disk_grid(radius_km=10.0, step_km=1.0):
    if radius_km <= 0 or step_km <= 0:
        raise ValueError("positive radius and spacing required")
    axis = np.arange(-radius_km, radius_km + step_km / 2, step_km)
    points = [
        (float(e), float(n)) for n in axis for e in axis if e * e + n * n <= radius_km**2 + 1e-8
    ]
    return axis, points
