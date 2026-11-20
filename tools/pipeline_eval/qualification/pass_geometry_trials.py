"""Run and independently score closest-approach candidates on two development captures."""

import argparse
import gzip
import hashlib
import io
import json
import math
import os
import secrets
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, local_output, references, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import pass_geometry, rate_triplets
from .cold_input import load, matched_offers
from .prefix_figures import csv_file
from .rate_triplet_trials import WORKER as ORIGINAL_WORKER
from .rate_triplet_trials import sandbox_command

ROSTER = ("DS26-0036", "DS29-0082")
MODES = ("global", "matched-tile")
OUTPUT = ROOT / "reports/2026_11_19_position_atlas/pass-geometry"
WORKER = Path(__file__).with_name("pass_geometry_worker.py")
SYNTHETIC_TITLE = "Closest-approach receiver on a fresh synthetic scene"
SYNTHETIC_SUBTITLE = "Causal-TLE signal scene (n=1) in two search modes and shuffled control (n=1)"
SYNTHETIC_VIEWS = (
    ("generated-signal", "global", "Global"),
    ("generated-signal", "matched-tile", "Supplied tile"),
    ("generated-null", "global", "Shuffled null"),
)


def bound_source():
    paths = [Path(pass_geometry.__file__), Path(rate_triplets.__file__), WORKER]
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def namespace(cpu):
    command = sandbox_command(cpu)
    command[command.index(str(ORIGINAL_WORKER))] = str(WORKER)
    dest = "/worker/tools/pipeline_eval/variants"
    for module in (rate_triplets, pass_geometry):
        source = Path(module.__file__)
        command[-3:-3] = ["--ro-bind", str(source), f"{dest}/{source.name}"]
    return command


def worker(case, mode, capture, tile, cpu, scratch, version):
    packet = dict(capture=dict(capture, catalog=capture["catalog"].decode("ascii")))
    if tile is not None:
        packet["tile"] = tile
    raw = encoded(packet)
    start = perf_counter()
    try:
        output = subprocess.run(
            namespace(cpu),
            cwd=scratch,
            input=raw,
            capture_output=True,
            timeout=120,
            check=True,
        )
        result = json.loads(output.stdout)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        result = dict(
            status="timed_out" if isinstance(exc, subprocess.TimeoutExpired) else "failed",
            reason=(exc.stderr or b"").decode(errors="replace")[-1600:] or str(exc),
            boundary=pass_geometry.BOUNDARY,
            metrics={},
            arms={a: {"latlon": None, "forced_latlon": None} for a in ARMS},
        )
    validate_result(result)
    row = dict(
        id=case,
        mode=mode,
        method=pass_geometry.METHOD,
        worker_wall_s=perf_counter() - start,
        cpu=cpu,
        result=result,
        implementation_sha256=version["pass_geometry.py"],
        input_sha256=hashlib.sha256(raw).hexdigest(),
        native_sha256=capture["native_sha256"],
        catalog_sha256=capture["catalog_sha256"],
    )
    print(case, mode, result["status"], round(row["worker_wall_s"], 2), flush=True)
    save_json(scratch / f"{case}-{mode}.json", row)
    return row


def sealed(path, rows):
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))


def replay(scratch, report, cpus):
    if len(cpus) != 4 or len(set(cpus)) != 4 or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("choose four distinct available worker CPUs")
    version = bound_source()
    save_json(scratch / "roof-source-lock.json", version)
    roster = []
    for case in ROSTER:
        capture = vars(load(case))
        (tile,) = matched_offers(case)
        for mode in MODES:
            offer = (
                dict(tile, width_km=tile.get("width_km", 25.0)) if mode == "matched-tile" else None
            )
            roster.append((case, mode, capture, offer))
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [
            pool.submit(worker, *row, cpu, scratch, version)
            for row, cpu in zip(roster, cpus, strict=True)
        ]
        rows = [job.result() for job in jobs]
    if bound_source() != version:
        raise ValueError("the algorithm changed while the archive jobs ran")
    for mode in MODES:
        sealed(report / f"{mode}.jsonl.gz", [r for r in rows if r["mode"] == mode])
    save_json(report / "roof-source-lock.json", version)


