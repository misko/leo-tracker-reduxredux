"""Test tail-derived per-frame/carrier phase corrections without fitting header bits."""

import hashlib
import json
from pathlib import Path

import numpy as np
from local_header_recovery import select_positions
from region_phase_audit import WORDS

BASE = Path(__file__).resolve().parent


def phase_gain(values, signs):
    return np.exp(-1j * np.angle(np.mean(values * signs, axis=1)))


def main():
    physical = [
        int(k)
        for k in np.argsort(np.fft.fftfreq(1024))
        if 2 <= k < 1022 and k not in range(488, 496) and k not in range(528, 536)
    ]
    compact = {b: i for i, b in enumerate(physical)}
    rows = []
    for tag in ("middle", "last"):
        source = BASE / f"local/DS9-{tag}-soft.npz"
        word_path = BASE / (
            "local/ds9_word_audit.json" if tag == "middle" else "local/ds9_last_word_audit.json"
        )
        archive = np.load(source)
        bins = archive["bins0"]
        assert np.array_equal(bins, archive["bins1"])
        phase = {}
        for r in json.loads(word_path.read_text())["rows"]:
            if r["accepted"] and r["phase"] is not None and r["last_symbol"] < 242:
                assert r["frame"] not in phase or phase[r["frame"]] == r["phase"]
                phase[r["frame"]] = r["phase"]
        frames = sorted(phase)
        split = len(frames) // 2
        train, held = frames[:split], frames[split:]
        symbols = np.arange(242, 302)
        slots = (np.array([compact[int(b)] for b in bins])[None, :] - 16 * symbols[:, None]) % 60
        expected = WORDS[np.array([phase[f] for f in held])[:, None, None], slots[None]]
        streams = [archive[f"z{rx}"][held] for rx in range(2)]
        corrections = [phase_gain(z[:, 240:270], expected[:, :30]) for z in streams]
        tail = []
        for z, c in zip(streams, corrections, strict=True):
            before = z[:, 270:300]
            after = before * c[:, None, :]
            truth = expected[:, 30:] > 0
            tail.append(
                dict(
                    count=int(truth.size),
                    errors_before=int(((before.real >= 0) != truth).sum()),
                    errors_after=int(((after.real >= 0) != truth).sum()),
                    median_abs_rotation_degrees=float(np.median(abs(np.angle(c))) * 180 / np.pi),
                )
            )
        variable, threshold = select_positions(archive["z0"][train, :6])
        x, y = [z[:, :6] for z in streams]
        keep = variable[None] & (abs(x.real) / np.maximum(abs(x), 1e-20) >= threshold[None])
        corrected = [z[:, :6] * c[:, None, :] for z, c in zip(streams, corrections, strict=True)]
        header = dict(
            count=int(keep.sum()),
            original_agreement=float(((x.real >= 0) == (y.real >= 0))[keep].mean()),
            both_corrected_agreement=float(
                ((corrected[0].real >= 0) == (corrected[1].real >= 0))[keep].mean()
            ),
            rx0_only_agreement=float(((corrected[0].real >= 0) == (y.real >= 0))[keep].mean()),
            rx1_only_agreement=float(((x.real >= 0) == (corrected[1].real >= 0))[keep].mean()),
        )
        row = dict(
            tag=tag,
            discovery_frames=train,
            evaluation_frames=held,
            tail=tail,
            header=header,
            input_sha256={
                str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, word_path)
            },
        )
        rows.append(row)
        print(json.dumps(dict(tag=tag, tail=tail, header=header), indent=2))
    output = dict(
        rows=rows,
        limitation="Per-frame gain fit only symbols242–271 using "
        "previously paired recovered phase from windows ending before242. "
        "Tail272–301 and header2–7 not fitted. Header mask frozen from original "
        "RX0 discovery signs; opposite receiver is noisy validation, not truth. "
        "Paired word selection is shared context, not independent receivers in "
        "every processing stage. No corrected data written to native caches.",
    )
    (BASE / "local/ds9_tail_phase_transfer.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
