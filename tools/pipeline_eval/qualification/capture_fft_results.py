"""Score the paired detector archive, then independently publish optional position fits."""

import argparse
import gzip
import json
from statistics import median

from ..__main__ import save_json
from ..scoring import ARMS, distance_km
from . import capture_fft_positions as fits
from . import capture_fft_trial as detector
from .full_receiver_comparison import _frozen_roof
from .input_factor_bridge import _sha, check, read
from .phase_support_results import pack
from .prefix_figures import csv_file

REPORT = detector.REPORT
MODES = ("installed", "fft")


def ms(samples):
    return median(samples) / 1e6


def checked(tape, key, expected):
    if {r["visit"]: r["iq_sha256"] for r in tape["captures"]} != expected:
        raise ValueError("detector rows differ from their bound selection")
    return tape[key]


def raw():
    authority = REPORT / "source-lock.json"
    frozen = read(authority)
    files = {}
    result = {}
    for ident, binding in frozen["cases"].items():
        path = REPORT / f"{ident}.json.gz"
        files[path.name] = _sha(path)
        tape = json.loads(gzip.decompress(path.read_bytes()))
        if tape["candidate_source_sha256"] != frozen["source_files"][frozen["library"]]:
            raise ValueError("candidate detector source differs from its seal")
        visits = {v["visit"]: v["iq_sha256"] for v in binding["roster"].values()}
        cases = checked(tape, "captures", visits)
        controls = checked(tape, "controls", visits)
        groups = dict(
            authentic=[pair for row in cases for pair in row["rows"]],
            warm=[row["rows"][-1] for row in cases],
            controls=[pair for row in controls.values() for pair in row["rows"]],
        )
        means = {}
        for label, rows in groups.items():
            counts = sum(len(p["installed"]["public"]["receivers"]) for p in rows)
            matched = sum(
                pair["installed"][field] == pair["fft"][field]
                for pair in rows
                for field in ("public", "probes", "attempts")
            )
            if matched != 3 * len(rows):
                raise ValueError("paired detector scientific record differs")
            stages = {
                mode: {
                    "cpu_ms": ms(pair[mode]["cpu_ns"] for pair in rows),
                    "wall_ms": ms(pair[mode]["wall_ns"] for pair in rows),
                    "stages_cpu_ms": {
                        key: ms(pair[mode]["stages_cpu_ns"][key] for pair in rows)
                        for key in detector.FIELDS
                    },
                }
                for mode in MODES
            }
            calls = [grid for pair in rows for grid in pair["fft"]["grid_receipts"]]
            means[label] = dict(
                pairs=len(rows),
                receiver_rows=counts,
                exact_record_comparisons=matched,
                times_ms=stages,
                fft_calls=len(calls),
                fft_fallbacks=sum(not c["applied"] for c in calls),
                anchors=sorted({c["anchors"] for c in calls}),
                native_grid_cpu_ms=ms(c["native_cpu_ns"] for c in calls),
                python_config_cpu_ms=ms(c["config_cpu_ns"] for c in calls),
                explicit_fft_buffer_peak_bytes=max(c["buffer_bytes"] for c in calls),
                explicit_grid_and_support_peak_bytes=max(
                    c["grid_bytes"] + c["support_bytes"] for c in calls
                ),
            )
        # The frozen sampler took the kernel's VmHWM and VmRSS lines in file order.
        result[ident] = dict(
            edge=binding["edge"],
            library_setup_cpu_ms=tape["setup_cpu_ns"] / 1e6,
            process_peak_rss_kib=tape["process_memory"]["rss_kib"],
            ending_rss_kib=tape["process_memory"]["hwm_kib"],
            observations=means,
        )
    save_json(REPORT / "summary.json", result)
    files["summary.json"] = _sha(REPORT / "summary.json")
    save_json(REPORT / "detector-lock.json", dict(source_lock_sha256=_sha(authority), files=files))


def position():
    analysis = read(REPORT / "fit-result-lock.json")
    for name, want in analysis.items():
        check(REPORT / name, want)
    plan = read(REPORT / "fit-lock.json")
    rows = read(REPORT / "fit-results.json")
    matches = {(r["id"], r["method"]): r for r in rows}
    if matches.keys() != {(i, m) for i in fits.PINS for m in (fits.MIX, fits.CONTROL)}:
        raise ValueError("a planned position attempt is missing")
    refs, _ = _frozen_roof()
    scores = []
    parity = {}
    for ident in fits.PINS:
        variant = matches[ident, fits.MIX]
        original = matches[ident, fits.CONTROL]
        expected = plan["jobs"][ident]["binding"]
        shared = ("catalog_sha256", "track_config_sha256", "original_native_sha256", "tile")
        if any(row[key] != expected[key] for row in (variant, original) for key in shared):
            raise ValueError("fit inputs do not match their substitution lock")
        parity[ident] = {
            arm: variant["result"]["arms"][arm] == original["result"]["arms"][arm] for arm in ARMS
        }
        for row in (variant, original):
            result = row["result"]
            for arm in ARMS:
                selected = result["arms"][arm]
                point = selected["latlon"]
                detail = row["runtime"]["finish"]
                scores.append(
                    dict(
                        id=ident,
                        method=row["method"],
                        arm=arm,
                        status=result["status"],
                        error_km=distance_km(point, refs[ident]["truth"]),
                        conditional_rms_hz=selected.get("rf_rms_hz"),
                        wall_s=row["wall_s"],
                        cpu_s=detail[0]["cgroup_cpu_s"] if detail else None,
                        replaced_visits=len(plan["jobs"][ident]["audit"]["substituted_visits"]),
                        unchanged_visits=plan["jobs"][ident]["audit"]["untouched_visits"],
                    )
                )
    save_json(REPORT / "fit-parity.json", parity)
    csv_file(REPORT / "scores.csv", scores)
    pack(REPORT / "positions.jsonl.gz", rows)
    files = ("fit-result-lock.json", "fit-parity.json", "scores.csv", "positions.jsonl.gz")
    save_json(
        REPORT / "roof-lock.json",
        dict(
            cases=list(fits.PINS),
            files={key: _sha(REPORT / key) for key in files},
        ),
    )
    save_json(
        REPORT / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="capture-fft-partial-iq",
                    method=fits.MIX,
                    scope="roof",
                    cases="sealed",
                    title=(
                        "FFT coarse acquisition with four saved-IQ visits substituted per recording"
                    ),
                    caption=(
                        "Actual capped phase-release positions. All unselected capture-era "
                        "factor rows remain unchanged. A complete stored-IQ replay was "
                        "outside this experiment."
                    ),
                    seal="roof-lock.json",
                    provenance=list(files[:-1]),
                    series=[
                        dict(
                            key="one",
                            label="FFT partial IQ",
                            file="positions.jsonl.gz",
                            value=fits.MIX,
                            native_field="original_native_sha256",
                        ),
                        dict(
                            key="stock",
                            label="Original capture-era factors",
                            file="positions.jsonl.gz",
                            value=fits.CONTROL,
                            match=["original_native_sha256", "catalog_sha256", "tile"],
                        ),
                    ],
                )
            ],
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("kind", choices=("raw", "position"))
    args = cli.parse_args()
    (raw if args.kind == "raw" else position)()
