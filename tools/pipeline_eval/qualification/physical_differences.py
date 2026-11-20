"""Prepare anonymous exact-timestamp beacon pairs and score a sealed physical panel."""

import argparse
import gzip
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from itertools import combinations
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.io import loadmat

from ..__main__ import ROOT, encoded, read_predictions, save_json, write
from ..reference import grid
from ..scoring import ARMS, distance_km, distribution, validate_result
from . import physical_transfer as prior
from .physical_differences_solver import BOUNDARY

OUTPUT = ROOT / "reports/2026_11_19_receiver_screening/inference/physical-differences"
METHOD = "coincident_beacon_difference"
SOLVER = Path(__file__).with_name("physical_differences_solver.py")
MODES = ("supplied-tile", "omitted-tile", "shuffled")
CPUS = (0, 7)
RF_HZ = 11_325_000_000
COMB_HZ = 43_945.5
BIN_HZ = 2_000_000 / 28_000


def digest(raw):
    return sha256(raw).hexdigest()


def _json(path, sha=None):
    return json.loads(prior._read(path, sha))


def consolidate(window):
    rows = window[:, :2].real
    order = np.argsort(rows[:, 0], kind="stable")
    times, first, counts = np.unique(rows[order, 0], return_index=True, return_counts=True)
    values = rows[order, 1]
    if len(times) < 5 or not np.isfinite(rows).all():
        raise ValueError("the raw beacon release has an invalid curve")
    return times, np.array(
        [np.median(values[k : k + n]) for k, n in zip(first, counts, strict=True)]
    )


def simultaneous(arcs):
    offered, audit = [], []
    for (i, (ti, fi)), (j, (tj, fj)) in combinations(enumerate(arcs), 2):
        common, a, b = np.intersect1d(ti, tj, assume_unique=True, return_indices=True)
        if not len(common):
            continue
        span = float(common[-1] - common[0])
        first, second = fi[a], fj[b]
        difference = first - second
        center = float(np.median(difference))
        nearest = round(center / COMB_HZ)
        comb_copy = bool(
            span >= 6
            and np.median(abs(difference - nearest * COMB_HZ)) <= 25 * BIN_HZ
            and np.median(abs(difference - center)) <= 7 * BIN_HZ
        )
        eligible = len(common) >= 20 and span >= 6 and not comb_copy
        row = dict(
            track_rows=[i, j],
            coincident_epochs=len(common),
            span_s=span,
            difference_span_hz=float(np.ptp(difference)),
            median_level_hz=center,
            median_centered_absolute_hz=float(np.median(abs(difference - center))),
            harmonic_like=comb_copy,
            eligible=eligible,
            selected=False,
        )
        audit.append(row)
        if eligible:
            indices = np.rint(np.linspace(0, len(common) - 1, min(24, len(common)))).astype(int)
            pair = dict(
                times=common[indices].tolist(),
                first_hz=first[indices].tolist(),
                second_hz=second[indices].tolist(),
            )
            offered.append((span, i, j, row, pair))
    used, pairs = set(), []
    for _, i, j, row, pair in sorted(offered, key=lambda x: (-x[0], x[1], x[2])):
        if i in used or j in used:
            continue
        used.update((i, j))
        row["selected"] = True
        pairs.append(pair)
    return pairs, audit


def shuffled(pairs, duration):
    control = []
    for pair in pairs:
        t = np.asarray(pair["times"])
        shift = 180 if t[-1] + 180 <= duration else -180
        moved = t + shift
        if moved[0] < 0 or moved[-1] > duration:
            raise ValueError("the predeclared pair shuffle leaves this capture")
        control.append(dict(pair, times=moved.tolist()))
    return control


