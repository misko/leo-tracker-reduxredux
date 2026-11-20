"""Bound known-site field clock information from the archived measured StarLoc arcs."""

import argparse
import json
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np
from scipy.io import loadmat

from ..__main__ import ROOT, save_json
from ..variants import external_clock_information as model
from . import physical_differences as coincidence
from . import physical_transfer as authority

REPORT = ROOT / "reports/2026_11_19_receiver_screening/detector-origins/field-clock"
CLOCK_FIELDS = ("anchor_utc_ns", "cutoff_utc_ns", "catalog_timestamp_ns", "duration_s")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def observed_arcs(raw):
    entries = loadmat(BytesIO(raw), variable_names=["main_tone_dict", "id_dict"])
    arrays, identification = (entries[key].ravel() for key in ("main_tone_dict", "id_dict"))
    labels = [str(item.item()) for item in identification]
    if len(arrays) != len(labels):
        raise ValueError("released author-supplied label grid does not match the measured arcs")
    arcs = [coincidence.consolidate(row) for row in arrays]
    _, pairs = coincidence.simultaneous(arcs)
    duplicate = {
        min(pair["track_rows"], key=lambda i: (np.ptp(arcs[i][0]), -i))
        for pair in pairs
        if pair["harmonic_like"]
    }
    kept = []
    for i, (time, frequency) in enumerate(arcs):
        if i in duplicate:
            continue
        _, start, count = np.unique(np.floor(time / 2.0), return_index=True, return_counts=True)
        keep = start + (count - 1) // 2
        if len(keep) >= 6:
            kept.append(dict(label=labels[i], time_s=time[keep], frequency_hz=frequency[keep]))
    return kept


def stage(raw, out):
    base = authority.STUDY
    source = base / "field_private/source_provenance.json"
    field = base / "field-receipt.json"
    manifest = json.loads(field.read_bytes())
    truth = json.loads(authority._verified_truth(manifest))["cases"]
    selected = {x["pair"]: x for x in truth if x["condition"] == "present"}
    root = base / "public_field"
    seen, rows = set(), []
    for item in json.loads(source.read_bytes())["captures"]:
        ref = selected[item["pair"]]
        name, group = item["date"], item["site_group"]
        offer = json.loads(
            authority._read(
                root / "queries" / f"{ref['id']}.json", manifest["public_query_sha256"][ref["id"]]
            )
        )
        data, catalogue = offer["observation"], offer["catalog"]
        metadata = json.loads(authority._read(root / "observations" / f"{data}.json", data))
        elements = authority._read(root / "orbits" / f"{catalogue}.tle", catalogue)
        raw_data = authority._read(raw / name / "tracked_tones.mat", item["track_file_sha256"])
        arcs = observed_arcs(raw_data)
        clock = {k: metadata[k] for k in CLOCK_FIELDS}
        binding = dict(
            capture=name,
            site=group,
            cohort="repeat" if group in seen else "primary",
            mat_sha256=item["track_file_sha256"],
            original_observation_sha256=data,
            catalogue_sha256=catalogue,
            reference_id=ref["id"],
            altitude_m=item["altitude_median_m"],
            selected_arcs=len(arcs),
            **clock,
        )
        rows.append((binding, dict(clock, arcs=arcs), elements.decode("ascii"), ref["latlon"]))
        seen.add(group)
    if len(rows) != 11 or len(seen) != 8:
        raise ValueError("the declared field panel requires all eight sites and three repeats")
    files = (
        Path(__file__),
        Path(model.__file__),
        Path(coincidence.__file__),
        Path(authority.__file__),
        source,
        field,
        out / "PROTOCOL.md",
    )
    lock = dict(
        source_sha256={p.name: digest(p) for p in files},
        survey_authority_sha256=manifest["sealed_truth_sha256"],
        plan=[row[0] for row in rows],
        cpus=[2],
    )
    return rows, lock


def other_sites(capture, estimates, roster):
    return [
        estimates[entry["capture"]]
        for entry in roster
        if entry["cohort"] == "primary" and capture["site"] != entry["site"]
    ]


def qualification(raw, out):
    if (out / "results-lock.json").exists():
        raise ValueError("choose a new report location for a fresh source-locked replay")
    staged, lock = stage(raw, out)
    save_json(out / "source-lock.json", lock)
    finish, drafts = [], {}
    start = perf_counter()
    for binding, packet, elements, site in staged:
        before = perf_counter()
        arcs = model.prepare(packet, elements)
        calibration = model.evaluate(arcs, site, binding["altitude_m"])
        finish.append((binding, arcs, site, perf_counter() - before))
        drafts[binding["capture"]] = calibration
    rows = []
    for binding, arcs, site, first_wall in finish:
        before = perf_counter()
        donors = other_sites(binding, drafts, lock["plan"])
        clocks = [
            item["own_effective_shift_s"]
            for item in donors
            if item["own_effective_shift_s"] is not None
        ]
        clock = median(clocks) if clocks else None
        noise = max(model.BIN_SIGMA_HZ, median(item["fixed_utc_held_rms_hz"][0] for item in donors))
        evidence = model.evaluate(arcs, site, binding["altitude_m"], clock, noise)
        case_wall = first_wall + perf_counter() - before
        rows.append(
            dict(
                binding,
                **evidence,
                other_primary_sites=len(donors),
                clock_donors=len(clocks),
                numeric_wall_s=case_wall,
            )
        )
    save_json(
        out / "results.json",
        dict(
            elapsed_s=perf_counter() - start,
            rows=rows,
            site_groups=8,
            calibration_arms={arm: "same_affine_carrier_gauge" for arm in ("c0", "fitted_c")},
            five_km_alternatives=["east", "north", "west", "south"],
        ),
    )
    save_json(
        out / "results-lock.json",
        dict(files={name: digest(out / name) for name in ("source-lock.json", "results.json")}),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    qualification(args.raw, args.out)


if __name__ == "__main__":
    main()
