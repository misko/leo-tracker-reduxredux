"""Exploratory held-out power combination after actual C proposal selection.

Small, contiguous saved-control corpus; this is not rare-false-alarm calibration.
Training uses frames 0,9,18,27; scoring uses 36,45,54,63, with no held-out search.
"""

import json
import subprocess
from pathlib import Path
import numpy as np
from scipy.signal import zoom_fft
from diagnose_live_observer3_alignment import BASE, RATE, digest


def evaluate(iq, first, cfo, refs):
    frames = np.arange(8) * 9
    grid = np.linspace(cfo - 1000, cfo + 1000, 401)
    trained = []
    for frame in frames[:4]:
        at = first + int(frame) * 10000 // 3
        z = iq[at + 32 : at + 3268]
        assert len(z) == 3236
        best = None
        for quarter in range(-64, 65):
            whole, phase = divmod(quarter, 4)
            ref = refs[phase, 32 - whole : 3268 - whole]
            values = zoom_fft(z * ref.conj(), [grid[0], grid[-1]], 401, fs=RATE, endpoint=True)
            k = int(np.argmax(abs(values)))
            power = float(abs(values[k]) ** 2 / (np.vdot(z, z).real * np.vdot(ref, ref).real))
            row = dict(
                frame=int(frame), offset_quarters=quarter, cfo_hz=float(grid[k]), power=power
            )
            if best is None or power > best["power"]:
                best = row
        trained.append(best)
    timing = np.polyfit(frames[:4], [r["offset_quarters"] / 4 for r in trained], 1)
    carrier = np.polyfit(frames[:4], [r["cfo_hz"] for r in trained], 1)
    held = []
    for frame in frames[4:]:
        at = first + int(frame) * 10000 // 3
        quarter = round(float(np.polyval(timing, frame)) * 4)
        whole, phase = divmod(quarter, 4)
        if 32 - whole < 0 or 3268 - whole > 3300:
            return dict(training=trained, score=None, reason="reference_extent_exceeded")
        z = iq[at + 32 : at + 3268]
        ref = refs[phase, 32 - whole : 3268 - whole]
        frequency = float(np.polyval(carrier, frame))
        dot = np.vdot(ref, z * np.exp(-2j * np.pi * frequency * np.arange(3236) / RATE))
        power = float(abs(dot) ** 2 / (np.vdot(z, z).real * np.vdot(ref, ref).real))
        held.append(dict(frame=int(frame), offset_quarters=quarter, cfo_hz=frequency, power=power))
    return dict(
        training=trained,
        heldout=held,
        score=float(np.mean([r["power"] for r in held])),
        minimum_heldout_power=min(r["power"] for r in held),
        reason="evaluated",
    )


def main():
    old = json.loads((BASE / "missed-candidate-replay-v1/result.json").read_text())
    binary = BASE / "missed-candidate-replay-v1/bench"
    assert digest(binary) == old["binary_sha256"]
    raw = (
        np.fromfile(BASE / "direct-references.ci16", dtype="<i2").reshape(4, 3300, 4).astype(float)
    )
    assert (
        digest(BASE / "direct-references.ci16")
        == "78b50e1aea5c350889b0798fc691491299925932e496a918cd5fbd3b9bc4faf2"
    )
    refs = raw[:, :, 0] + 1j * raw[:, :, 1]
    manifest = json.loads((BASE / "paced-original-seed-input-v1/manifest.json").read_text())
    out = BASE / "combined-pilot-controls-v1"
    out.mkdir(exist_ok=False)
    result = dict(
        scope="same_C_selected_proposal_four_training_four_heldout_mean_power",
        new_rf_samples=0,
        acceptance_gates_changed=False,
        false_alarm_calibrated=False,
        native_tracking_qualified=False,
        score_definition="arithmetic_mean_of_four_heldout_normalized_interior_powers",
        source_sha256=digest(Path(__file__)),
        bench_sha256=digest(binary),
        cases=[],
    )
    for label in ("positive", "control"):
        path = BASE / f"paced-original-seed-input-v1/{label}.ci16"
        assert digest(path) == manifest[label]["sha256"]
        raw = np.fromfile(path, dtype="<i2").reshape(-1, 2)
        # Full replay extents do not overlap. Do not treat these nearby cuts as independent RF realizations.
        for number, offset in enumerate(range(0, len(raw) - 447851 + 1, 447851)):
            root = out / f"{label}-{number}"
            root.mkdir()
            cut = raw[offset : offset + 447851]
            cut.tofile(root / "iq.ci16")
            run = subprocess.run(
                [
                    str(binary),
                    str(BASE / "coarse-bank.ci16"),
                    str(root / "iq.ci16"),
                    str(BASE / "direct-references.ci16"),
                ],
                capture_output=True,
                timeout=12,
            )
            (root / "stdout.jsonl").write_bytes(run.stdout)
            run.check_returncode()
            assert not run.stderr
            rows = [json.loads(line) for line in run.stdout.splitlines()]
            initial = next(r for r in rows if r["kind"] == 3)
            assert initial["frame"] == initial["reference_phase"] == 0
            frequency = next(r for r in rows if r["kind"] == 2)["cfo_hz"]
            z = cut[:, 0].astype(float) + 1j * cut[:, 1]
            scored = evaluate(z, initial["first"], frequency, refs)
            result["cases"].append(
                dict(
                    label=label,
                    number=number,
                    source_offset=offset,
                    source_sha256=manifest[label]["sha256"],
                    input_sha256=digest(root / "iq.ci16"),
                    journal_sha256=digest(root / "stdout.jsonl"),
                    proposal=rows[0],
                    first=initial["first"],
                    resolver_cfo_hz=frequency,
                    **scored,
                )
            )
            print(label, number, scored["score"], flush=True)
    with (out / "result.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
