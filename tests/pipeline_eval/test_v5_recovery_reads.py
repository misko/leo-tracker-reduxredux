import gzip
import json
from pathlib import Path

import numpy as np

from tools.pipeline_eval.__main__ import read_predictions
from tools.pipeline_eval.qualification.full_v5_check import _sha
from tools.pipeline_eval.variants import v5_recovery_reads as tiled


class Rows:
    def __init__(self, values):
        self.values = values
        self.shape = values.shape
        self.reads = []

    def __getitem__(self, item):
        self.reads.append(item)
        return self.values[item]


def banks():
    n = 2 * tiled.BLOCK + 3
    p = np.arange(n, dtype=float).reshape(n, 1, 1)
    v = np.mod(p, 7)
    dense = dict(time_s=np.arange(8), position_km=p, velocity_km_s=v)
    counted = dict(dense, position_km=Rows(p), velocity_km_s=Rows(v))
    return dense, counted


def project(bank, time, positions, *, phase_seconds):
    p = bank["position_km"][:, 0]
    v = bank["velocity_km_s"][:, 0]
    return [
        (p + v * time + phase_seconds + receiver, p - time - phase_seconds)
        for receiver in positions
    ]


def profile(y, f, t, **_):
    raw = y - f
    adjusted = raw - np.rint(raw.mean(axis=1) / 13)[:, None] * 13
    return {"cost": (adjusted * adjusted).sum(axis=1) + (adjusted @ t) ** 2}


def test_residual_tiles_preserve_phase_fold_minima_and_read_each_state_once():
    dense, bank = banks()
    phases = [-30, -15, 0, 15, 30]
    arms = ("c0", "fitted_c")
    times = np.arange(12, dtype=float)
    query = np.array([2, 3, 5, 7, 9, 11])
    columns = {"full": np.array([0, 1, 2, 4, 5]), "held": np.array([1, 3, 4])}
    folds = [(name, None, None) for name in columns]
    positions = (2.0, 10.0)
    measured = {a: times * k + 7 for k, a in enumerate(arms, 1)}
    scale = 2.0
    shape = dense["position_km"].shape[0]

    def minima():
        return {
            a: {(b, s): np.full(shape, np.inf) for b in (15, 30) for s in columns} for a in arms
        }

    def select(data, t, mask, xy, **options):
        return project(data, t[mask], xy, **options)

    want, got = minima(), minima()
    for phase in phases:
        grids = select(dense, times, query, positions, phase_seconds=phase)
        for a, (f, e) in zip(arms, grids, strict=True):
            f *= scale
            for s, c in columns.items():
                ix = query[c]
                cost = profile(measured[a][ix], f[:, c], times[ix])["cost"] + (phase / 5) ** 2
                cost = np.where(e[:, c].min(axis=1) >= 0, cost, np.inf)
                for b in (15, 30):
                    if abs(phase) <= b:
                        want[a][b, s] = np.minimum(want[a][b, s], cost)
    tiled.residual_blocks(
        select,
        profile,
        bank,
        phases,
        times,
        query,
        positions,
        arms,
        measured,
        folds,
        columns,
        scale,
        got,
    )
    for a in arms:
        for key in want[a]:
            np.testing.assert_array_equal(got[a][key], want[a][key])
    assert len(bank["position_km"].reads) == len(bank["velocity_km_s"].reads) == 3


def test_reassociation_tiles_preserve_global_minima_and_ties():
    dense, bank = banks()
    phases = [-30, 0, 30]
    arms = ("c0", "fitted_c")
    times = np.arange(4, dtype=float)
    scale = np.array([0.75, 1.0, 1.0, 0.5])
    measured = {a: times * k + 7 for k, a in enumerate(arms, 1)}
    positions = (31.0, 32.0)
    want = {a: np.full(dense["position_km"].shape[0], np.inf) for a in arms}
    got = {a: value.copy() for a, value in want.items()}
    for phase in phases:
        grids = project(dense, times, positions, phase_seconds=phase)
        for a, (f, e) in zip(arms, grids, strict=True):
            cost = profile(measured[a], f * scale, times)["cost"] + (phase / 5) ** 2
            want[a] = np.minimum(want[a], np.where(e.min(axis=1) >= 0, cost, np.inf))
    tiled.reassociation_blocks(
        project,
        profile,
        bank,
        phases,
        times,
        positions,
        arms,
        measured,
        scale,
        got,
    )
    for a in arms:
        np.testing.assert_array_equal(got[a], want[a])
        np.testing.assert_array_equal(np.argsort(got[a]), np.argsort(want[a]))
    assert bank["position_km"].reads == bank["velocity_km_s"].reads
    assert len(bank["position_km"].reads) == 3


def test_packaged_cap_observation_binds_completed_exact_geographic_run():
    folder = (
        Path(__file__).resolve().parents[2]
        / "reports/2026_11_19_receiver_screening/deployment/recovery-reads"
    )
    proof = json.loads((folder / "cap-observation.json").read_bytes())
    assert all(_sha(folder / name) == sha for name, sha in proof["files"].items())
    samples = gzip.decompress((folder / "cap-physical-samples.jsonl.gz").read_bytes()).splitlines()
    assert len(samples) == proof["samples"] == 14
    for item in map(json.loads, samples):
        assert item["group"].endswith(f"/{proof['unit']}.service")
        assert item["memory.max"] == str(512 * 1024**2)
        assert item["memory.swap.max"] == item["memory.swap.current"] == "0"
    assert proof["last_observed_memory_events"]["oom_kill"] == 0
    case = "DS29-0082"
    free = read_predictions(folder / "uncapped-positions.jsonl.gz")[case]
    capped = read_predictions(folder / "capped-positions.jsonl.gz")[case]
    assert capped["result"]["status"] == "ok"
    assert capped["input_sha256"] == free["input_sha256"]
    assert capped["result"]["arms"] == free["result"]["arms"]
    accounting = capped["result"]["metrics"]["recovery_reads"]
    sweeps = accounting["sweeps"]
    assert sum(row["state_bytes"] for row in sweeps) == 1_022_756_400
    assert sum(row["phase_major_state_bytes"] for row in sweeps) == 32_932_756_080
