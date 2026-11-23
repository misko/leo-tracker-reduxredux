"""Record the completed observations and censor any unfinished stock timing."""

import argparse
from hashlib import sha256
from pathlib import Path
from statistics import median

from short_raw_diagnostic import (
    CASES, ORIGINALS, REFERENCE, REFERENCE_SHA256, artifacts, assignment, calibration, checked, pairs, read, write,
)
from leo.contracts.digests import canonical_digest


def archived_stock(case, case_spec, stock, root):
    _, archived = assignment(*case_spec[:4])
    receipt = archived["receipt"]
    saved = ORIGINALS / case / "candidate"
    evidence = pairs.evidence(saved, receipt, 0, read_only=True)
    if any(evidence[key] != archived[key] for key in ("raw_authority", "arms", "owners", "scientific_digests", "artifacts")):
        raise ValueError("Archived named-v3 publication no longer reproduces its original receipt")
    images = artifacts(saved, receipt)
    if len(images["images"]) != 8:
        raise ValueError("The archived complete stock witness must contain all eight images")
    work = root / "stock/fast-scan-automatic-work"
    terminal_path = work / receipt["run_id"] / "terminal.json"
    native_path, = work.glob("*/detections.json")
    terminal, native = read(terminal_path), read(native_path)
    if (canonical_digest(terminal) != receipt["terminal_sha256"]
            or canonical_digest(native) != terminal["native_sha256"]
            or native["source"]["raw_recording_authority_digest"] != archived["raw_authority"]):
        raise ValueError("The fresh partial stock handoff differs from its verified archived publication")
    started = stock["started_unix_ns"]
    current = dict(terminal_sha256=receipt["terminal_sha256"], native_sha256=terminal["native_sha256"],
                   arms=terminal["arms"], detection_file_s=(native_path.stat().st_mtime_ns - started) / 1e9,
                   terminal_file_s=(terminal_path.stat().st_mtime_ns - started) / 1e9)
    witness = dict(root=str(saved), publication_status=receipt["decision"], arms=archived["arms"],
                   owners=archived["owners"], scientific_digests=archived["scientific_digests"], pngs=images["images"])
    return current, witness


def censor_elapsed(cumulative, rows, cutoff):
    """Keep all assignments and separate a censoring bound from a complete ratio."""
    lower_ratios, upper_ratios, candidates, stock_floor = [], [], [], []
    for row in rows:
        stock, candidate = (row["runs"][arm] for arm in ("stock", "candidate"))
        candidates.append(candidate["elapsed_s"])
        censored = stock["exit_code"] == 124
        stock_floor.append(cutoff if censored else stock["elapsed_s"])
        upper_ratios.append(candidates[-1] / stock_floor[-1])
        lower_ratios.append(0 if censored else upper_ratios[-1])
    median_floor = median(lower_ratios)
    return cumulative | dict(installed_elapsed_s=None, paired_median_elapsed_ratio=None, summed_elapsed_ratio=None,
                             installed_elapsed_lower_bound_s=sum(stock_floor),
                             censored_paired_median_ratio_lower_bound=median_floor,
                             censored_paired_median_ratio_upper_bound=median(upper_ratios),
                             censored_summed_ratio_upper_bound=sum(candidates) / sum(stock_floor),
                             half_time_gate_ruled_out_by_median=median_floor > 0.5,
                             completed_elapsed_gate=None)


def score(root, output):
    source = root / "results.json"
    data = read(source)
    data["raw_receipt"] = dict(path=str(source), sha256=sha256(source.read_bytes()).hexdigest())
    reference = read(checked(REFERENCE, REFERENCE_SHA256))["cases"]
    cases = data["cases"]
    for row, case_spec in zip(cases, CASES, strict=True):
        stock = row["runs"]["stock"]
        if stock["exit_code"] != 124:
            continue
        cutoff = 150
        stock["elapsed_censored_at_s"] = cutoff
        stock["elapsed_including_timeout_reap_s"] = stock["elapsed_s"]
        stock["elapsed_s"] = None
        handoff, archived = archived_stock(row["case"], case_spec, stock, root / row["case"])
        stock["retained_handoff"] = handoff
        row["archived_stock_publication"] = archived
        row["scientific_status"] = "candidate complete and fresh stock terminal matched archived complete stock"
        ref, = (item for item in reference if item["dataset_label"] == row["case"])
        truth = ([ref["reference"][key] for key in ("latitude_deg", "longitude_deg")]
                 if ref["authority_eligible"] and ref["sealed_metadata_digests_verified"] else None)
        row["calibration_through_terminal"] = calibration(row["runs"] | {"stock": handoff}, truth)
        for index, result in enumerate(data["cumulative"]):
            if row["case"] in result["cases"]:
                data["cumulative"][index] = censor_elapsed(result, cases[:index + 1], cutoff)
    for result in data["cumulative"]:
        if "completed_elapsed_gate" not in result:
            result["completed_elapsed_gate"] = (result["paired_median_elapsed_ratio"] <= 0.5
                                                and result["summed_elapsed_ratio"] <= 0.5)
    write(output, data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    score(**vars(parser.parse_args()))
