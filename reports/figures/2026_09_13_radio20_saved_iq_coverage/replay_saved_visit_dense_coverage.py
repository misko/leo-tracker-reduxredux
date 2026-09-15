"""Bounded offline coverage experiment using the unchanged C coarse scanner."""

import ctypes as C
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from tests.starlink_glrt.test_cpu_coarse import Workspace, POLL

BASE = Path(__file__).parent
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
lib = C.CDLL(str(BASE / "saved-visit-coarse-replay.so"))
lib.glrt_cpu_coarse_search.argtypes = [
    C.POINTER(Workspace),
    C.c_void_p,
    C.c_void_p,
    POLL,
    C.c_void_p,
]
deadline = time.monotonic() + 180
poll = POLL(lambda _: int(time.monotonic() > deadline))
bank = np.fromfile(BASE / "coarse-bank.ci16", dtype="<i2").reshape(12, 11, 11, 2)
refs = np.fromfile(BASE / "direct-references.ci16", dtype="<i2").reshape(4, 3300, 4)
ref = refs[0, :, 0].astype(float) + 1j * refs[0, :, 1]
energy = np.vdot(ref, ref).real
result = dict(
    scope="offline_scanner_temporal_coverage_experiment",
    new_rf_samples=0,
    acceptance_gates_changed=False,
    acquisitions_qualified=False,
    cases={},
    source_sha256=digest(Path(__file__)),
    scanner_binary_sha256=digest(BASE / "saved-visit-coarse-replay.so"),
    scanner_source_sha256=digest(
        Path("/home/mouse9911/gits/plutosdr-fw-radio20-tracking/tools/glrt_cpu_coarse.c")
    ),
    reference_sha256=digest(BASE / "direct-references.ci16"),
    bank_sha256=digest(BASE / "coarse-bank.ci16"),
)
paths = {"60_CH3": BASE / "two-frequency-visits60-v3/visit-0"}
for label in [*paths, "positive", "control"]:
    old = {}
    if label in paths:
        root = paths[label]
        path = root / "iq.ci16"
        prior = json.loads((root / "independent-visit-review.json").read_text())
        origin = prior["coarse_origin"]
        rows = [json.loads(line) for line in (root / "worker.jsonl").read_text().splitlines()]
        grids = np.fromfile(root / "grids.u32", dtype="<u4").reshape(-1, 11, 3333)
        scans = [r for r in rows if r["kind"] == "scan"]
        orders = [r for r in rows if r["kind"] == "candidate_order"]
        for i, (s, o) in enumerate(zip(scans, orders, strict=True)):
            old[s["window_start"] - origin] = (grids[i], o["single_pilot_power"])
        expected = prior["sha256"]["iq.ci16"]
    else:
        path = BASE / f"paced-original-seed-input-v1/{label}.ci16"
        expected = {
            "positive": "af991e03e69271c253d2fe6b5aeff110c9da5d5bd6ddda8c6850584f9e97b1c4",
            "control": "5b945b575fbff519de733ded2418b2f82110458ff52237e2a3126d8d7a53d5b9",
        }[label]
    assert digest(path) == expected
    iq = np.memmap(path, mode="r", dtype="<i2").reshape(-1, 2)
    positions = sorted(
        set(
            range(0, len(iq) - 14000 + 1, 14000)
            if label == "60_CH3"
            else np.linspace(0, len(iq) - 14000, 48, dtype=int).tolist()
        )
        | set(old)
    )
    measurements = []
    for at in positions:
        w = Workspace()
        x = np.ascontiguousarray(iq[at : at + 14000])
        assert (
            lib.glrt_cpu_coarse_search(C.byref(w), x.ctypes.data, bank.ctypes.data, poll, None) == 0
        )
        scores = []
        for peak in w.peaks[: w.count]:
            start = peak.epoch + 22
            y = x[start : start + 3300].astype(float)
            z = y[:, 0] + 1j * y[:, 1]
            scores.append(
                float(
                    np.max(abs(np.fft.fft(z * np.conj(ref), 16384)) ** 2)
                    / max(np.vdot(z, z).real * energy, 1)
                )
            )
        if at in old:
            np.testing.assert_array_equal(np.ctypeslib.as_array(w.grid), old[at][0])
            np.testing.assert_allclose(scores, old[at][1], rtol=2e-12, atol=2e-14)
        measurements.append(
            dict(
                offset=at,
                seconds=at / 2500000,
                previously_scanned=at in old,
                maximum_rank_power=max(scores),
                scores=scores,
            )
        )
    result["cases"][label] = dict(
        iq_sha256=expected,
        complex_samples=len(iq),
        prior_scans_reproduced=len(old),
        windows=len(measurements),
        maximum_rank_power=max(r["maximum_rank_power"] for r in measurements),
        measurements=measurements,
    )
    print(
        json.dumps(
            {
                "case": label,
                "windows": len(measurements),
                "max_rank": result["cases"][label]["maximum_rank_power"],
            }
        ),
        flush=True,
    )
result["elapsed_seconds"] = time.monotonic() - (deadline - 180)
with (BASE / "saved-visit-dense-coverage-v1.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