def stage(raw_root):
    manifest = _json(prior.STUDY / "field-receipt.json")
    source = _json(prior.STUDY / "field_private/source_provenance.json")
    routing = [
        {k: r[k] for k in ("id", "pair", "condition", "site_group", "true_region")}
        for r in json.loads(prior._verified_truth(manifest))["cases"]
    ]
    locked = dict(
        solver_sha256=digest(SOLVER.read_bytes()),
        harness_sha256=digest(Path(__file__).read_bytes()),
        grid_sha256=digest(Path(grid.__file__).read_bytes()),
        protocol_sha256=digest((OUTPUT / "PROTOCOL.md").read_bytes()),
        scoring_truth_sha256=manifest["sealed_truth_sha256"],
    )
    public = prior.STUDY / "public_field"
    seen, coverage, jobs = set(), [], []
    for capture in source["captures"]:
        group = capture["site_group"]
        path = raw_root / capture["date"] / "tracked_tones.mat"
        prior._read(path, capture["track_file_sha256"])
        windows = loadmat(path, variable_names=["main_tone_dict"])["main_tone_dict"].ravel()
        arcs = [consolidate(row) for row in windows]
        pairs, details = simultaneous(arcs)
        primary = group not in seen
        coverage.append(
            dict(
                site_group=group,
                capture=capture["date"],
                primary=primary,
                raw_sha256=capture["track_file_sha256"],
                anonymous_curves=len(arcs),
                exact_coverage=details,
                selected_pairs=len(pairs),
            )
        )
        if not primary:
            continue
        seen.add(group)
        labels = {r["condition"]: r for r in routing if r["pair"] == capture["pair"]}
        present, missing = (labels[k] for k in ("present", "missing"))
        matched, omitted = (
            _json(public / "queries" / f"{r['id']}.json", manifest["public_query_sha256"][r["id"]])
            for r in (present, missing)
        )
        if any(matched[k] != omitted[k] for k in ("observation", "catalog")):
            raise ValueError("paired tiles do not bind the same physical capture")
        (correct,) = (r["center"] for r in matched["regions"] if r["id"] == present["true_region"])
        wrong = omitted["regions"][0]["center"]
        clock = _json(
            public / "observations" / f"{matched['observation']}.json", matched["observation"]
        )
        orbits = prior._read(
            public / "orbits" / f"{matched['catalog']}.tle", matched["catalog"]
        ).decode("ascii")
        observed = {
            k: clock[k]
            for k in ("anchor_utc_ns", "cutoff_utc_ns", "catalog_timestamp_ns", "duration_s")
        }
        observed.update(rf_hz=RF_HZ, pairs=pairs)
        if any(t[0] < 0 or t[-1] > clock["duration_s"] for t, _ in arcs):
            raise ValueError("raw STFT times are outside the public clock window")
        for mode, tile in zip(MODES, (correct, wrong, correct), strict=True):
            ident = digest(encoded([group, mode, present["id"], matched["observation"]]))[:32]
            obs = (
                dict(observed, pairs=shuffled(pairs, observed["duration_s"]))
                if mode == "shuffled"
                else observed
            )
            payload = encoded(
                dict(
                    id=ident,
                    observation=obs,
                    catalogue=orbits,
                    tile=tile,
                    solver_sha256=locked["solver_sha256"],
                )
            )
            jobs.append(
                (
                    dict(
                        id=ident,
                        site_group=group,
                        mode=mode,
                        tile_center=tile,
                        original_case=present["id"],
                        input_sha256=digest(payload),
                        native_mat_sha256=capture["track_file_sha256"],
                        observation_sha256=matched["observation"],
                        catalogue_sha256=matched["catalog"],
                    ),
                    payload,
                )
            )
    if len(seen) != 8 or len(jobs) != 24 or len(coverage) != 11:
        raise ValueError("the complete frozen measured-site archive is required")
    return jobs, coverage, locked


def one(binding, payload, cpu):
    start = perf_counter()
    command = prior._sandbox(cpu, [SOLVER])
    command[-4:-4] = [
        "--ro-bind",
        str(Path(grid.__file__)),
        "/worker/tools/pipeline_eval/reference/grid.py",
    ]
    command[-1] = prior.WORKER
    try:
        proc = subprocess.run(command, input=payload, capture_output=True, check=True, timeout=25)
        receipt = json.loads(proc.stdout)
        if receipt["id"] != binding["id"]:
            raise ValueError("worker changed the opaque request identifier")
    except (ValueError, subprocess.SubprocessError, OSError) as error:
        message = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-1300:]
        status = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
        receipt = dict(
            id=binding["id"],
            result=dict(
                status=status,
                reason=message or str(error),
                boundary=BOUNDARY,
                metrics={},
                arms={a: {"latlon": None, "forced_latlon": None} for a in ARMS},
            ),
        )
    validate_result(receipt["result"])
    print(
        binding["site_group"],
        binding["mode"],
        receipt["result"]["status"],
        receipt["result"]["reason"],
        flush=True,
    )
    return dict(
        receipt,
        method=METHOD,
        mode=binding["mode"],
        cpu=cpu,
        worker_wall_s=perf_counter() - start,
        input_sha256=binding["input_sha256"],
    )


