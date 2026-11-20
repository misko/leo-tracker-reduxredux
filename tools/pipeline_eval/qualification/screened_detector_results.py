"""Validate complete detector rows and report measured, paired leaf costs."""

import argparse
import gzip
import json
from pathlib import Path
from statistics import median

from ..__main__ import encoded, save_json
from .capture_fft_positions import substitute
from .full_v5_check import BULK, _load_case, _sha

SCIENCE = ("status", "public", "probes", "attempts", "screened_calls")


def archive(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def compare(left, right):
    return all(encoded(left[field]) == encoded(right[field]) for field in SCIENCE)


def candidates(result):
    return sum(len(probe["candidates"]) for probe in result["probes"])


def clocks(row):
    return dict(
        cpu=row["cpu_ns"],
        wall=row["wall_ns"],
        setup_cpu=row["setup_cpu_ns"],
        setup_wall=row["setup_wall_ns"],
        **row["stages_cpu_ns"],
        **{
            ("screen_integer_grid" if k == "screen_fp32_grid" else k): v
            for k, v in row["refinement_cpu_ns"].items()
        },
    )


def medians(rows):
    clocks_by_row = [clocks(row) for row in rows]
    return {
        k: round(median(row.get(k, 0) for row in clocks_by_row) / 1e6, 4)
        for k in sorted(set().union(*clocks_by_row))
    }


def summarize_group(group, method):
    pairs = [item for window in group for item in window["pairs"]]
    control = [item["installed"] for item in pairs]
    variant = [item[method] for item in pairs]
    cell_receipts = [packet for window in group for packet in window.get("cells", [])]
    same = [compare(a, b) for a, b in zip(control, variant, strict=True)]
    count = len(same)
    if sum(same) != count or any(r["different_cells"] or r["fallback"] for r in cell_receipts):
        raise ValueError("a public detector field, screen decision or audited score differs")
    work = [r["work"] for r in variant if r["work"] is not None]
    grid = [r["grid_work"] for r in variant if "grid_work" in r]
    return dict(
        windows=len(group),
        detector_pairs=count,
        exact_pairs=sum(same),
        audited_screen_calls=len(cell_receipts),
        audited_screen_cells=sum(packet["cells"] for packet in cell_receipts),
        differing_screen_cells=sum(packet["different_cells"] for packet in cell_receipts),
        candidates_per_window=[candidates(window["pairs"][0]["installed"]) for window in group],
        status_per_window=[window["pairs"][0]["installed"]["status"] for window in group],
        median_ms={"installed": medians(control), method: medians(variant)},
        paired_median_cpu_improvement_percent=round(
            100
            * median(
                1.0 - b["cpu_ns"] / a["cpu_ns"] for a, b in zip(control, variant, strict=True)
            ),
            3,
        ),
        paired_median_wall_improvement_percent=round(
            100
            * median(
                1.0 - b["wall_ns"] / a["wall_ns"] for a, b in zip(control, variant, strict=True)
            ),
            3,
        ),
        candidate_lanczos_work={
            k: sum(r[k] for r in work)
            for k in ("calls", "samples", "uniform_calls", "weight_rows", "fallback_calls")
        }
        if work
        else None,
        candidate_grid_work={k: sum(r[k] for r in grid) for k in ("calls", "cells", "fallbacks")}
        if grid
        else None,
    )


def summarize(warm, cold, method):
    control, variant = cold
    if control["capture"] != variant["capture"] or not compare(control["row"], variant["row"]):
        raise ValueError("first-use detector output differs")
    return dict(
        authentic=summarize_group(warm["captures"], method),
        controls=summarize_group(list(warm["controls"].values()), method),
        control_names=list(warm["controls"]),
        authentic_visits=[r["visit"] for r in warm["captures"]],
        cold_first_visit={
            "visit": control["capture"]["visit"],
            "installed_ms": medians([control["row"]]),
            method + "_ms": medians([variant["row"]]),
            "extra_setup_ms": {k: v / 1e6 for k, v in variant.get("setup", {}).items()},
        },
    )


def summarize_archives(path):
    return dict(
        lanczos_reuse={
            ident: summarize(
                archive(path / f"{ident}.json.gz"),
                tuple(
                    archive(path / f"{ident}-cold-{label}.json.gz")
                    for label in ("installed", "reuse")
                ),
                "reuse",
            )
            for ident in ("DS26-0036", "DS29-0174")
        },
        vnni_pair={
            "DS29-0174": summarize(
                archive(path / "grid-run.json.gz"),
                tuple(
                    archive(path / f"grid-{label}.json.gz") for label in ("installed", "vnni_pair")
                ),
                "vnni_pair",
            )
        },
    )


def factor_parity(root):
    results = {}
    for ident, traces in (
        ("DS26-0036", (("reuse", "DS26-0036.json.gz"),)),
        ("DS29-0174", (("reuse", "DS29-0174.json.gz"), ("vnni_pair", "grid-run.json.gz"))),
    ):
        native = _load_case(ident)["native"]
        source = BULK / native["path"]
        digest = _sha(source)
        if digest != native["sha256"]:
            raise ValueError("capture-era native factor authority changed")
        stock = json.loads(source.read_bytes())
        for method, name in traces:
            warm = archive(root / name)
            indexed = {
                window["visit"]: (pair["installed"]["probes"], pair[method]["probes"])
                for window in warm["captures"]
                if (pair := window["pairs"][0])["installed"]["status"] == "processed"
            }
            result, receipt = substitute(stock, indexed)
            if encoded(result) != encoded(stock["source"]["probes"]):
                raise ValueError("partial recomputation actually changed the native factors")
            results[f"{method}:{ident}"] = dict(
                receipt,
                native_sha256=digest,
                worker_trace_sha256=_sha(root / name),
                position_boundary="ordered native factors identical; no new position solve",
            )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    save_json(args.report / "summary.json", summarize_archives(args.report))
    save_json(args.report / "factor-parity.json", factor_parity(args.report))
