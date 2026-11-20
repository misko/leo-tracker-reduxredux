"""Apply the frozen phase stop to stored initial trajectories without numerical replay."""

import argparse
import gzip
import json
import math
from concurrent.futures import ProcessPoolExecutor
from hashlib import file_digest
from pathlib import Path
from time import perf_counter
from zipfile import ZipFile

import numpy as np

from .. import corpus
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km
from ..variants import stable_phase
from ..variants.v5_lean import SOURCE_SHA256
from . import prefix_figures
from .full_v5_check import REPO, _sha
from .initial_branch_audit import ARCHIVE, DS29, _map, read_choices, value

REPORT = REPO / "reports/2026_11_19_receiver_screening/recovery/phase-history-audit"
PARENT = REPORT.with_name("stable-phase") / "plan.json"
METHOD = "stable_phase_initial_audit"
CONTROL = "original_initial_phase_history"
ROUNDS = 5


def stop_index(rows):
    return next(
        (
            i
            for i, row in enumerate(rows)
            if i >= 1
            and row["raw_phase_change_s"] <= stable_phase.PHASE_SECONDS
            and row["movement_km"] <= stable_phase.POSITION_KM
        ),
        len(rows) - 1,
    )


def winner(branches, *, stopped):
    field = "stop_index" if stopped else None
    return min(
        range(len(branches)),
        key=lambda i: branches[i]["c0"]["rounds"][branches[i]["c0"][field] if field else -1][
            "objective"
        ],
    )


def fit_values(fit, archive):
    point = value(fit["parameters"], archive)
    values = [value(fit[key], archive) for key in ("score", "residual_rms_hz")]
    if len(point) != 2 or not all(math.isfinite(x) for x in (*point, *values)) or values[1] < 0:
        raise ValueError("invalid archived initial fit position or RF metric")
    return dict(east_north_km=point, objective=values[0], conditional_rms_hz=values[1])


def trajectory(arm, archive):
    series = _map(arm)["phase_rounds"]
    if series[0] != "list" or len(series[1]) != ROUNDS:
        raise ValueError("expected the original five phase rounds")
    starts = np.zeros(2)
    previous = None
    rows = []
    for epoch, item in enumerate(series[1]):
        row = _map(item)
        fields = fit_values(_map(row["fit"]), archive)
        reference, posterior = (
            np.asarray(value(row[key], archive), dtype=float)
            for key in ("phase_reference", "posterior_phase_s")
        )
        if (
            row["epoch"] != epoch
            or reference.ndim != 1
            or not reference.size
            or reference.shape != posterior.shape
            or not np.isfinite(reference).all()
            or not np.isfinite(posterior).all()
            or not np.array_equal(
                reference,
                np.zeros_like(reference) if previous is None else np.clip(previous, -15, 15),
            )
        ):
            raise ValueError("archived phase reference does not follow the preceding raw posterior")
        change = float(np.max(np.abs(posterior - reference)))
        saved = value(row["max_reference_change_s"], archive)
        if not math.isclose(change, saved, rel_tol=0, abs_tol=1e-12):
            raise ValueError("stored maximum raw phase change differs from its arrays")
        after = np.asarray(fields["east_north_km"], dtype=float)
        rows.append(
            dict(
                epoch=epoch,
                start_east_north_km=starts.tolist(),
                movement_km=float(np.linalg.norm(after - starts)),
                raw_phase_change_s=change,
                **fields,
            )
        )
        starts, previous = after, posterior
    full = fit_values(_map(_map(arm)["fit"]), archive)
    if full != {key: rows[-1][key] for key in full}:
        raise ValueError("original branch's selected fit differs from its final phase round")
    return dict(stop_index=stop_index(rows), rounds=rows)


def point(row, center):
    east, north = row["east_north_km"]
    return dict(
        latlon=[
            center[0] + north / 111,
            center[1] + east / (111.32 * np.cos(np.deg2rad(center[0]))),
        ],
        rf_rms_hz=row["conditional_rms_hz"],
        initial_objective=row["objective"],
    )


