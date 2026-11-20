"""Seal and run crossed native factor diagnostics on the compact receiver."""

import argparse
import gzip
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from ..__main__ import encoded, local_output, save_json, write
from . import cavity_payload_transfer as trial
from .factor_cross import TREATMENTS, assess, interchange
from .fractional_runtime_whole import verify_request
from .full_v5_check import _load_case
from .input_factor_bridge import BULK, REPO, RUN, SCREEN, _sha, check, checked_history, read
from .input_factor_comparison import DEVELOPMENT, sealed
from .input_factor_comparison import REPORT as ORIGINAL

REPORT = SCREEN / "detector-origins/crossed-factors"
TRIAL = (DEVELOPMENT, ("DS26-0237", "DS29-0174"))
CPUS = (10, 11)
LIMIT = 135


def write_members(path, rows):
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))


def load_pair(ident, known):
    case = _load_case(ident)
    truth_free = BULK / case["request"]["path"]
    original = read(truth_free)
    check(truth_free, case["request"]["sha256"])
    base = RUN / ("whole-fractional" if ident in DEVELOPMENT else "full-held-pair") / ident
    request = base / "position/request.json"
    check(request, known["request_sha256"]["ordinary"])
    verify_request(
        read(request),
        original,
        native_path=base / "native.json",
        native_sha256=known["ordinary_native_sha256"],
    )
    files = (BULK / case["native"]["path"], base / "native.json")
    refs = (known["capture_era_native_sha256"], known["ordinary_native_sha256"])
    for path, key in zip(files, refs, strict=True):
        check(path, key)
    job = original["job"]
    cfg = Path(job["track_config"]["path"])
    check(cfg, case["track_config"]["sha256"])
    history = checked_history(job, original["causal_snapshots"], case["cutoff_utc_ns"])
    if history != known["causal_history"]:
        raise ValueError("causal catalogue changed from the exact factor comparison")
    return (
        dict(
            recording=ident,
            tile=dict(case["regions"][0], width_km=25),
            capture_id=case["session_id"],
            track_config_sha256=case["track_config"]["sha256"],
            screen_center=job["screen_center"],
            catalog_sha256=case["catalog"]["sha256"],
        ),
        (cfg, Path(job["tle_root"])),
        files,
        refs,
    )


def prepare(root):
    if (REPORT / "plan.json").exists():
        raise ValueError("crossed-factor source and inputs already frozen")
    sealed(ORIGINAL, "prediction-lock.json")
    known = read(ORIGINAL / "comparison.json")["cases"]
    package = trial.bound_packages(trial.RELEASE)["small"]
    shipped = SCREEN / "next/cavity-payload/package.json"
    if package["count"] != 78 or package["archive_sha256"] != read(shipped)["archive_sha256"]:
        raise ValueError("unexpected standalone scientific package")
    records, maps, audits = [], {}, {}
    for cohort in TRIAL:
        for ident in cohort:
            settings, (config, archive), files, digests = load_pair(ident, known[ident])
            first, second = tuple(map(read, files))
            rows, audit = assess(first, second)
            audits[ident], maps[ident] = audit, rows
            for name in TREATMENTS:
                for reverse in (False, True):
                    base, donor = (second, first) if reverse else (first, second)
                    recipient_sha, donor_sha = digests[::-1] if reverse else digests
                    recipient_label = "ordinary" if reverse else "capture-era"
                    row_id = f"{ident}-{recipient_label}-{name}"
                    labeled = dict(
                        id=row_id,
                        treatment=name,
                        recipient=recipient_label,
                        recipient_native_sha256=recipient_sha,
                        donor_native_sha256=donor_sha,
                    )
                    payload, changes = interchange(base, donor, rows, name, reverse=reverse)
                    payload["provenance"] = dict(
                        base["provenance"], crossed_factor_diagnostic=labeled
                    )
                    target = root / "hybrids" / (row_id + ".json")
                    write(target, encoded(payload) + b"\n")
                    row = dict(
                        settings,
                        **labeled,
                        native_sha256=_sha(target),
                        changes=changes,
                        origin_native_sha256=known[ident]["ordinary_stock_sha256"]
                        if reverse
                        else recipient_sha,
                    )
                    records.append((row, target, config, archive, None))
    write_members(REPORT / "matches.jsonl.gz", (dict(id=k, indices=v) for k, v in maps.items()))
    save_json(REPORT / "matching.json", audits)
    plan = dict(
        stages=TRIAL,
        cpus=CPUS,
        per_service_limit_s=LIMIT,
        memory_bytes=trial.MEMORY,
        swap_bytes=0,
        package_archive_sha256=package["archive_sha256"],
        cases=[row for row, *_ in records],
        files={
            name: _sha(REPORT / name)
            for name in ("matching.json", "matches.jsonl.gz", "PROTOCOL.md")
        },
        sources={
            str(p.relative_to(REPO)): _sha(p)
            for p in (
                Path(__file__),
                Path(trial.__file__),
                trial.OBSERVER,
                Path(__file__).with_name("factor_cross.py"),
                ORIGINAL / "prediction-lock.json",
                shipped,
            )
        },
    )
    save_json(REPORT / "plan.json", plan)
    return records


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    (root / "hybrids").mkdir()
    records = prepare(root)
    plan_sha = _sha(REPORT / "plan.json")
    scored = []

    def lane(cpu, jobs):
        completed = []
        for job in jobs:
            check(job[1], job[0]["native_sha256"])
            row = trial.capped(root, trial.RELEASE, job, "small", cpu)
            destination = root / "runs" / row["id"] / "checked.json"
            save_json(destination, row)
            completed.append(row)
        return completed

    with patch.object(trial, "LIMIT_S", LIMIT), ThreadPoolExecutor(len(CPUS)) as pool:
        for ids in TRIAL:
            for treatments in (("score", "cfo"), ("both",)):
                active = [
                    pool.submit(
                        lane,
                        cpu,
                        [
                            job
                            for job in records
                            if job[0]["recording"] == ident and job[0]["treatment"] in treatments
                        ],
                    )
                    for ident, cpu in zip(ids, CPUS, strict=True)
                ]
                for pending in active:
                    scored.extend(pending.result())
                path = REPORT / "results.jsonl.gz"
                write_members(path, scored)
                save_json(
                    REPORT / "prediction-lock.json",
                    dict(
                        cases=[r["id"] for r in scored],
                        pending=[
                            row["id"]
                            for row, *_ in records
                            if row["id"] not in {r["id"] for r in scored}
                        ],
                        files={path.name: _sha(path), "plan.json": plan_sha},
                    ),
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=local_output)
    run(parser.parse_args().root)
