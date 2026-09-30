"""Repeat late residual assay on independently bound paired visit caches."""

import hashlib
import json
from pathlib import Path

import numpy as np
from decode_tracks import SEED, codebook, slots
from state_residuals import assess, fit_gain
from ten_msps_atlas import classify

BASE = Path(__file__).parent
SOURCE = BASE.parent / "2026_09_28_sequence_semantics/local"


def plane_stats(a, b):
    rows = {}
    for name, x, y in [("real", a.real, b.real), ("imag", a.imag, b.imag)]:
        x, y = x - x.mean(axis=0), y - y.mean(axis=0)
        correlation = float(np.vdot(x, y) / max(np.linalg.norm(x) * np.linalg.norm(y), 1e-12))
        sign = float(np.mean((x >= 0) == (y >= 0)))
        controls = [
            float(np.mean((x >= 0) == (np.roll(y, k, axis=0) >= 0))) for k in range(1, len(x))
        ]
        rows[name] = dict(
            correlation=correlation,
            centered_sign_agreement=sign,
            control_sign_mean=float(np.mean(controls)),
            control_sign_max=float(np.max(controls)),
        )
    return rows


def main():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = BASE / "local/residual-constellation"
    out.mkdir(exist_ok=True)
    words = np.array([[1 if b == "1" else -1 for b in w] for w in codebook(list(map(int, SEED)))])
    rng = np.random.default_rng(20260929)
    result = dict(method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), visits=[])
    fig, axes = plt.subplots(2, 2, figsize=(10, 8), layout="constrained")
    for vi, name in enumerate(["DS9-middle", "DS9-last"]):
        path = SOURCE / f"{name}-soft.npz"
        inventory = SOURCE / f"ds9-{name[4:]}-10m/inventory.json"
        data = np.load(path)
        digest = hashlib.sha256(inventory.read_bytes()).hexdigest()
        assert str(data["inventory_sha256"]) == digest
        meta = [json.loads(str(data[f"metadata{rx}"])) for rx in range(2)]
        bins = np.intersect1d(data["bins0"], data["bins1"])
        bins = bins[~np.isin(bins, np.union1d(meta[0]["pilot_bins"], meta[1]["pilot_bins"]))]
        a, b = [data[f"z{rx}"][:, :, np.searchsorted(data[f"bins{rx}"], bins)] for rx in range(2)]
        frames, phases = [], []
        for f in sorted(set(meta[0]["evaluation_frames"]) & set(meta[1]["evaluation_frames"])):
            if min(m["diagnostics"][f]["held_pilot_coherence"] for m in meta) <= 0.5:
                continue
            check = classify(
                a[f, 192:224], b[f, 192:224], slots(bins, np.arange(194, 226)), words, rng
            )
            if check["label"] == 1:
                frames.append(f)
                phases.append(check["phase_hypothesis"])
        assert len(frames) >= 10
        a, b = a[frames], b[frames]
        p = words[phases][:, slots(bins, np.arange(2, 302))]
        ga, gb = fit_gain(a, p), fit_gain(b, p)
        ra, rb = a - ga[:, None, None] * p, b - gb[:, None, None] * p
        item = dict(
            name=name,
            frames=len(frames),
            carriers=len(bins),
            source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            inventory_sha256=digest,
            late=assess(a, b, p, ga, gb, 256, 288),
            planes=plane_stats(ra[:, 256:288], rb[:, 256:288]),
        )
        result["visits"].append(item)
        np.savez_compressed(
            out / f"{name}.npz",
            frames=frames,
            phases=phases,
            bins=bins,
            gain0=ga,
            gain1=gb,
            residual0=ra,
            residual1=rb,
        )
        for rx, z in enumerate([ra, rb]):
            z = z[:, 256:288].ravel()
            scale = np.sqrt(np.mean(abs(z) ** 2))
            z = z / scale
            limit = float(np.quantile(np.maximum(abs(z.real), abs(z.imag)), 0.99))
            axes[vi, rx].hist2d(
                z.real, z.imag, bins=80, range=[[-limit, limit], [-limit, limit]], cmap="magma"
            )
            axes[vi, rx].set(
                title=f"{name} RX{rx}: {len(frames)} frames",
                xlabel="Residual real / RMS",
                ylabel="Residual imaginary / RMS",
                aspect="equal",
            )
    fig.suptitle(
        "Held symbols 258–289; late-fitted known-state subtraction\n"
        "Density view clips outer 1%; no constellation classes assumed"
    )
    fig.savefig(out / "constellations.png", dpi=150)
    plt.close(fig)
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
