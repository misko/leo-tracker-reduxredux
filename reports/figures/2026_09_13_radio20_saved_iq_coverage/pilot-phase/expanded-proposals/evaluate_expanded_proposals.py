"""Compare candidate budgets and same-frequency repeated-pilot ranking offline."""

import ctypes as c
import json
from pathlib import Path
import time
import numpy as np
from tests.starlink_glrt.test_cpu_coarse import integer_grid, bank, Workspace, POLL
from diagnose_live_observer3_alignment import BASE, digest


def select(grid, limit):
    local = []
    for f in range(11):
        for e in range(3333):
            p = int(grid[f, e])
            left = int(grid[f, e - 1]) if e else 0
            right = int(grid[f, e + 1]) if e < 3332 else 0
            if p and p >= left and p >= right and not p == left == right:
                local.append((e, f, p))
    local.sort(key=lambda r: (-r[2], abs(r[1] - 5), r[0], r[1]))
    selected = []
    for row in local:
        if any(
            min(abs(row[0] - r[0]), 3333 - abs(row[0] - r[0])) < 20 and abs(row[1] - r[1]) <= 1
            for r in selected
        ):
            continue
        selected.append(row)
        if len(selected) == limit:
            break
    return selected


def main():
    source = BASE / "combined-pilot-controls-v1/result.json"
    manifest = json.loads(source.read_text())
    refs = (
        np.fromfile(BASE / "direct-references.ci16", dtype="<i2").reshape(4, 3300, 4).astype(float)
    )
    ref = refs[0, :, 0] + 1j * refs[0, :, 1]
    energy = np.vdot(ref, ref).real
    lib = c.CDLL(str(BASE / "saved-visit-coarse-replay.so"))
    lib.glrt_cpu_coarse_select.argtypes = [c.POINTER(Workspace), POLL, c.c_void_p]
    poll = POLL(lambda _: 0)
    result = dict(
        scope="expanded_coarse_candidates_single_and_four_pilot_ranking",
        new_rf_samples=0,
        acceptance_gates_changed=False,
        acquisition_qualified=False,
        arm_cost_measured=False,
        budgets=[8, 32, 64, 128, 256],
        source_sha256=digest(Path(__file__)),
        input_manifest_sha256=digest(source),
        cases=[],
    )
    started = time.monotonic()
    for case in manifest["cases"]:
        path = BASE / "combined-pilot-controls-v1" / f"{case['label']}-{case['number']}" / "iq.ci16"
        assert digest(path) == case["input_sha256"]
        raw = np.fromfile(path, dtype="<i2").reshape(-1, 2)
        grid = integer_grid(raw[:14000], bank()).astype("<u4")
        peaks = select(grid, 256)
        work = Workspace()
        c.memmove(c.addressof(work.grid), grid.ctypes.data, grid.nbytes)
        work.completed_epochs = 3333
        assert lib.glrt_cpu_coarse_select(c.byref(work), poll, None) == 0
        assert peaks[:8] == [(r.epoch, r.frequency, r.score) for r in work.peaks]
        iq = raw[:, 0].astype(float) + 1j * raw[:, 1]
        scores = []
        for e, f, p in peaks:
            spectra = []
            for shift in (0, 3333, 6667, 10000):
                z = iq[e + 22 + shift : e + 22 + shift + 3300]
                assert len(z) == 3300
                spectra.append(
                    abs(np.fft.fft(z * ref.conj(), 16384)) ** 2
                    / max(energy * np.vdot(z, z).real, 1)
                )
            joint = np.mean(spectra, axis=0)
            scores.append(
                dict(
                    epoch=e,
                    frequency=f,
                    coarse_score=p,
                    single=float(max(spectra[0])),
                    four=float(max(joint)),
                    four_cfo_bin=int(np.argmax(joint)),
                )
            )
        single = [r["single"] for r in scores]
        four = [r["four"] for r in scores]
        np.testing.assert_allclose(
            max(single[:8]), case["proposal"]["rank_power"], rtol=2e-12, atol=2e-14
        )
        assert int(np.argmax(single[:8])) == case["proposal"]["selected"]
        budgets = []
        for n in result["budgets"]:
            a = int(np.argmax(single[:n]))
            b = int(np.argmax(four[:n]))
            budgets.append(
                dict(
                    budget=n,
                    single_winner=a + 1,
                    single=scores[a],
                    four_winner=b + 1,
                    four=scores[b],
                )
            )
        result["cases"].append(
            dict(label=case["label"], number=case["number"], budgets=budgets, scores=scores)
        )
        print(
            case["label"],
            case["number"],
            [
                (r["budget"], round(r["single"]["single"], 4), round(r["four"]["four"], 4))
                for r in budgets
            ],
            flush=True,
        )
    result["host_elapsed_seconds"] = time.monotonic() - started
    with (BASE / "expanded-proposal-ranking-v1.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