def prospective(scratch, report, cpus, seed_hex):
    import numpy as np

    from . import cold_scenes as scene

    version = bound_source()
    version["scene_generator_sha256"] = hashlib.sha256(
        Path(scene.__file__).read_bytes()
    ).hexdigest()
    save_json(scratch / "synthetic-source-lock.json", version)
    seed = secrets.token_bytes(32) if seed_hex is None else bytes.fromhex(seed_hex)
    if len(seed) != 32:
        raise ValueError("the prospective seed must contain 32 bytes")
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    archive = json.loads(scene.SNAPSHOT.read_bytes())
    received = scene._stamp(datetime.fromisoformat(archive["retrieved_at"]))
    catalog = (scene.TLE_ARCHIVE / archive["raw_object"]).read_bytes()
    digest = hashlib.sha256(catalog).hexdigest()
    if digest != scene.CATALOG_SHA256:
        raise ValueError("the independent causal simulation catalogue differs from its inventory")
    site = tuple(map(float, np.array([-36, 146]) + rng.uniform(-3, 3, 2)))
    anchor = received + 1680 * scene.NS
    satellites = scene._constellation(catalog, received)
    probes, counter, truth = scene._generate_capture(satellites, anchor, site, rng)
    shared = dict(
        sample_rate_hz=scene.RATE,
        probe_ms=scene.PROBE_MS,
        first_counter=counter,
        anchor_utc_ns=anchor,
        cutoff_utc_ns=anchor,
        catalog_timestamp_ns=received,
        duration_s=scene.SECONDS,
        catalog=catalog,
        catalog_sha256=digest,
    )
    signal = dict(shared, probes=probes, native_sha256=hashlib.sha256(encoded(probes)).hexdigest())
    shuffled = scene._shuffled(probes, rng)
    null = dict(
        shared, probes=shuffled, native_sha256=hashlib.sha256(encoded(shuffled)).hexdigest()
    )
    offer = dict(center=(np.asarray(site) + rng.uniform(-0.075, 0.075, 2)).tolist(), width_km=25.0)
    jobs = [
        ("generated-signal", "global", signal, None),
        ("generated-signal", "matched-tile", signal, offer),
        ("generated-null", "global", null, None),
    ]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(worker, *job, cpu, scratch, version)
            for job, cpu in zip(jobs, cpus[:3], strict=True)
        ]
        rows = [f.result() for f in futures]
    sealed(report / "synthetic-predictions.jsonl.gz", rows)
    save_json(
        report / "synthetic-scores.json",
        dict(
            source_lock=version,
            seed_hex=seed.hex(),
            generated_site=site,
            generated_c_hz_per_ghz=truth["rf_constant_hz_per_ghz"],
            scores=[
                dict(
                    id=row["id"],
                    mode=row["mode"],
                    status=row["result"]["status"],
                    arms={
                        arm: dict(
                            forced_km=distance_km(rec["forced_latlon"], site)
                            if row["id"] == "generated-signal"
                            else None,
                            returned_km=distance_km(rec["latlon"], site)
                            if row["id"] == "generated-signal"
                            else None,
                            conditional_rms_hz=rec.get("conditional_rms_hz"),
                        )
                        for arm, rec in row["result"]["arms"].items()
                    },
                )
                for row in rows
            ],
        ),
    )


