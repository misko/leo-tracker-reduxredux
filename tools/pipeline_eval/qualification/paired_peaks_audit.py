"""Check alternative frequency modes and the cost of removing orbit nominations."""

import concurrent.futures
import os

from ..__main__ import save_json
from ..variants import paired_peaks as model
from . import paired_peaks_trial as trial


def full(job):
    q, cpu = job
    algorithms = trial.prior.sources()
    plan = trial.prior.read(trial.OUTPUT / "blind-plan.json")
    trial.WORKER = trial.WORKER.replace(
        "result, trace = solver.solve(capture,",
        "import numpy as np\n"
        "solver.nominations = lambda bank, lane, pair, phase: np.arange(len(bank.positions_km))\n"
        "result, trace = solver.solve(capture,",
    )
    out = trial.paired_attempt(q, cpu, algorithms, plan["frozen_pair_sha256"], True)
    return dict(out, scope="diagnostic_full_decoder_without_nomination_pruning")


def mode_check(q):
    capture = trial.load(q["recording"])
    streams, info = model.synchronized(capture, q["misalign"])
    frame = capture.sample_rate_hz / model.FRAME_RATE
    result = {}
    for band in (0, 1):
        points = []
        for (channel, _), values in streams.items():
            if int(channel > 4) != band:
                continue
            for visit, t, left, right in values:
                i, j, de, df = model.edges(left, right, frame)
                joint = (left[i, 3] > 0) & (right[j, 3] > 0)
                if joint.any():
                    points.append((t, visit, de[joint], df[joint]))
        fit = model.calibrate(points, capture.duration_s)
        training = [p for p in points if p[0] % 60 < 27]
        held = [p for p in points if p[0] % 60 >= 48]
        rival = 0
        far_mode = None
        if fit["supported"]:
            main, drift = fit["offset_hz"], fit["drift_hz_per_s"]
            mid = capture.duration_s / 2
            choices = {
                int(round(v / 500)) * 500
                for t, _, _, df in training
                for v in (model.stock.fold(df - drift * (t - mid)))
                if abs(model.stock.fold(v - main)) > 2200
            }
            for alternative in sorted(choices):
                hits = len(model.nearest(held, alternative, drift, mid))
                if hits > rival:
                    far_mode, rival = alternative, hits
        result[band] = dict(
            calibration=fit, alternative_offset_hz=far_mode, alternative_held_visits=rival
        )
    return dict(id=q["id"], metrics=info, bands=result)


def main():
    os.sched_setaffinity(0, set(trial.CPUS))
    seal = trial.prior.read(trial.OUTPUT / "prediction-lock.json")
    trial.prior.archive.base.secant_full._verify_files(trial.OUTPUT, seal["files"])
    jobs = trial.rows()
    with concurrent.futures.ProcessPoolExecutor(2) as pool:
        controls = list(pool.map(full, zip(jobs[:2], trial.CPUS, strict=True)))
    save_json(trial.OUTPUT / "unpruned-diagnostic.json", controls)
    os.nice(10)
    save_json(trial.OUTPUT / "mode-audit.json", [mode_check(q) for q in jobs])


if __name__ == "__main__":
    main()