def audit(task):
    case_id, dataset, case, summary = task
    directory = (ARCHIVE if dataset == "DS26" else DS29) / f"{case_id}-r0"
    path = directory / "baseline/experimental-evidence.zip"
    receipt = json.loads((directory / "baseline-execution.json").read_bytes())
    with path.open("rb") as stream:
        digest = "sha256:" + file_digest(stream, "sha256").hexdigest()
    if (
        digest != summary["archive_sha256"]
        or receipt["worker"]["artifact"]["sha256"] != digest
        or receipt["worker"]["source_sha256"] != SOURCE_SHA256
        or (receipt["role"], receipt["status"]) != ("baseline", "complete")
    ):
        raise ValueError(f"{case_id} original initial archive differs from the frozen receipt")

    with ZipFile(path) as archive:
        raw = archive.read("values.json")
        if (
            raw.count(b'["request_sha256",') != 1
            or raw.count(encoded(["request_sha256", receipt["request_sha256"]])) != 1
        ):
            raise ValueError(f"{case_id} checkpoint request digest differs from worker receipt")
        choices, selected = read_choices(raw)
        del raw
        centers = [value(choice["center_score"], archive) for choice in choices]
        branches = [
            {a: trajectory(_map(choice["arms"])[a], archive) for a in ARMS} for choice in choices
        ]
    if (
        [row["hypothesis"] for row in choices] != list(range(len(choices)))
        or centers != sorted(centers)
        or selected != winner(branches, stopped=False)
    ):
        raise ValueError("original cold branch order or minimum c0 loss was not reproduced")
    chosen = winner(branches, stopped=True)
    (tile,) = case["regions"]
    before = {a: point(branches[selected][a]["rounds"][-1], tile["center"]) for a in ARMS}
    after = {
        a: point(branches[chosen][a]["rounds"][branches[chosen][a]["stop_index"]], tile["center"])
        for a in ARMS
    }
    for arm, row in before.items():
        old = summary["stages"]["initial"][arm]
        if (
            distance_km(row["latlon"], old["latlon"]) > 1e-7
            or row["rf_rms_hz"] != old["conditional_rms_hz"]
        ):
            raise ValueError("original selected initial endpoint differs from previous authority")
    meta = dict(
        id=case_id,
        dataset=dataset,
        native_sha256=case["native"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        input_sha256=receipt["request_sha256"].removeprefix("sha256:"),
        source_archive_sha256=digest.removeprefix("sha256:"),
    )
    return dict(
        meta,
        original_rank=selected,
        stopped_rank=chosen,
        branches=branches,
        original_initial=before,
        stopped_initial=after,
        original_final=summary["stages"]["final"],
    )


def load_tasks():
    _, bound = corpus._selection("roof16")
    items = corpus._index(corpus._read_frozen("inputs.jsonl", bound))
    originals = prefix_figures.load_rows(prefix_figures.REPORT)
    if len(originals) != 135:
        raise ValueError("expected the complete matched roof roster")
    return [
        (ident, data[0]["group"], items[ident], data[2])
        for ident, data in sorted(originals.items())
    ]


def pack(output, name, rows):
    path = output / name
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
    return _sha(path)


def replay(output, jobs):
    began = perf_counter()
    parent = json.loads(PARENT.read_bytes())
    source = Path(stable_phase.__file__)
    digest = _sha(source)
    if digest != parent["source"]["study"]["stable_phase.py"] or jobs not in (1, 2):
        raise ValueError("audit requires the frozen rule and a one- or two-lane reader")
    tasks = load_tasks()
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        rows = list(pool.map(audit, tasks))
    if _sha(source) != digest:
        raise ValueError("stable phase source changed during audit")
    receipts = dict(
        cases=[r["id"] for r in rows],
        rule_sha256=digest,
        parent_plan_sha256=_sha(PARENT),
        audit_sha256=_sha(Path(__file__)),
        cutoff=dict(
            phase_s=stable_phase.PHASE_SECONDS,
            movement_km=stable_phase.POSITION_KM,
            earliest_epoch=1,
        ),
        original_science_sha256=SOURCE_SHA256,
        archive_lanes=jobs,
        archive_audit_wall_s=perf_counter() - began,
    )
    receipts["files"] = {"phase-histories.jsonl.gz": pack(output, "phase-histories.jsonl.gz", rows)}
    save_json(output / "audit-lock.json", receipts)
    elapsed = receipts["archive_audit_wall_s"]
    print(f"{len(rows)} sealed original initial histories in {elapsed:.2f} s", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=REPORT)
    parser.add_argument("--lanes", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    replay(args.out, args.lanes)


if __name__ == "__main__":
    main()
