"""Prepare the six-recording factor census and run the fixed shared-probe ablation."""

import argparse
import gzip
import json
import os
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from ..__main__ import encoded, local_output, save_json, write
from . import cavity_payload_transfer as receiver
from .factor_cross_trial import write_members
from .full_v5_check import _load_case
from .input_factor_bridge import BULK, REPO, SCREEN, _sha, check, checked_history, read
from .input_factor_comparison import sealed
from .peak_support import SOURCES, examine, subset, thinned
from .raw_robust import prior_directory

REPORT = SCREEN / "acquisition-support/peak-support"
BAND = SCREEN / "detector-origins/whole-band"
ORDER = ("DS26-0036", "DS29-0082", "DS26-0237", "DS29-0174", "DS26-0122", "DS29-0247")
CPUS = (8, 9)
LIMIT = 135


def read_band():
    sealed(BAND, "prediction-lock.json")
    with gzip.open(BAND / "positions.jsonl.gz", "rt") as stream:
        wide = {
            r["id"]: r for r in map(json.loads, stream) if r["method"] == "regional_wide_full_iq"
        }
    plan = read(BAND / "source-lock.json")
    if set(wide) != set(plan["cases"]) or set(wide) != set(ORDER):
        raise ValueError("complete wide evidence differs from the declared six recordings")
    return wide, plan


def authority(ident, wide, band):
    data = band["cases"][ident]
    case = _load_case(ident)
    paths = (
        BULK / case["native"]["path"],
        prior_directory(ident) / "native.json",
        BAND / "native" / (ident + ".json.gz"),
    )
    pins = (
        data["capture_native_sha256"],
        data["ordinary_sha256"],
        wide[ident]["native_sha256"],
    )
    records = []
    for source, path, digest in zip(SOURCES, paths, pins, strict=True):
        content = path.read_bytes()
        if source == "wide":
            content = gzip.decompress(content)
        if sha256(content).hexdigest() != digest:
            raise ValueError(f"{ident} {source} factor digest differs")
        records.append(json.loads(content))
    job_path = BULK / case["request"]["path"]
    request = check(job_path, data["request_sha256"])
    causal = read(job_path)
    if causal["causal_snapshots"] != data["history"]:
        raise ValueError("causal snapshots differ from the common full receiver request")
    job = causal["job"]
    archive = Path(job["tle_root"])
    history = checked_history(job, causal["causal_snapshots"], case["cutoff_utc_ns"])
    config = Path(job["track_config"]["path"])
    config_sha = check(config, case["track_config"]["sha256"])
    settings = dict(
        recording=ident,
        tile=dict(case["regions"][0], width_km=25),
        capture_id=case["session_id"],
        track_config_sha256=config_sha,
        screen_center=job["screen_center"],
        catalog_sha256=case["catalog"]["sha256"],
    )
    if (
        history[-1]["sha256"] != settings["catalog_sha256"]
        or job["evaluation_reference"] is not None
        or job["search_center"] != settings["tile"]["center"]
        or job["identity"]["session_id"] != settings["capture_id"]
    ):
        raise ValueError("session, tile or causal catalogue changed")
    return (
        settings,
        (config, archive),
        records,
        dict(
            paths={source: str(path) for source, path in zip(SOURCES, paths, strict=True)},
            native_sha={source: digest for source, digest in zip(SOURCES, pins, strict=True)},
            request_sha256=request,
            history=history,
        ),
    )


