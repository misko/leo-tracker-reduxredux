"""Bounded offline UT header investigation; no runtime application dependencies."""

import argparse
import hashlib
import json
import platform
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.ndimage import uniform_filter1d
from scipy.optimize import minimize_scalar
from scipy.signal import correlate, resample_poly

FS = 240e6
N = 1024
NS = 1056


def pss():
    state = [0, 0, 1, 1, 0, 1, 0]
    bits = []
    for _ in range(127):
        bit = (state[2] + state[6]) % 2
        state = [bit] + state[:-1]
        bits.append(bit)
    segment = np.exp(-1j * np.pi / 4 - 0.5j * np.pi * np.cumsum(2 * np.array([0] + bits[::-1]) - 1))
    body = np.concatenate([-segment] + [segment] * 7)
    return np.r_[-body[-32:], body]


def acquire(x, replica):
    """Search CFO and delay inside a metadata-centered window; not blind capture search."""
    t = np.arange(len(x)) / FS

    def trial(f):
        c = correlate(x * np.exp(-2j * np.pi * f * t), replica, mode="valid", method="fft")
        k = int(np.argmax(abs(c)))
        return float(abs(c[k])), k

    grid = np.arange(-2e6, 2e6 + 1, 25000.0)
    scores = [trial(f)[0] for f in grid]
    f0 = grid[np.argmax(scores)]
    opt = minimize_scalar(lambda f: -trial(f)[0], bounds=(f0 - 25000, f0 + 25000), method="bounded")
    score, k = trial(opt.x)
    rho = score / np.sqrt(
        np.vdot(replica, replica).real
        * np.vdot(x[k : k + len(replica)], x[k : k + len(replica)]).real
    )
    return k, float(opt.x), float(rho)


def remove_blind_slope(y, freq, previous=0.0):
    """Fourth-power timing fit uses no payload/reference-template values."""
    unit = y / np.maximum(abs(y), 1e-12)
    z = unit**4

    def score(delay):
        return abs(np.mean(z * np.exp(-8j * np.pi * freq * delay)))

    grid = previous + np.linspace(-0.7, 0.7, 29)
    best = grid[np.argmax([score(d) for d in grid])]
    opt = minimize_scalar(lambda d: -score(d), bounds=(best - 0.05, best + 0.05), method="bounded")
    return y * np.exp(-2j * np.pi * freq * opt.x), float(opt.x), float(score(opt.x))


