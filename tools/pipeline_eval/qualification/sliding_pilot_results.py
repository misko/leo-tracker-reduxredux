"""Chart rolling-bank timings and seal the development and blind receipts."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

import matplotlib
import numpy as np

from ..__main__ import local_output, save_json, write
from ..variants import sliding_pilot
from . import sliding_pilot_trial as trial
from .capture_runtime import checked, decompress, read
from .fine_search_results import spread
from .full_v5_check import _sha
from .prefix_figures import csv_file

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


def paired_gain(rows, mode, key):
    pairs = defaultdict(dict)
    for row in rows:
        pairs[row["case"], row["visit"], row["receiver"], row["repetition"]][row["mode"]] = row[key]
    base = [r["prepared"] for r in pairs.values()]
    variant = [r[mode] for r in pairs.values()]
    change = [a - b for a, b in zip(base, variant, strict=True)]
    return dict(
        prepared=spread(base),
        candidate=spread(variant),
        saved=spread(change),
        median_percent=median(100 * d / a for d, a in zip(change, base, strict=True)),
    )


def draw(out, rows):
    blind = [r for r in rows if r["stage"] == "blind"]
    panels = (
        ("12-anchor development grids", [r for r in rows if r["anchors"] == 12]),
        ("22-anchor development grids", [r for r in rows if r["anchors"] == 22]),
        ("Complete detector · six held visits", blind),
        ("Complete detector · two actual retries", [r for r in blind if r["retries"]]),
    )
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 6.1), layout="constrained")
    labels = dict(
        prepared="Prepared float32 FFT",
        rolling64="Rolling float64",
        rolling32="Rolling float32",
        paired32="Rolling float32 with phase pairs",
        retry_only="Rolling retry only",
    )
    palette = dict(
        prepared="#405a77",
        rolling64="#8f4f29",
        rolling32="#087a70",
        paired32="#7e5498",
        retry_only="#087a70",
    )
    for axis, (title, entries) in zip(axes.flat, panels, strict=True):
        axis.set_title(title, pad=9, fontsize=11)
        if not entries:
            axis.text(0.5, 0.5, "No held visit retried", ha="center", va="center")
            axis.set_axis_off()
            continue
        all_modes = list(dict.fromkeys(r["mode"] for r in entries))
        all_stats = [spread([r["cpu_ms"] for r in entries if r["mode"] == m]) for m in all_modes]
        for i, (mode, stats) in enumerate(zip(all_modes, all_stats, strict=True)):
            midpoint = stats["median"]
            axis.errorbar(
                midpoint,
                i,
                xerr=[[midpoint - stats["min"]], [stats["max"] - midpoint]],
                fmt="o",
                capsize=3,
                color=palette[mode],
            )
        axis.set_xlabel("Process CPU (ms)")
        axis.set_yticks(range(len(all_modes)), [labels[m] for m in all_modes])
        axis.invert_yaxis()
        axis.grid(axis="x", color="#dee4ea")
        axis.set_axisbelow(True)
    fig.suptitle("Rolling Qin tone correlators on existing dual-receiver IQ", fontsize=14)
    fig.savefig(out / "stage.png", dpi=160)
    fig.savefig(out / "stage.pdf", metadata={"CreationDate": None})
    plt.close(fig)


def template_fit():
    models = []
    from leo.analysis.starlink import acquisition

    for edge in ("lower", "upper"):
        for anchors in (acquisition.DEFAULT_ANCHOR_SYMBOLS, sliding_pilot.RETRY):
            model = sliding_pilot.family(edge, anchors)
            ref = sliding_pilot.template_for(edge)[model.starts[:, None] + np.arange(44)]
            w = np.exp(2j * np.pi * np.arange(1, 44)[:, None] * model.tones_hz / sliding_pilot.RATE)
            fitted = w @ np.linalg.lstsq(w, ref[:, 1:].T, rcond=None)[0]
            rem = np.linalg.norm(fitted.T - ref[:, 1:], axis=1) / np.linalg.norm(ref, axis=1)
            models.append(
                dict(
                    edge=edge,
                    anchors=len(anchors),
                    tones_hz=model.tones_hz.tolist(),
                    seam_anchors=np.flatnonzero(model.seam).tolist(),
                    relative_residual=model.relative_error,
                    maximum_tap_residual=model.tap_error,
                    irreducible_relative_residual=float(max(rem)),
                    min_support=int(model.support.min()),
                    max_support=int(model.support.max()),
                )
            )
    return models


def report(work, folder=trial.REPORT):
    receipt = work / "input-lock.json"
    lock = read(receipt)
    for path, digest in lock["sources"].items():
        checked(Path(path), digest)
    write(folder / receipt.name, receipt.read_bytes())
    exports, maps, drift, held, evidence = [], [], [], [], []
    counts = Counter()
    for case, binding in lock["cases"].items():
        path = work / f"{case}.json.gz"
        raw = decompress(path)
        if raw["input_lock_sha256"] != _sha(receipt):
            raise ValueError("result was not tied to the frozen IQ plan")
        write(folder / path.name, path.read_bytes())
        evidence.append(path.name)
        for output, fixture in zip(raw["rows"], binding["rows"], strict=True):
            if any(output[k] != fixture[k] for k in ("visit", "role")):
                raise ValueError("result differs from the frozen visit")
            row_key = dict(case=case, edge=raw["edge"], visit=output["visit"])
            if output["role"] == "development":
                for grid in output["grids"]:
                    about = dict(
                        row_key,
                        stage="development",
                        receiver=grid["receiver"],
                        anchors=grid["anchors"],
                        retries="",
                    )
                    for row in grid["timings"]:
                        exports.append(
                            dict(
                                about,
                                mode=row["mode"],
                                repetition=row["repetition"],
                                cpu_ms=row["cpu_ns"] / 1e6,
                                wall_ms=row["wall_ns"] / 1e6,
                                inverse_ffts=row["kernel"]["inverse_ffts"],
                                matches="",
                            )
                        )
                    drift.append(dict(about, **grid["drift"]))
                    for mode, result in grid["comparisons"].items():
                        maps.append(dict(about, mode=mode, **result))
                continue
            if output["probes"] != fixture["probes"]:
                raise ValueError("detector factors differ from the frozen archive")
            public = [c for part in output["public"]["receivers"] for c in part["candidates"]]
            factors = [c for p in output["probes"] for c in p["candidates"]]
            retries = output["timings"][0]["retries"]
            counts.update(
                dict(
                    visits=1,
                    retries=retries,
                    visits_that_retry=int(retries > 0),
                    receiver_probes=len(output["probes"]),
                    public_candidates=len(public),
                    integer_pass=sum(c["passed_margin_gate"] for c in public),
                    factor_candidates=len(factors),
                    fractional_pass=sum(c["passed_fractional_margin_gate"] for c in factors),
                )
            )
            for row in output["timings"]:
                exports.append(
                    dict(
                        row_key,
                        stage="blind",
                        receiver="both",
                        anchors="",
                        retries=row["retries"],
                        mode=row["mode"],
                        repetition=row["repetition"],
                        cpu_ms=row["cpu_ns"] / 1e6,
                        wall_ms=row["wall_ns"] / 1e6,
                        inverse_ffts=row["inverse_ffts"],
                        matches=row["matches"],
                    )
                )
            held.append(
                dict(
                    row_key,
                    retries=retries,
                    status=output["status"],
                    peak_rss_kib=raw["peak_rss_kib"],
                )
            )

    development, wall = {}, {}
    for count in (12, 22):
        lane_rows = [r for r in exports if r["anchors"] == count]
        development[count] = {m: paired_gain(lane_rows, m, "cpu_ms") for m in trial.MODES[1:]}
        wall[count] = {m: paired_gain(lane_rows, m, "wall_ms") for m in trial.MODES[1:]}
    blind = [r for r in exports if r["stage"] == "blind"]
    retry = [r for r in blind if r["retries"] > 0]
    repaired = [r for r in maps if r["anchors"] == 22 and r["mode"] == "paired32"]
    ordered = all(r["ordered"] and r["max_abs"] < 1e-6 for r in repaired)
    qualifies = (
        ordered
        and development[22]["paired32"]["saved"]["median"] >= 15
        and all(r["matches"] for r in blind)
        and bool(retry)
        and paired_gain(retry, "retry_only", "cpu_ms")["saved"]["median"] > 0
    )
    save_json(
        folder / "summary.json",
        dict(
            retry_followup=qualifies,
            development_cpu=development,
            development_wall=wall,
            blind={
                clock: paired_gain(blind, "retry_only", clock) for clock in ("cpu_ms", "wall_ms")
            },
            blind_with_retry={
                clock: paired_gain(retry, "retry_only", clock) for clock in ("cpu_ms", "wall_ms")
            }
            if retry
            else {},
            counts=dict(counts),
            held=held,
            dense_grids=maps,
            drift=drift,
            pilot_family=template_fit(),
        ),
    )
    csv_file(folder / "stage.csv", exports)
    draw(folder, exports)
    save_json(
        folder / "stage-figure.json",
        dict(
            version=1,
            id="sliding-pilot-bank",
            title="Rolling Qin pilot correlators",
            sample="Three producers, 12 development grids and six blind dual-IQ visits",
            boundary="Prepared folded maps and complete detector timings on resident saved IQ",
            note="Markers show medians and observed ranges. Shared-pair rolling runs on retries.",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="qualification-lock.json",
        ),
    )
    names = (
        "input-lock.json",
        "PROTOCOL.md",
        "summary.json",
        "stage.csv",
        "stage.png",
        "stage.pdf",
        "stage-figure.json",
        *evidence,
    )
    save_json(
        folder / "qualification-lock.json",
        dict(
            files={name: _sha(folder / name) for name in names},
            report_generator_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=local_output)
    report(p.parse_args().work)
