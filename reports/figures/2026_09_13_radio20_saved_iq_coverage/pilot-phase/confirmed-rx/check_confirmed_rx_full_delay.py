"""Offline exhaustive delay/FFT-bin pilot ranking on retained scan windows."""

import hashlib, json, time
from pathlib import Path
import numpy as np

BASE = Path(__file__).parent
out = BASE / "confirmed-rx-full-delay-v1"
out.mkdir(exist_ok=False)
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
refs = np.fromfile(BASE / "direct-references.ci16", dtype="<i2").reshape(4, 3300, 4).astype(float)
assert (
    digest(BASE / "direct-references.ci16")
    == "78b50e1aea5c350889b0798fc691491299925932e496a918cd5fbd3b9bc4faf2"
)
ref = refs[0, :, 0] + 1j * refs[0, :, 1]
energy = np.vdot(ref, ref).real
results = []
for name, indices in [("live-scan64-30-confirmed-rx-v1", range(6)), ("live-scan64-30-v1", [3])]:
    root = BASE / name
    op = json.loads((root / "operator.json").read_text())
    path = root / "scan.iq.ci16"
    assert digest(path) == op["artifacts"][path.name]["sha256"]
    raw = np.fromfile(path, dtype="<i2").reshape(-1, 14000, 2)
    rows = [json.loads(line) for line in (root / "worker.jsonl").read_text().splitlines()]
    for index in indices:
        before = time.monotonic()
        iq = raw[index, :, 0].astype(float) + 1j * raw[index, :, 1]
        windows = np.lib.stride_tricks.sliding_window_view(iq, 3300)
        powers = np.empty(9999)
        bins = np.empty(9999, dtype=np.int64)
        for first in range(0, 9999, 128):
            last = min(first + 128, 9999)
            z = windows[22 + first : 22 + last]
            spectrum = abs(np.fft.fft(z * ref.conj(), 4096, axis=1)) ** 2
            maxima = spectrum.argmax(axis=1)
            denom = np.maximum(energy * np.sum(abs(z) ** 2, axis=1), 1)
            powers[first:last] = spectrum[np.arange(last - first), maxima] / denom
            bins[first:last] = maxima
        scan = next(r for r in rows if r["kind"] == "scan" and r["attempt"] == index + 1)
        order = next(
            r for r in rows if r["kind"] == "candidate_order" and r["attempt"] == index + 1
        )
        np.testing.assert_allclose(
            powers[[p[0] for p in scan["peaks"]]],
            order["single_pilot_power"],
            rtol=2e-12,
            atol=2e-14,
        )
        groups = []
        for first, last in [(0, 3333), (3333, 6666), (6666, 9999)]:
            winner = first + int(powers[first:last].argmax())
            z = windows[22 + winner]
            direct = abs(
                np.vdot(ref, z * np.exp(-2j * np.pi * bins[winner] * np.arange(3300) / 4096))
            ) ** 2 / max(float(energy * np.vdot(z, z).real), 1)
            np.testing.assert_allclose(powers[winner], direct, rtol=2e-10, atol=2e-14)
            groups.append(dict(epoch=winner, bin=int(bins[winner]), power=float(powers[winner])))
        label = f"{name}-attempt{index + 1}"
        array = out / f"{label}.npz"
        np.savez(array, powers=powers, bins=bins)
        result = dict(
            source=name,
            attempt=index + 1,
            source_sha256=digest(path),
            scan_offset_samples=index * 14000,
            delay_count=9999,
            fft_bins=4096,
            shortlist_scores_checked=len(scan["peaks"]),
            group_maxima=groups,
            shortlist_maximum=max(order["single_pilot_power"]),
            host_seconds=time.monotonic() - before,
            surface_sha256=digest(array),
        )
        results.append(result)
        print(label, groups, flush=True)
result = dict(
    scope="offline_exhaustive_first_three_period_delay_and_frequency_ranking",
    new_rf_samples=0,
    arm_cost_measured=False,
    physical_tracking_qualified=False,
    acceptance_gates_changed=False,
    reference_phase=0,
    script_sha256=digest(Path(__file__)),
    cases=results,
)
with (out / "result.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