def bpsk_score(y, template):
    d = y * np.conj(template)
    unit = d / np.maximum(abs(d), 1e-12)
    return float(abs(np.mean(unit**2)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("docs/research/starlink-literature"))
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "local")
    parser.add_argument("--channel-smooth", type=int, default=9)
    parser.add_argument("--carrier-limit", type=float, default=0.42)
    args = parser.parse_args()
    if not 0 < args.carrier_limit <= 0.5:
        parser.error("--carrier-limit must be in (0, 0.5]")
    args.out.mkdir(parents=True, exist_ok=True)
    source = args.catalog / "local/data/ut-pilots"
    rawpath = source / "exemplar250-257/exemplar250-257.bin"
    refs = source / "supplement/reference-template"
    sss = loadmat(refs / "sssVec.mat")["sssVecFull"].ravel()
    rotations = loadmat(refs / "referenceTemplate.mat")["referenceTemplateRotations"]
    template = np.exp(0.5j * np.pi * rotations)
    sss_td = np.fft.ifft(sss) * 32
    replica = np.r_[pss(), sss_td[-32:], sss_td]
    raw = np.memmap(rawpath, dtype="<i2", mode="r").reshape(-1, 2)
    meta = json.loads((source / "exemplar250-257/sliceInfo.json").read_text())
    indices = np.arange(2, 1022)
    indices = indices[~np.isin(indices, np.r_[488:496, 528:536])]
    # Central, strong subcarriers used for header evidence; exclude noisy channel edges.
    indices = indices[abs(np.fft.fftfreq(N)[indices]) <= args.carrier_limit]
    freq = np.fft.fftfreq(N)[indices]
    results, arrays = [], []
    for frame_id, toa in zip(meta["frameSet"]["index"], meta["frameSet"]["toa_s"], strict=True):
        if toa + 302 * NS / FS > len(raw) / 250e6:
            continue
        start = round((toa - 10e-6) * 250e6)
        stop = start + round(1.35e-3 * 250e6)
        iq = raw[start:stop].astype(np.float64)
        x = resample_poly(iq[:, 0] + 1j * iq[:, 1], 24, 25)
        k, cfo, rho = acquire(x[: int(30e-6 * FS)], replica)
        x *= np.exp(-2j * np.pi * cfo * np.arange(len(x)) / FS)
        # FFT starts 16 samples before nominal useful interval, inside cyclic prefix.
        symbols = np.array(
            [np.fft.fft(x[k + i * NS + 16 : k + i * NS + 16 + N]) / 32 for i in range(1, 302)]
        )
        h = np.zeros(N, complex)
        loaded = abs(sss) > 0
        h[loaded] = symbols[0, loaded] / sss[loaded]
        h = uniform_filter1d(h.real, size=args.channel_smooth, mode="wrap") + 1j * uniform_filter1d(
            h.imag, size=args.channel_smooth, mode="wrap"
        )
        # Null-gutter interpolation affects only excluded bins.
        y = symbols[:, indices] / h[indices]
        rows = []
        deviations = []
        last_delay = 0.0
        for column in range(1, 301):
            corrected, delay, q4 = remove_blind_slope(y[column], freq, last_delay)
            last_delay = delay
            tr = template[indices, column]
            exact = bpsk_score(corrected, tr)
            controls = [bpsk_score(corrected, np.roll(tr, shift)) for shift in [7, 19, 43, 101]]
            temporal_control = bpsk_score(corrected, template[indices, (column + 17) % 301])
            d = corrected * np.conj(tr)
            # Axis alignment leaves a +/- ambiguity; these are NOT decoded header bytes.
            axis = 0.5 * np.angle(np.mean((d / np.maximum(abs(d), 1e-12)) ** 2))
            aligned = d * np.exp(-1j * axis)
            bits = np.sign(aligned.real)
            kmap = {int(v): j for j, v in enumerate(indices)}
            pairs = [(j, kmap[int(v + 60)]) for j, v in enumerate(indices) if int(v + 60) in kmap]
            lag60 = np.mean([bits[a] * bits[b] for a, b in pairs])
            rows.append(
                dict(
                    symbol=column + 1,
                    template_bpsk_score=exact,
                    rolled_control_max=max(controls),
                    temporal_control=temporal_control,
                    fourth_power_score=q4,
                    delay_samples=delay,
                    lag60_sign_correlation=float(lag60),
                )
            )
            deviations.append(aligned)
        result = dict(
            frame_id=frame_id,
            metadata_toa_s=toa,
            acquired_toa_s=start / 250e6 + k / FS,
            cfo_hz=cfo,
            sync_correlation=rho,
            symbols=rows,
        )
        results.append(result)
        arrays.append(np.array(deviations))
        print(
            frame_id,
            "rho",
            round(rho, 3),
            "CFO",
            round(cfo, 1),
            "first20",
            [
                (
                    r["symbol"],
                    round(r["template_bpsk_score"], 2),
                    round(r["lag60_sign_correlation"], 2),
                )
                for r in rows[:20]
            ],
            flush=True,
        )
    import scipy

    input_hashes = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [
            rawpath,
            refs / "sssVec.mat",
            refs / "referenceTemplate.mat",
            source / "exemplar250-257/sliceInfo.json",
            Path(__file__),
        ]
    }
    summary = dict(
        scope=(
            "Metadata-window acquisition and soft symbol structure; "
            "no FEC, CRC, payload semantics or ID claims."
        ),
        input_sha256=input_hashes,
        environment=dict(
            python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__
        ),
        channel_smooth=args.channel_smooth,
        carrier_limit=args.carrier_limit,
        sample_rate_hz=FS,
        subcarrier_indices=indices.tolist(),
        frames=results,
    )
    (args.out / "results.json").write_text(json.dumps(summary, indent=2) + "\n")
    np.savez_compressed(
        args.out / "soft_deviations.npz", deviations=np.array(arrays), subcarriers=indices
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), layout="constrained")
    for fr in results:
        rows = fr["symbols"]
        xx = [r["symbol"] for r in rows]
        axes[0].plot(
            xx, [r["template_bpsk_score"] for r in rows], label=str(fr["frame_id"]), alpha=0.8
        )
        axes[1].plot(xx, [r["lag60_sign_correlation"] for r in rows], alpha=0.8)
    axes[0].set(ylabel="Template BPSK axis score", ylim=(0, 1))
    axes[0].legend(ncol=7)
    axes[1].set(
        ylabel="Lag-60 sign correlation", ylim=(-0.2, 1), xlabel="OFDM symbol index (PSS=0, SSS=1)"
    )
    axes[2].imshow(
        np.sign(arrays[0][:35].real).T,
        aspect="auto",
        origin="lower",
        cmap="coolwarm",
        extent=(1.5, 36.5, 0, len(indices)),
    )
    axes[2].set(
        xlabel="OFDM symbol index",
        ylabel="Selected subcarrier ordinal",
        title="Frame 250: template deviations; per-symbol sign ambiguity remains",
    )
    fig.savefig(args.out / "header_structure.png", dpi=140)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    for fr in results:
        rows = fr["symbols"][:15]
        axes[0, 0].plot(
            [r["symbol"] for r in rows],
            [r["template_bpsk_score"] for r in rows],
            ".-",
            label=str(fr["frame_id"]),
        )
        axes[0, 0].plot(
            [r["symbol"] for r in rows],
            [max(r["rolled_control_max"], r["temporal_control"]) for r in rows],
            color="gray",
            alpha=0.4,
            linewidth=0.8,
        )
    axes[0, 0].set(
        title="Correct template vs gray wrong-template controls",
        xlabel="OFDM symbol index",
        ylabel="BPSK axis score",
        ylim=(0, 1.05),
    )
    axes[0, 0].legend(ncol=4, fontsize=8)
    d = arrays[0][0]
    tr = template[indices, 1]
    for ax, points, title in [
        (axes[0, 1], d, "Frame 250, symbol 2: correct template"),
        (
            axes[1, 0],
            d * tr * np.conj(np.roll(tr, 19)),
            "Same received symbols: template shifted 19 bins",
        ),
        (axes[1, 1], arrays[0][10], "Frame 250, symbol 12: later non-header region"),
    ]:
        ax.scatter(points.real, points.imag, s=3, alpha=0.4)
        ax.set(
            title=title,
            xlabel="I (normalized)",
            ylabel="Q (normalized)",
            xlim=(-1.7, 1.7),
            ylim=(-1.7, 1.7),
            aspect="equal",
        )
    fig.savefig(args.out / "header_evidence.png", dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    main()
