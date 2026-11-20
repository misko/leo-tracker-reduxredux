"""Replay both sealed waveform requests through the installed interior publication profile."""

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from ..__main__ import save_json, write
from ..scoring import ARMS, distance_km
from ..variants.compact_tile_interior import guard
from . import screening_figures
from . import waveform_site_results as scores
from . import waveform_site_trial as trial

PROFILE = Path.home() / ".cache/leo-installed-interior-20261119/interior"
AUTHORITY = trial.REPORT.parents[1] / "receiver-core/installed-interior/source-lock.json"
METHOD = "waveform_site_interior"
FILES = ("plan.json", "positions.jsonl.gz", "queries.json", "parity.json", "scores.json")


def exact_parity(installed, raw, case):
    expected = guard(raw, dict(center=case["tile"], width_km=25.0))
    if (
        installed["status"] == "ok"
        or installed.get("reason") == "terminal_compact_fit_at_tile_face"
    ):
        expected_metrics = {k: v for k, v in expected["metrics"].items() if k != "stage_s"}
        actual_metrics = {k: v for k, v in installed["metrics"].items() if k != "stage_s"}
        return expected_metrics == actual_metrics and all(
            installed.get(k) == expected.get(k) for k in ("status", "reason", "arms", "boundary")
        )
    return None


def run(work, out, profile):
    primary = out.parent
    prediction = trial.sealed(primary, "prediction-lock.json")
    trial.sealed(primary, "score-lock.json")
    base = scores.read_rows(primary / "positions.jsonl.gz")
    requests = trial.read(primary / "requests.json")
    source = trial.read(AUTHORITY)
    if any(trial.digest(profile / path) != checksum for path, checksum in source["files"].items()):
        raise ValueError("installed interior receiver differs from its published source lock")
    public = work / "public"
    history = trial.read(primary / "causal-authority.json")
    leaves = public / "tle/archive/space-track"
    if (
        {p.name for p in leaves.glob("*.tle")} != set(history)
        or any(trial.digest(leaves / name) != r["sha256"] for name, r in history.items())
        or any(
            trial.digest(public / r[name]) != r[key]
            for r in requests
            for name, key in (("native", "native_sha256"), ("track_config", "config_sha256"))
        )
    ):
        raise ValueError("retrospective requests lack their exact frozen waveform inputs")
    scratch = work / "interior-profile"
    scratch.mkdir()
    os.symlink(public, scratch / "public", target_is_directory=True)
    save_json(
        out / "plan.json",
        dict(
            retrospective=True,
            previous_outcomes_known=True,
            exact_fixed_guard=True,
            threshold_km=0.02,
            cases=prediction["cases"],
            base_predictions_sha256=trial.digest(primary / "prediction-lock.json"),
            source_sha256=trial.digest(Path(__file__)),
            shared_runner_sha256=trial.digest(Path(trial.__file__)),
            installed_source_lock_sha256=trial.digest(AUTHORITY),
            installed_files=source["files"],
            cpus=trial.POS_CPUS,
            memory_max=trial.MEMORY,
            swap_max=0,
            position_limit_s=trial.POS_LIMIT,
        ),
    )
    # The sealed stock runner differs only in the install tree and receipt method here.
    with (
        patch.multiple(trial, INSTALL=profile, METHOD=METHOD),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        jobs = [
            pool.submit(trial.position_attempt, scratch, req, cpu)
            for req, cpu in zip(requests, trial.POS_CPUS, strict=True)
        ]
        rows = [job.result() for job in jobs]
    base_rows = {r["id"]: r for r in base}
    trial.pack(out, "positions.jsonl.gz", rows)
    queries = trial.read(primary / "figure-queries.json")
    save_json(out / "queries.json", dict(queries=queries))
    query = {r["id"]: r for r in queries}
    parity, scored = [], []
    for row, case in zip(rows, requests, strict=True):
        rid, result = row["id"], row["result"]
        raw = base_rows[rid]
        if any(row[k] != raw[k] for k in ("input_sha256", "native_sha256", "catalogue_sha256")):
            raise ValueError("interior installation received different scientific inputs")
        parity.append(dict(id=rid, exact_parity=exact_parity(result, raw["result"], case)))
        ref = query[rid]
        for arm in ARMS:
            fit = result["arms"][arm]
            scored.append(
                dict(
                    id=rid,
                    arm=arm,
                    condition=ref["condition"],
                    status=result["status"],
                    published=fit["latlon"] is not None,
                    false_publication=ref["condition"] == "omitted" and fit["latlon"] is not None,
                    position_error_km=distance_km(ref["truth"], fit["latlon"]),
                    forced_error_km=distance_km(ref["truth"], fit.get("forced_latlon")),
                    rf_rms_hz=fit.get("rf_rms_hz"),
                    **{k: row[k] for k in ("worker_wall_s", "worker_cpu_s", "peak_rss_kib")},
                )
            )
        print(
            rid,
            result["status"],
            round(row["worker_wall_s"], 2),
            parity[-1]["exact_parity"],
            flush=True,
        )
    save_json(out / "parity.json", parity)
    save_json(out / "scores.json", scored)
    write(out / "stock-positions.jsonl.gz", (primary / "positions.jsonl.gz").read_bytes())
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=prediction["cases"],
            files={p: trial.digest(out / p) for p in (*FILES, "stock-positions.jsonl.gz")},
        ),
    )
    spec = dict(
        id="waveform-site-interior",
        method=METHOD,
        scope="transfer",
        cases="sealed",
        title="Installed 20 m interior policy on the same Qin waveform",
        caption=(
            "Retrospective replay of both sealed 25 km requests with the unchanged installed "
            "20 m rule. Both profiles used identical detected factors and causal ephemerides. "
            "Forced positions show the underlying fit after the publication decision."
        ),
        seal="prediction-lock.json",
        queries="queries.json",
        provenance=["plan.json", "parity.json", "scores.json"],
        condition_labels={
            "containing": "25 km containing offer",
            "omitted": "25 km near-omitted offer",
        },
        series=[
            dict(
                key="candidate",
                label="Interior profile",
                file="positions.jsonl.gz",
                value=METHOD,
                forced_label="Interior forced fit",
            ),
            dict(
                key="stock",
                label="Phase release",
                file="stock-positions.jsonl.gz",
                value=trial.METHOD,
                match=["input_sha256", "native_sha256", "catalogue_sha256"],
            ),
        ],
    )
    save_json(out / "figures.json", dict(version=1, charts=[spec]))
    screening_figures.generate(out / "charts", methods=[METHOD], evidence=out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("--out", type=Path, default=trial.REPORT / "interior-profile")
    p.add_argument("--profile", type=Path, default=PROFILE)
    args = p.parse_args()
    run(args.work, args.out, args.profile)


if __name__ == "__main__":
    main()