def score(report):
    refs = {
        row["id"]: row
        for panel, case in zip(("ds26-common127", "roof16"), ROSTER, strict=True)
        for row in references(panel, [case])[1]
    }
    all_rows = []
    summary = {}
    for mode in MODES:
        with gzip.open(report / f"{mode}.jsonl.gz", "rt") as f:
            rows = list(map(json.loads, f))
        if tuple(r["id"] for r in rows) != ROSTER or any(r["mode"] != mode for r in rows):
            raise ValueError("incorrect roster or mode")
        scores = []
        for r in rows:
            case = r["id"]
            result = r["result"]
            truth = refs[case]["truth"]
            scores.extend(
                dict(
                    id=case,
                    mode=mode,
                    arm=arm,
                    status=result["status"],
                    returned_km=distance_km(result["arms"][arm]["latlon"], truth),
                    forced_km=distance_km(result["arms"][arm]["forced_latlon"], truth),
                    conditional_rms_hz=result["arms"][arm].get("conditional_rms_hz"),
                    original_v5_km=refs[case]["reference"]["baseline"][arm]["error_km"]
                    if mode == "matched-tile"
                    else None,
                    worker_wall_s=r["worker_wall_s"],
                )
                for arm in ARMS
            )
        all_rows.extend(scores)
        summary[mode] = dict(
            arms={
                arm: {
                    key: distribution(r[key] for r in scores if r["arm"] == arm)
                    for key in ("returned_km", "forced_km", "conditional_rms_hz", "original_v5_km")
                }
                for arm in ARMS
            },
            paired_fitted_minus_zero={
                key: distribution(
                    scores[i + 1][key] - scores[i][key]
                    for i in range(0, len(scores), 2)
                    if scores[i][key] is not None and scores[i + 1][key] is not None
                )
                for key in ("forced_km", "conditional_rms_hz")
            },
            worker_wall_s=distribution(r["worker_wall_s"] for r in rows),
        )
    csv_file(
        report / "position-errors.csv",
        [{k: v for k, v in r.items() if k != "conditional_rms_hz"} for r in all_rows],
    )
    csv_file(
        report / "conditional-frequency-rms.csv",
        [
            {k: r[k] for k in ("id", "mode", "arm", "status", "conditional_rms_hz")}
            for r in all_rows
        ],
    )
    save_json(report / "summary.json", summary)


def read_synthetic_scores(score_path):
    """Bind both search views of one geographic case and the one shuffled case."""
    raw = Path(score_path).read_bytes()
    scores = json.loads(raw)["scores"]
    keys = {(case, mode) for case, mode, _ in SYNTHETIC_VIEWS}
    rows = {(item["id"], item["mode"]): item for item in scores}
    if len(scores) != len(keys) or rows.keys() != keys:
        raise ValueError("synthetic pass-geometry scores need one signal and one shuffled case")
    for (case, _), row in rows.items():
        if row["status"] not in {"ok", "withheld"} or set(row["arms"]) != set(ARMS):
            raise ValueError("invalid synthetic pass-geometry status or calibration arms")
        for values in row["arms"].values():
            returned = values["returned_km"]
            forced = values["forced_km"]
            rms = values["conditional_rms_hz"]
            if case == "generated-null":
                if row["status"] != "withheld" or (returned, forced, rms) != (None, None, None):
                    raise ValueError(
                        "the shuffled case has no geographic reference or frequency fit"
                    )
                continue
            if (
                forced is None
                or not math.isfinite(forced)
                or forced <= 0
                or rms is None
                or not math.isfinite(rms)
                or rms < 0
                or returned != (forced if row["status"] == "ok" else None)
            ):
                raise ValueError("inconsistent position or frequency scores for the signal case")
    return raw, rows


def synthetic_position_label(km):
    return f"{km:,.0f}" if km >= 10 else f"{km:.3f}"