def predict(raw_root):
    if (OUTPUT / "prediction-lock.json").exists():
        raise FileExistsError("the measured prediction panel is already sealed")
    jobs, coverage, sources = stage(raw_root)
    save_json(OUTPUT / "source-lock.json", sources)
    save_json(OUTPUT / "plan.json", dict(cases=[b for b, _ in jobs], cpu=list(CPUS)))
    save_json(OUTPUT / "simultaneous-coverage.json", dict(captures=coverage))

    def run_lane(slot):
        return [one(binding, packet, CPUS[slot]) for binding, packet in jobs[slot :: len(CPUS)]]

    with ThreadPoolExecutor(max_workers=len(CPUS)) as executor:
        by_id = {
            row["id"]: row for result in executor.map(run_lane, range(len(CPUS))) for row in result
        }
    payload = b"".join(encoded(by_id[b["id"]]) + b"\n" for b, _ in jobs)
    write(OUTPUT / "positions.jsonl.gz", gzip.compress(payload, mtime=0))
    files = ("positions.jsonl.gz", "plan.json", "source-lock.json", "simultaneous-coverage.json")
    save_json(
        OUTPUT / "prediction-lock.json",
        dict(
            cases=list(by_id), files={name: digest((OUTPUT / name).read_bytes()) for name in files}
        ),
    )


def score():
    lock = _json(OUTPUT / "prediction-lock.json")
    for name, expected in lock["files"].items():
        prior._read(OUTPUT / name, expected)
    sources = _json(OUTPUT / "source-lock.json")
    target = _json(prior.STUDY / "field_private/truth.json", sources["scoring_truth_sha256"])
    labels = {row["id"]: row for row in target["cases"]}
    plan = _json(OUTPUT / "plan.json")["cases"]
    predictions = read_predictions(OUTPUT / "positions.jsonl.gz")
    rows, figure_queries = [], []
    for item in plan:
        ident, group, mode = (item[k] for k in ("id", "site_group", "mode"))
        entry, label = predictions[ident], labels[item["original_case"]]
        if entry["input_sha256"] != item["input_sha256"] or label["site_group"] != group:
            raise ValueError("measured prediction or ground truth binding changed")
        truth = label["latlon"]
        figure_queries.append(
            dict(
                id=ident,
                condition=mode,
                recording=group,
                truth=truth,
                bindings={"input_sha256": item["input_sha256"]},
            )
        )
        for key, value in entry["result"]["arms"].items():
            issue, forced = value["latlon"], value.get("forced_latlon")
            rows.append(
                dict(
                    id=ident,
                    site_group=group,
                    cohort="prior" if group > "field-site-04" else "new",
                    mode=mode,
                    arm=key,
                    status=entry["result"]["status"],
                    issue=issue,
                    forced=forced,
                    false_issue=bool(mode != "supplied-tile" and issue is not None),
                    issued_error_km=distance_km(issue, truth),
                    forced_error_km=distance_km(forced, truth),
                    tile_center_error_km=distance_km(item["tile_center"], truth),
                    wall_s=entry["worker_wall_s"],
                    diagnostics=entry["result"]["metrics"],
                )
            )
    summary = {}
    for mode in MODES:
        group = [r for r in rows if r["mode"] == mode and r["arm"] == "c0"]
        summary[mode] = dict(
            attempts=len(group),
            issued=sum(r["issue"] is not None for r in group),
            forced=sum(r["forced"] is not None for r in group),
            **{
                key: distribution(r[key] for r in group)
                for key in ("issued_error_km", "forced_error_km", "tile_center_error_km", "wall_s")
            },
        )
    save_json(OUTPUT / "scores.json", dict(summary=summary, rows=rows))
    save_json(OUTPUT / "figure-queries.json", dict(queries=figure_queries))
    files = (*lock["files"], "prediction-lock.json", "scores.json", "figure-queries.json")
    save_json(
        OUTPUT / "figure-lock.json",
        dict(
            cases=[b["id"] for b in plan],
            files={name: digest((OUTPUT / name).read_bytes()) for name in files},
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("predict", "score"))
    parser.add_argument("--raw", type=Path)
    args = parser.parse_args()
    if args.phase == "score":
        score()
    elif args.raw is None:
        parser.error("predict needs the released timestamped MAT directories")
    else:
        predict(args.raw)


if __name__ == "__main__":
    main()
