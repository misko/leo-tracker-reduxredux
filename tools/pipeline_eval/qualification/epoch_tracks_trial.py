"""Replay causal epoch links and stock Graph through the capped phase-release receiver."""

import argparse
import gzip
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from .. import cavity_runtime
from ..__main__ import local_output, save_json, write
from ..variants import coherent_peak_filter, epoch_tracks, track_epoch
from . import cavity_payload_transfer as receiver
from .factor_cross_trial import write_members
from .full_v5_check import _load_case
from .input_factor_bridge import REPO, SCREEN, _sha, check, read
from .peak_support_trial import BAND
from .selective_capture_trial import archive_context

REPORT = SCREEN / "track-recovery/epoch-tracks"
STRIDE = SCREEN / "receiver-core/full-stride"
PROFILE = "phase-release"
LIMIT = 210
CPUS = (4, 5)
CASES = (
    ("DS26-0036", "DS29-0082"),
    ("DS26-0162", "DS29-0519"),
)
METHODS = {
    "DS26-0036": ("epoch", "graph"),
    "DS29-0082": ("graph", "epoch"),
    "DS26-0162": ("epoch",),
    "DS29-0519": ("epoch",),
}
OBSERVE = Path(__file__).with_name("epoch_tracks_probe.py").resolve()
TRACE = Path(__file__).with_name("alias_attribution_graph.py").resolve()
EXTRA = tuple(Path(m.__file__) for m in (epoch_tracks, coherent_peak_filter, track_epoch))


def prepare(root):
    if (REPORT / "plan.json").exists():
        raise ValueError("sealed epoch-track study already exists")
    installed = root / PROFILE
    cavity_runtime.install(installed, profile=PROFILE)
    package = cavity_runtime.release_files(cavity_runtime.RELEASE, PROFILE)
    if any((installed / n).read_bytes() != d for n, d in package.items()):
        raise ValueError("installed phase-release scientific sources differ from signed release")
    for p in EXTRA:
        shutil.copyfile(p, installed / "tools/pipeline_eval/variants" / p.name)
    release_files = {
        str(p.relative_to(installed)): _sha(p) for p in installed.rglob("*") if p.is_file()
    }
    jobs = []
    authorities = {}
    for cohort in CASES:
        for ident in cohort:
            study = BAND if ident in CASES[0] else STRIDE
            relative = (
                f"native/{ident}.json.gz" if study == BAND else f"native/control/{ident}.json.gz"
            )
            parent = study / "prediction-lock.json"
            original = study / relative
            check(original, read(parent)["files"][relative])
            case = _load_case(ident)
            work = root / ident
            work.mkdir()
            payload = gzip.decompress(original.read_bytes())
            header = json.loads(payload)
            if (
                header["source"]["session_id"] != case["session_id"]
                or header["clock_anchor"]["before"]["realtime_ns"] != case["cutoff_utc_ns"]
            ):
                raise ValueError("wide input differs from the frozen session and causal cutoff")
            native = work / "wide.json"
            write(native, payload)
            shared, config, archive, history = archive_context(case, work)
            authorities[ident] = dict(
                recording=ident,
                origin_native_sha256=case["native"]["sha256"],
                native_sha256=_sha(native),
                parent=str(parent.relative_to(REPO)),
                wide_factors=str(original.relative_to(REPO)),
                wide_factors_sha256=_sha(original),
                history=history,
            )
            for method in METHODS[ident]:
                binding = dict(
                    shared,
                    id=f"{ident}-{method}",
                    recording=ident,
                    method_key=method,
                    origin_native_sha256=case["native"]["sha256"],
                    native_sha256=_sha(native),
                )
                jobs.append((binding, native, config, archive, None))
    paths = (
        Path(__file__),
        OBSERVE,
        TRACE,
        Path(receiver.__file__),
        receiver.OBSERVER,
        REPORT / "PROTOCOL.md",
        *(p / "prediction-lock.json" for p in (BAND, STRIDE)),
        *EXTRA,
    )
    save_json(
        REPORT / "plan.json",
        dict(
            cases=[list(c) for c in CASES],
            sequence=METHODS,
            cpus=list(CPUS),
            deadline_s=LIMIT,
            memory_bytes=receiver.MEMORY,
            swap_bytes=0,
            authorities=authorities,
            receiver_files=release_files,
            inputs=[x[0] for x in jobs],
            sources={str(path.relative_to(REPO)): _sha(path) for path in paths},
        ),
    )
    return installed, jobs


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    tmp = root / "tmp"
    tmp.mkdir()
    os.environ["TMPDIR"] = str(tmp)
    installed, jobs = prepare(root)
    locked = REPORT / "plan.json"
    plan = read(locked)
    for name, digest in plan["receiver_files"].items():
        check(installed / name, digest)
    script = receiver.WORKER.replace(
        'worker.__globals__["TMP"] = tmp\n',
        'worker.__globals__["TMP"] = tmp\n'
        + f"runpy.run_path({str(OBSERVE)!r})['setup']("
        + f"tmp,tmp.parent.name.rsplit('-',1)[-1],{str(TRACE)!r})\n",
    )
    if script == receiver.WORKER:
        raise ValueError("phase worker observation insertion point changed")

    def lane(ident, cpu):
        out = []
        for job in jobs:
            binding, native, *_ = job
            if binding["recording"] != ident:
                continue
            check(native, binding["native_sha256"])
            row = receiver.capped(root, root, job, PROFILE, cpu)
            scratch = root / "runs" / row["id"] / PROFILE
            for key in ("track-stage", "tracks"):
                receipt = scratch / (key + ".json")
                row[key] = read(receipt) if receipt.is_file() else None
            save_json(scratch / "receipt.json", row)
            out.append(row)
        return out

    all_rows = []
    with patch.multiple(receiver, WORKER=script, LIMIT_S=LIMIT), ThreadPoolExecutor(2) as pool:
        for cohort in CASES:
            pending = [pool.submit(lane, i, cpu) for i, cpu in zip(cohort, CPUS, strict=True)]
            for future in pending:
                all_rows.extend(future.result())
            write_members(REPORT / "results.jsonl.gz", all_rows)
            save_json(
                REPORT / "prediction-lock.json",
                dict(
                    cases=[r["id"] for r in all_rows],
                    files={n: _sha(REPORT / n) for n in ("plan.json", "results.jsonl.gz")},
                ),
            )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=local_output)
    run(p.parse_args().root)
