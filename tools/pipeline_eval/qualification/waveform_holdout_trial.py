"""Qualify a second blind Qin waveform scene through both installed position profiles."""

import argparse
import gzip
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ..__main__ import save_json
from . import cold_scenes as cold
from . import waveform_holdout_model as model
from . import waveform_site_interior as interior
from . import waveform_site_trial as stock

REPORT = stock.REPORT.parents[1] / "acquisition-frontier/waveform-holdout"
METHODS = ("waveform_holdout_phase_release", "waveform_holdout_interior")
ANCHOR_DELAY_S = 7340
STOCK_FREEZE = stock.freeze
STOCK_MODEL = stock.model
STOCK_MODULE = stock.__name__
MODULE = "tools.pipeline_eval.qualification.waveform_holdout_trial"


def revised(received, old_sha):
    valid = []
    for path in cold.SNAPSHOT.parent.glob("*.json"):
        authority = stock.read(path)
        collection = cold._stamp(datetime.fromisoformat(authority["retrieved_at"]))
        epoch = cold._stamp(datetime.fromisoformat(authority["tle_epoch_max"]))
        if (
            epoch <= collection
            and received + 5 * 3600 * cold.NS <= collection <= received + 10 * 3600 * cold.NS
            and authority["raw_sha256"] != old_sha
        ):
            valid.append((collection, path, authority))
    if not valid:
        raise ValueError("no distinct revised catalogue in the predeclared time window")
    collection, path, authority = min(valid)
    body = (cold.TLE_ARCHIVE / authority["raw_object"]).read_bytes()
    if stock.raw_digest(body) != authority["raw_sha256"]:
        raise ValueError("revised catalogue bytes differ from authenticated metadata")
    return (
        body,
        collection,
        dict(
            collection_utc_ns=collection,
            metadata_sha256=stock.digest(path),
            raw_object=authority["raw_object"],
            raw_sha256=authority["raw_sha256"],
        ),
    )


def freeze(out):
    value = STOCK_FREEZE(out)
    if any(
        stock.digest(interior.PROFILE / path) != checksum
        for path, checksum in stock.read(interior.AUTHORITY)["files"].items()
    ):
        raise ValueError("installed 20 m profile differs from its publication seal")
    value["sources"].update(
        {
            str(p): stock.digest(p)
            for p in (Path(__file__), Path(STOCK_MODEL.__file__), interior.AUTHORITY)
        }
    )
    return dict(
        value,
        interior_install=stock.whole_iq.receiver_identity(interior.PROFILE),
        anchor_delay_s=ANCHOR_DELAY_S,
        prospective_methods=list(METHODS),
    )


def detector_command(command, *args, **kwargs):
    command = list(command)
    command[command.index(STOCK_MODULE)] = MODULE
    return subprocess.Popen(command, *args, **kwargs)


def detect(work, out):
    with patch.object(
        stock,
        "subprocess",
        SimpleNamespace(Popen=detector_command, TimeoutExpired=subprocess.TimeoutExpired),
    ):
        stock.detect(work, out)


def positions(work, out):
    if (out / "prediction-lock.json").exists():
        raise FileExistsError("holdout predictions already sealed")
    detector = stock.sealed(out, "detector-lock.json")
    stock.sealed(out, "input-lock.json")
    if freeze(out) != stock.read(out / "source-lock.json"):
        raise ValueError("holdout solver, truth model or driver changed")
    schedule = stock.read(out / "schedule.json")
    public = work / "public"
    history = stock.read(out / "causal-authority.json")
    leaves = public / "tle/archive/space-track"
    if {p.name for p in leaves.glob("*.tle")} != set(history) or any(
        stock.digest(leaves / name) != r["sha256"] for name, r in history.items()
    ):
        raise ValueError("position is missing an authenticated causal archive snapshot")
    requests_path = out / "requests.json"
    if detector["ready"]:
        requests = stock.read(requests_path)
        if {r["native_sha256"] for r in requests} != {
            stock.digest(public / "native.json"),
            stock.raw_digest(gzip.decompress((out / "native.json.gz").read_bytes())),
        } or {r["config_sha256"] for r in requests} != {stock.digest(public / "track-config.json")}:
            raise ValueError("position requests do not bind both emitted-waveform native copies")
    else:
        requests = [
            dict(r, native_sha256=None, catalog_sha256=schedule["catalog_sha256"])
            for r in schedule["offers"]
        ]
        save_json(requests_path, requests)
    if len(requests) != 3 or {r["id"] for r in requests} != {o["id"] for o in schedule["offers"]}:
        raise ValueError("the three predeclared blind regional offers are required")
    rows = []
    for method, executable in zip(METHODS, (stock.INSTALL, interior.PROFILE), strict=True):
        if detector["ready"]:
            trial = work / method
            trial.mkdir()
            (trial / "public").symlink_to(public, target_is_directory=True)
            with (
                patch.multiple(stock, INSTALL=executable, METHOD=method),
                ThreadPoolExecutor(max_workers=2) as pool,
            ):
                jobs = [
                    pool.submit(stock.position_attempt, trial, r, cpu)
                    for r, cpu in zip(requests[:2], stock.POS_CPUS, strict=True)
                ]
                outcome = [j.result() for j in jobs]
                outcome.append(stock.position_attempt(trial, requests[2], stock.POS_CPUS[0]))
            for r in outcome:
                print(
                    f"{method} {r['id']} {r['result']['status']} {r['worker_wall_s']:.2f}s",
                    flush=True,
                )
            rows.extend(outcome)
        else:
            for r in requests:
                rows.append(
                    dict(
                        id=r["id"],
                        method=method,
                        result=stock.no_estimate("unavailable", "Stock detector panel incomplete"),
                        input_sha256=stock.raw_digest(stock.encoded(r)),
                        native_sha256=None,
                        catalogue_sha256=r["catalog_sha256"],
                        worker_wall_s=None,
                        worker_cpu_s=None,
                        peak_rss_kib=None,
                    )
                )
    stock.pack(out, "positions.jsonl.gz", rows)
    names = (
        "positions.jsonl.gz",
        "requests.json",
        "input-lock.json",
        "detector-lock.json",
        "source-lock.json",
        "causal-authority.json",
    )
    save_json(
        out / "prediction-lock.json",
        dict(cases=[r["id"] for r in requests], files={n: stock.digest(out / n) for n in names}),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("prepare", "detect", "lane", "position"))
    p.add_argument("work", type=Path)
    p.add_argument("--out", type=Path, default=REPORT)
    p.add_argument("--lane", type=int, choices=range(2))
    p.add_argument("--seed-hex")
    args = p.parse_args()
    work, out = args.work.resolve(), args.out.resolve()
    with patch.multiple(
        stock, model=model, freeze=freeze, revised=revised, ANCHOR_DELAY_S=ANCHOR_DELAY_S
    ):
        if args.action == "prepare":
            stock.prepare(work, out, args.seed_hex)
        elif args.action == "detect":
            detect(work, out)
        elif args.action == "lane":
            stock.detector_lane(work, out, args.lane)
        else:
            positions(work, out)


if __name__ == "__main__":
    main()