def write_synthetic_figure(score_path, out_path, *, pdf_path=None):
    """Plot returned and forced solutions from the single fresh causal scene and its null."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D

    source, rows = read_synthetic_scores(score_path)
    order = SYNTHETIC_VIEWS
    labels = (("c0", "#23579a", 0.15), ("fitted_c", "#ad501e", -0.15))
    ink = "#253248"
    figure = Figure(figsize=(10.4, 4.2), facecolor="white", dpi=150)
    canvas = FigureCanvasAgg(figure)
    position, frequency = figure.subplots(1, 2, sharey=True)
    figure.subplots_adjust(left=0.15, right=0.96, top=0.71, bottom=0.25, wspace=0.23)
    figure.text(
        0.055,
        0.92,
        SYNTHETIC_TITLE,
        color=ink,
        weight="bold",
        fontsize=16,
    )
    figure.text(
        0.055,
        0.846,
        SYNTHETIC_SUBTITLE,
        color="#495569",
        fontsize=10,
    )
    for ax in (position, frequency):
        ax.set_ylim(-0.48, 2.48)
        ax.set_yticks((2, 1, 0), [item[2] for item in order], color=ink)
        ax.tick_params(axis="both", length=0, pad=6, labelsize=9, colors=ink)
        ax.grid(axis="x", color="#e0e5ef", linewidth=0.8)
        ax.set_axisbelow(True)
        ax.axhline(0.5, color="#e5eaf1", linewidth=0.8)
        ax.axhline(1.5, color="#e5eaf1", linewidth=0.8)
        for side in ("left", "top", "right"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#aab3c2")
    position.set_xscale("log")
    position.set_xlim(0.084, 65_000)
    position.set_xlabel("Position error (km, log scale)", color=ink, labelpad=10)
    frequency.set_xlim(0, 210)
    frequency.set_xlabel("Conditional Doppler RMS (Hz)", color=ink, labelpad=10)
    null = rows["generated-null", "global"]
    null_status = "Returned" if null["status"] == "ok" else null["status"].replace("_", " ").title()
    position.text(
        0.03,
        0,
        f"{null_status} · no geographic distance",
        transform=position.get_yaxis_transform(),
        color="#59657a",
        va="center",
        fontsize=9,
    )
    if all(arm["conditional_rms_hz"] is None for arm in null["arms"].values()):
        frequency.text(
            0.03,
            0,
            "No frequency fit",
            transform=frequency.get_yaxis_transform(),
            color="#59657a",
            va="center",
            fontsize=9,
        )
    for y, (case, mode, _) in zip((2, 1), order[:2], strict=True):
        item = rows[case, mode]
        for arm, color, offset in labels:
            values = item["arms"][arm]
            returned = values["returned_km"] is not None
            marker = "o" if returned else "x"
            km, hz = values["forced_km"], values["conditional_rms_hz"]
            position.scatter(km, y + offset, color=color, marker=marker, s=45, linewidths=1.6)
            frequency.scatter(hz, y + offset, color=color, marker=marker, s=45, linewidths=1.6)
            position.annotate(
                synthetic_position_label(km),
                (km, y + offset),
                xytext=(7, 0),
                textcoords="offset points",
                color=color,
                va="center",
                fontsize=9,
            )
            frequency.annotate(
                f"{hz:.1f}",
                (hz, y + offset),
                xytext=(7, 0),
                textcoords="offset points",
                color=color,
                va="center",
                fontsize=9,
            )
    key = [
        Line2D([], [], lw=2, color=labels[0][1], label="Zero calibration"),
        Line2D([], [], lw=2, color=labels[1][1], label="Fitted calibration"),
        Line2D([], [], lw=0, marker="o", color=ink, label="Returned fix"),
        Line2D([], [], lw=0, marker="x", color=ink, label="Forced estimate (withheld)"),
    ]
    figure.legend(
        handles=key, loc="lower center", bbox_to_anchor=(0.52, 0.031), ncol=4, frameon=False
    )
    stream = io.BytesIO()
    canvas.print_png(stream)
    write(out_path, stream.getvalue())
    if pdf_path is not None:
        pdf = io.BytesIO()
        figure.savefig(
            pdf,
            format="pdf",
            metadata={
                "Title": SYNTHETIC_TITLE,
                "Subject": f"SHA-256 {hashlib.sha256(source).hexdigest()}",
                "CreationDate": None,
                "ModDate": None,
            },
        )
        write(pdf_path, pdf.getvalue())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("replay", "synthetic", "score", "figure"))
    parser.add_argument("--scratch", type=Path, default=Path("/tmp/glrt-pass-geometry"))
    parser.add_argument("--report", type=Path, default=OUTPUT)
    parser.add_argument("--cpus", type=int, nargs=4, default=(2, 3, 4, 5))
    parser.add_argument("--seed-hex")
    args = parser.parse_args()
    scratch, report = local_output(args.scratch), local_output(args.report)
    scratch.mkdir(parents=True, exist_ok=True)
    if args.action == "score":
        score(report)
    elif args.action == "figure":
        write_synthetic_figure(
            report / "synthetic-scores.json",
            report / "synthetic-errors.png",
            pdf_path=report / "synthetic-errors.pdf",
        )
    elif args.action == "replay":
        replay(scratch, report, args.cpus)
    else:
        prospective(scratch, report, args.cpus, args.seed_hex)


if __name__ == "__main__":
    main()
