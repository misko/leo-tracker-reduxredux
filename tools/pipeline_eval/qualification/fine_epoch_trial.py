"""Freeze a new original-schedule panel and trace per-epoch detector work."""

import argparse
import csv
import gzip
import os
import subprocess
from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

from ..__main__ import ROOT, encoded, save_json, write
from ..variants import fine_batch, fine_search, prepared_hotpath_peaks
from ..variants.original_kernel import PersistentGrid
from ..variants.selective_capture import visit_pairs
from . import fine_batch_trial as batch
from . import single_pass_trial as prior
from .capture_runtime import checked, read
from .full_v5_check import BULK, _load_case, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/original-schedule/fine-epoch-reuse"
WORK = Path("/srv/bulk/leo-dev/fine-epoch-20261120-A")
CASES = prior.CASE_IDS
N = 10
GUARD = "guard-witness"
MODULE = "tools.pipeline_eval.qualification.fine_epoch_trial"
ONE = "outcome-blind"
REPEATS = 5


def order(ident, purpose, visit):
    return sha256(encoded(["fine-epoch-v1", ident, purpose, visit])).digest()


def witnesses(ident, ledger, excluded):
    if ledger is None:
        return []
    buckets = {"primary": [], "retry": []}
    with ledger.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["status"] != "processed" or int(row["visit"]) in excluded:
                continue
            calls, inverse = int(row["calls"]), int(row["inverse_ffts"])
            wide, remainder = divmod(inverse - calls * 104_286, 86_751)
            if remainder:
                raise ValueError("prepared exact ledger changed anchor geometry")
            if calls - wide > 2:
                buckets["primary"].append(int(row["visit"]))
            if wide > 1:
                buckets["retry"].append(int(row["visit"]))
    return sorted(
        {v for k, rr in buckets.items() for v in sorted(rr, key=lambda x: order(ident, k, x))[:2]}
    )


def freeze(work):
    prior_input = prior.sealed(prior.REPORT, "qualification-lock.json", "input-lock.json")
    batch_input = prior.sealed(batch.REPORT, "qualification-lock.json", "input-lock.json")
    reference, fine = read(prior_input), read(batch_input)
    screen = REPORT.parents[1]
    ledgers = {
        "DS26-0237": prior.sealed(
            prior.selector_waveform.REPORT, "prediction-lock.json", "cache.csv"
        ),
        "DS29-0082": prior.sealed(
            screen / "pilot-search-and-region/field-exact-waveform",
            "prediction-lock.json",
            "coarse.csv",
        ),
    }
    all_cases = {}
    for ident, cfg in reference["cases"].items():
        case = _load_case(ident)
        archive = checked(BULK / case["native"]["path"], case["native"]["sha256"])
        rows = dict(visit_pairs(read(archive)["source"]["probes"]))
        excluded = {r["visit"] for r in cfg["rows"]}
        excluded.update(r["visit"] for r in fine["cases"].get(ident, {}).get("rows", []))
        held = sorted(sorted(set(rows) - excluded, key=lambda v: order(ident, "held", v))[:N])
        stress = witnesses(ident, ledgers.get(ident), excluded | set(held))
        items = []
        for visit in sorted(held + stress):
            seg, seq, manifest, digest = prior.original.locate(case, visit)
            items.append(
                dict(
                    visit=visit,
                    segment=seg,
                    sequence=seq,
                    manifest=str(manifest),
                    manifest_sha256=digest,
                    probes=rows[visit],
                    cohort=ONE if visit in held else GUARD,
                )
            )
        all_cases[ident] = dict(producer=cfg["producer"], rows=items)
        print(ident, "held", held, "guard", stress, flush=True)
    paths = (
        prior_input,
        batch_input,
        *ledgers.values(),
        Path(__file__),
        Path(fine_batch.__file__),
        Path(fine_search.__file__),
        Path(prior.__file__),
        REPORT / "PROTOCOL.md",
    )
    work.mkdir()
    save_json(
        work / "input-lock.json",
        dict(
            cases=all_cases,
            libs=reference["libs"] | {"batch": fine["libs"]["batch"]},
            python_sha256=reference["python_sha256"],
            sources={str(p): _sha(p) for p in paths},
            repeats=REPEATS,
        ),
    )


