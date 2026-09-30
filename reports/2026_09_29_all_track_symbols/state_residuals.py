"""Late-fitted known-state subtraction, including shared-subtraction controls."""

import hashlib
import json
from pathlib import Path

import numpy as np
from decode_tracks import SEED, codebook, slots

BASE = Path(__file__).parent
ATLAS = BASE.parent / "2026_09_28_sequence_semantics/local/ten-msps-atlas"


def fit_gain(z, prediction, start=224, stop=256, per_carrier=False):
    """OFDM 226–257 only; no early-symbol measurements enter this fit."""
    p = prediction[:, start:stop]
    axes = 1 if per_carrier else (1, 2)
    return np.sum(p.conj() * z[:, start:stop], axis=axes) / np.sum(abs(p) ** 2, axis=axes)


def expand(gain):
    return gain[:, None, :] if gain.ndim == 2 else gain[:, None, None]


def shared(a, b):
    a, b = a - a.mean(axis=0), b - b.mean(axis=0)
    return float(np.vdot(a, b).real / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-12))


def assess(a, b, prediction, ga, gb, start, stop):
    x, y, p = a[:, start:stop], b[:, start:stop], prediction[:, start:stop]
    ra, rb = x - expand(ga) * p, y - expand(gb) * p
    controls = []
    for shift in range(1, len(x)):
        # Both sides subtract the same target-frame pattern. This deliberately
        # preserves correlation that subtraction alone can manufacture.
        null = np.roll(y, shift, axis=0) - expand(np.roll(gb, shift, axis=0)) * p
        controls.append(shared(ra, null))
    return dict(
        first_symbol=start + 2,
        last_symbol=stop + 1,
        raw_shared=shared(x, y),
        residual_shared=shared(ra, rb),
        residual_control_mean=float(np.mean(controls)),
        residual_control_max=float(np.max(controls)),
        removed_energy_fraction=[
            float(1 - np.sum(abs(r) ** 2) / np.sum(abs(z) ** 2)) for r, z in [(ra, x), (rb, y)]
        ],
    )


def main():
    source = ATLAS / "atlas.json"
    atlas = json.loads(source.read_text())
    out = BASE / "local/state-residuals"
    out.mkdir(exist_ok=True)
    words = np.array([[1 if b == "1" else -1 for b in w] for w in codebook(list(map(int, SEED)))])
    result = dict(
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        atlas_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        visits=[],
    )
    for visit in atlas["visits"]:
        path = ATLAS / f"{visit['name']}.npz"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == visit["cache_sha256"]
        data = np.load(path)
        metadata = [json.loads(str(data[f"metadata{rx}"])) for rx in range(2)]
        bins = np.intersect1d(data["bins0"], data["bins1"])
        bins = bins[
            ~np.isin(bins, np.union1d(metadata[0]["pilot_bins"], metadata[1]["pilot_bins"]))
        ]
        phase_by_frame = {
            w["frame"]: w["phase_hypothesis"]
            for w in visit["windows"]
            if w["first_symbol"] == 194 and w["label"] == 1
        }
        frames = [f for f in visit["qualified_frames"] if f in phase_by_frame]
        phases = np.array([phase_by_frame[f] for f in frames])
        prediction = words[phases][:, slots(bins, np.arange(2, 302))]
        a, b = [
            data[f"z{rx}"][frames][:, :, np.searchsorted(data[f"bins{rx}"], bins)]
            for rx in range(2)
        ]
        ga, gb = fit_gain(a, prediction), fit_gain(b, prediction)
        regions = [
            assess(a, b, prediction, ga, gb, start, stop)
            for start, stop in [(0, 6), (6, 32), (32, 128), (128, 192), (256, 288)]
        ]
        np.savez_compressed(
            out / f"{visit['name']}.npz",
            frames=frames,
            bins=bins,
            phases=phases,
            gain0=ga,
            gain1=gb,
            residual0=a - ga[:, None, None] * prediction,
            residual1=b - gb[:, None, None] * prediction,
        )
        ga_carrier = fit_gain(a, prediction, per_carrier=True)
        gb_carrier = fit_gain(b, prediction, per_carrier=True)
        carrier_regions = [
            assess(a, b, prediction, ga_carrier, gb_carrier, start, stop)
            for start, stop in [(0, 6), (6, 32), (32, 128), (128, 192), (256, 288)]
        ]
        np.savez_compressed(
            out / f"{visit['name']}-per-carrier.npz",
            frames=frames,
            bins=bins,
            phases=phases,
            gain0=ga_carrier,
            gain1=gb_carrier,
            residual0=a - expand(ga_carrier) * prediction,
            residual1=b - expand(gb_carrier) * prediction,
        )
        result["visits"].append(
            dict(
                name=visit["name"],
                frames=len(frames),
                regions=regions,
                per_carrier_regions=carrier_regions,
            )
        )
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
