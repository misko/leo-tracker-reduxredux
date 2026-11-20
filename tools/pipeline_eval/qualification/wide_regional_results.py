"""Summarize and seal bounded wide-regional RF, timing and ABI receipts."""

import argparse
import gzip
import json
import subprocess
from collections import Counter
from pathlib import Path
from statistics import median

from ..__main__ import local_output, save_json, write
from . import wide_regional_build, wide_regional_eval
from .full_v5_check import PRODUCERS, _sha

REPORT = wide_regional_eval.REPORT
MODES = wide_regional_eval.MODES


def maximum_matches(original, variant):
    used = {0}
    for left in original:
        eligible = [
            i
            for i, right in enumerate(variant)
            if abs(left[1] - right[1]) <= 2 and abs(left[2] - right[2]) < 1000
        ]
        used = used | {mask | (1 << i) for mask in used for i in eligible if not mask & (1 << i)}
    return max(mask.bit_count() for mask in used)


def summarize(arch):
    receipts = [
        json.loads(gzip.decompress((REPORT / f"{c}-{arch}.json.gz").read_bytes()))
        for c in PRODUCERS
    ]
    rows = [r for receipt in receipts for r in receipt["rows"]]
    valid = [r for r in rows if r["status"] == "processed"]
    compares = Counter()
    for row in valid:
        for a, b in zip(*(row["payloads"][m]["rows"] for m in MODES), strict=True):
            original = [(c["coarse_epoch"], c["coarse_cfo_hz"]) for c in a["candidates"]]
            wide = [(c["coarse_epoch"], c["coarse_cfo_hz"]) for c in b["candidates"]]
            compares["same_rank_coarse_identity"] += sum(
                x == y for x, y in zip(original, wide, strict=False)
            )
            compares["shared_coarse_identity"] += sum((Counter(original) & Counter(wide)).values())
            compares["wide_outer_coarse_records"] += sum(abs(f) > 400_000 for _, f in wide)
        compares["physical_positive_matches"] += sum(
            maximum_matches(a, b)
            for a, b in zip(
                *(row["positives"][m] for m in MODES),
                strict=True,
            )
        )
    by_mode = {}
    for mode in MODES:
        timings = [
            t
            for r in receipts
            for i, row in enumerate(x for x in r["rows"] if x["status"] == "processed")
            for t in row["timings"][mode][int(i == 0 and arch == "host") :]
        ]
        cpu = [t["detector_cpu_ms"] for t in timings]
        wall = [t["wall_s"] * 1000 for t in timings]
        stages = Counter()
        for t in timings:
            for r in t["rows"]:
                stages.update(r)
        positives = [p for r in valid for rx in r["positives"][mode] for p in rx]
        by_mode[mode] = dict(
            detector_cpu_ms=sum(cpu),
            median_cpu_ms=median(cpu),
            max_cpu_ms=max(cpu),
            median_wall_ms=median(wall),
            max_wall_ms=max(wall),
            calls=len(cpu),
            cpu_at_most_20ms=sum(t <= 20 for t in cpu),
            wall_at_most_20ms=sum(t <= 20 for t in wall),
            emulator_peak_kib=max((t.get("emu_peak_kib", 0) for t in timings), default=0),
            stages_ms=dict(stages),
            positive_records=len(positives),
            positive_above_absolute_400khz=sum(abs(p[2]) > 400_000 for p in positives),
            candidate_records=sum(
                r["candidate_count"] for row in valid for r in row["payloads"][mode]["rows"]
            ),
        )
    return dict(
        architecture=arch,
        scope={r["case"]: dict(Counter(x["status"] for x in r["rows"])) for r in receipts},
        exact_ordinary_vs_wide=sum(r["exact"] for r in valid),
        repeated_candidate_payloads_stable=all(r["stable"] for r in valid),
        comparisons=dict(compares),
        timing=by_mode,
    )


def export_symbols(path):
    out = subprocess.run(
        ["nm", "-D", "--defined-only", str(path)], capture_output=True, text=True, check=True
    )
    return [line.split()[-1] for line in out.stdout.splitlines()]


def publish(work):
    sources = json.loads((REPORT / "source-lock.json").read_bytes())
    if sources != wide_regional_eval.sources():
        raise ValueError("Held trial source lock differs")
    names = []
    build_index = {}
    for arch in ("host", "arm"):
        symbols = {}
        for mode in MODES:
            root = work / (mode if arch == "host" else f"arm-{mode}")
            library = root / wide_regional_build.LIBRARY
            brief = json.loads((root / "width-receipt.json").read_bytes())
            origin = root / "build-receipt.json"
            receipt = json.loads(origin.read_bytes())
            if not _sha(library) == brief["sha256"] == receipt["outputs"][library.name]:
                raise ValueError("Build receipt and actual library do not match")
            symbols[mode] = export_symbols(library)
            key = f"{arch}-{mode}"
            name = f"{key}-build.json"
            names.append(name)
            write(REPORT / name, origin.read_bytes())
            build_index[key] = dict(
                brief, build_receipt_file=name, release_export_names=symbols[mode]
            )
        if symbols["control"] != symbols["wide"]:
            raise ValueError("Wide release changed the native exported ABI names")
    save_json(REPORT / "build-digests.json", build_index)
    by_arch = {arch: summarize(arch) for arch in ("host", "arm")}
    save_json(REPORT / "qualification.json", by_arch)
    names.extend(
        [
            "PROTOCOL.md",
            "source-lock.json",
            "qualification.json",
            "build-digests.json",
            "canary-host.json",
            "canary-arm.json",
            "sanitizers.json",
            *(f"{c}-{a}.json.gz" for c in PRODUCERS for a in ("host", "arm")),
        ]
    )
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(PRODUCERS),
            files={name: _sha(REPORT / name) for name in names},
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, default=wide_regional_build.ROOT)
    publish(local_output(cli.parse_args().work))