@contextmanager
def profile(acquisition, detector, grid):
    evaluate = detector._evaluate_probe
    frames = fine_search.FRAME_BASE
    active = None
    rows = []
    logical = Counter()
    pass_number = 0

    def probe(*args, receiver_id, probe_index, **kwargs):
        nonlocal active, pass_number
        lane = receiver_id, probe_index
        active = (*lane, logical[lane])
        logical[lane] += 1
        pass_number = -1
        try:
            return evaluate(*args, receiver_id=receiver_id, probe_index=probe_index, **kwargs)
        finally:
            active = None

    def coarse(*args):
        nonlocal pass_number
        pass_number += 1
        started = process_time_ns()
        reply = coarse_original(*args)
        rows.append(
            dict(
                kind="coarse",
                lane=active,
                pass_number=pass_number,
                anchors=len(args[-2]),
                cpu_ns=process_time_ns() - started,
            )
        )
        return reply

    def leaf(port, func):
        def measured(values, template, rate, epoch, freq, *args, **kwargs):
            if active is None:
                raise ValueError("refinement escaped its physical receiver")
            began = process_time_ns()
            result = func(values, template, rate, epoch, freq, *args, **kwargs)
            spent = process_time_ns() - began
            group = (float(freq),) if port == "verify" else freq
            if port == "conditioned":
                stop = len(template)
                reason = func.__self__.receipts[-1]["fallback"]
            else:
                stop = int(acquisition._pilot_sample_indexes(rate, args[0])[-1]) + 1
                reason = None
            rows.append(
                dict(
                    kind=port,
                    lane=active,
                    pass_number=pass_number,
                    epoch=int(epoch),
                    starts=(frames[epoch + frames + stop <= len(values)] + epoch).tolist(),
                    grid=list(group),
                    symbols=list(args[0]) if args else None,
                    template_sha256=sha256(memoryview(template).cast("B")).hexdigest(),
                    direct_reason=reason,
                    cpu_ns=spent,
                )
            )
            return result

        return measured

    coarse_original = grid.score_grid
    with (
        patch.object(detector, "_evaluate_probe", probe),
        patch.object(grid, "score_grid", coarse),
        patch.object(
            acquisition,
            "_normalized_frame_scores_fft",
            leaf("fine", acquisition._normalized_frame_scores_fft),
        ),
        patch.object(
            acquisition,
            "_conditioned_frame_scores",
            leaf("conditioned", acquisition._conditioned_frame_scores),
        ),
        patch.object(
            acquisition,
            "normalized_frame_score",
            leaf("verify", acquisition.normalized_frame_score),
        ),
    ):
        yield rows


def installed(work, name, cpu):
    from leo.analysis.starlink import acquisition
    from leo.scanner import fast_scan_detector as detector

    lock = read(work / "input-lock.json")
    cfg = lock["cases"][name]
    producer = cfg["producer"]
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError("worker outside assigned CPU")
    checked(prior.original.PYTHON, lock["python_sha256"])
    for p, h in (lock["sources"] | producer["sources"]).items():
        checked(Path(p), h)
    capture, policy, bound = prior.exact.lineage.source_lineage(_load_case(name))
    if (capture["edge"], bound["capture"]["root"], bound["capture"]["input_manifest_sha256"]) != (
        producer["edge"],
        producer["producer"],
        producer["input_manifest_sha256"],
    ):
        raise ValueError("installed original producer did not bind the fixture")
    libs = {k: checked(Path(v["path"]), v["sha256"]) for k, v in lock["libs"].items()}
    return acquisition, detector, cfg, policy, libs


def worker(work, name, cpu):
    acquisition, detector, cfg, policy, libs = installed(work, name, cpu)
    port = fine_batch.FineBatch(libs["batch"], acquisition)
    if not port.compatible:
        raise ValueError("qualified fine FFT failed its arithmetic sentinel")
    grid = PersistentGrid(libs["prepared"])
    evidence = []
    try:
        with (
            prior.exact.refiners(libs),
            grid.route(acquisition, prior.capture_starts.screen_module()),
            patch.object(
                acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks
            ),
            port.route(),
        ):
            for fixture, window in prior.load_windows(cfg["rows"]):
                with profile(acquisition, detector, grid) as traces:
                    observed, timing = prior.prepared_hotpath_trial.sample(window, policy)
                if observed[1] != fixture["probes"]:
                    raise ValueError("profile did not reproduce its original signed factors")
                evidence.append(
                    dict(
                        visit=fixture["visit"],
                        cohort=fixture["cohort"],
                        iq_sha256=window.iq_sha256,
                        trace=traces,
                        timing=timing,
                        public=observed[0],
                        probes=observed[1],
                    )
                )
                print(name, fixture["visit"], fixture["cohort"], flush=True)
    finally:
        grid.clear_cache()
    result = dict(
        case=name, cpu=cpu, input_lock_sha256=_sha(work / "input-lock.json"), rows=evidence
    )
    write(work / f"{name}-profile.json.gz", gzip.compress(encoded(result), mtime=0))


def run(work, name, cpu, module=MODULE):
    producer = read(work / "input-lock.json")["cases"][name]["producer"]["producer"]
    env = os.environ | {"PYTHONPATH": f"{producer}:{ROOT}", "TMPDIR": str(work)}
    env.update(
        {
            k + "_NUM_THREADS": "1"
            for k in ("OMP", "OPENBLAS", "MKL", "NUMEXPR", "BLIS", "VECLIB_MAXIMUM")
        }
    )
    command = [
        "taskset",
        "-c",
        str(cpu),
        str(prior.original.PYTHON),
        "-u",
        "-m",
        module,
        "worker",
        str(work),
        name,
        str(cpu),
    ]
    subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=300)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker"))
    parser.add_argument("work", type=Path, nargs="?", default=WORK)
    parser.add_argument("case", choices=CASES, nargs="?")
    parser.add_argument("cpu", type=int, nargs="?")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    else:
        (run if args.action == "run" else worker)(args.work, args.case, args.cpu)