def prepare(root):
    wide, band = read_band()
    package = receiver.bound_packages(receiver.RELEASE)["small"]
    release = SCREEN / "next/cavity-payload"
    lock = sealed(release, "prediction-lock.json")
    packaged = read(release / "package.json")
    if packaged["count"] != 78 or any(
        packaged[k] != package[k] for k in ("archive_sha256", "files", "binaries")
    ):
        raise ValueError("published standalone package differs from the measured distribution")
    if (REPORT / "plan.json").exists():
        raise ValueError("a peak-support plan already exists")
    sources = {
        str(p.relative_to(REPO)): _sha(p)
        for p in (
            Path(__file__),
            Path(__file__).with_name("peak_support.py"),
            REPORT / "PROTOCOL.md",
            Path(receiver.__file__),
            receiver.OBSERVER,
            BAND / "prediction-lock.json",
            release / "prediction-lock.json",
            release / "package.json",
        )
    }
    save_json(
        REPORT / "input-lock.json",
        dict(
            cases=list(ORDER),
            package_sha256=lock["files"]["package.json"],
            sources=sources,
            band_lock_sha256=_sha(BAND / "prediction-lock.json"),
        ),
    )
    records, audits, selections, authorities = [], {}, {}, {}
    for i, ident in enumerate(ORDER):
        settings, (config, archive), documents, bound = authority(ident, wide, band)
        statistics, selected = examine(documents)
        random = thinned(ident, documents[0], selected)
        audits[ident] = statistics
        authorities[ident] = bound
        selections[ident] = dict(
            common=selected,
            random=random,
            overlap=len(set(random) & set(selected)),
            probes=len(documents[0]["source"]["probes"]),
        )
        print(ident, f"common={len(selected)}", flush=True)
        save_json(REPORT / "peak-census.json", audits)
        if i >= 4:
            continue
        for symbol, document in zip(SOURCES, documents, strict=True):
            for kind, indices in (("common", selected), ("random", random)):
                row_id = f"{ident}-{symbol}-{kind}"
                label = dict(
                    id=row_id,
                    condition=kind,
                    factor_source=symbol,
                    parent_native_sha256=bound["native_sha"][symbol],
                )
                payload = subset(document, indices, label)
                path = root / "native" / (row_id + ".json")
                write(path, encoded(payload) + b"\n")
                row = dict(
                    settings,
                    **label,
                    native_sha256=_sha(path),
                    selected_probes=len(indices),
                    origin_native_sha256=bound["native_sha"][
                        "capture-era" if symbol == "capture-era" else "ordinary"
                    ],
                )
                records.append((row, path, config, archive, None))
    write_members(REPORT / "support.jsonl.gz", (dict(id=k, **v) for k, v in selections.items()))
    save_json(
        REPORT / "plan.json",
        dict(
            sources=sources,
            authorities=authorities,
            inputs=[row for row, *_ in records],
            cpus=CPUS,
            deadline_s=LIMIT,
            memory_bytes=receiver.MEMORY,
            swap_bytes=0,
            files={
                name: _sha(REPORT / name)
                for name in (
                    "peak-census.json",
                    "support.jsonl.gz",
                    "input-lock.json",
                )
            },
        ),
    )
    return records


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    (root / "native").mkdir()
    os.environ["TMPDIR"] = str(root)
    records = prepare(root)
    plan_sha = _sha(REPORT / "plan.json")
    results = []

    def lane(ident, cpu):
        completed = []
        for job in records:
            if job[0]["recording"] != ident:
                continue
            check(job[1], job[0]["native_sha256"])
            row = receiver.capped(root, receiver.RELEASE, job, "small", cpu)
            save_json(root / "runs" / row["id"] / "checked.json", row)
            completed.append(row)
        return completed

    with patch.object(receiver, "LIMIT_S", LIMIT), ThreadPoolExecutor(len(CPUS)) as pool:
        for batch in (ORDER[:2], ORDER[2:4]):
            active = [pool.submit(lane, id, cpu) for id, cpu in zip(batch, CPUS, strict=True)]
            for worker in active:
                results.extend(worker.result())
            path = REPORT / "results.jsonl.gz"
            write_members(path, results)
            save_json(
                REPORT / "prediction-lock.json",
                dict(
                    cases=[r["id"] for r in results],
                    files={path.name: _sha(path), "plan.json": plan_sha},
                ),
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=local_output)
    run(parser.parse_args().root)
