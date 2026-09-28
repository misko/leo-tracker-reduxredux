"""Matched-bandwidth DS7/UT illustrations; no new acquisition or detection claim."""

import hashlib
import json

import matplotlib
import numpy as np
from analyze import OUT, PILOT_CENTER, ROOT, demodulate
from scipy.io import loadmat
from scipy.signal import resample_poly, welch

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def rms(x):
    return np.sqrt(np.mean(abs(x) ** 2))


def main():
    inventory = json.loads((OUT / "inventory.json").read_text())
    result = json.loads((OUT / "results.json").read_text())[0]
    row = inventory["exports"][0]
    raw = np.load(OUT / (row["name"] + ".npy"))
    assert hashlib.sha256(raw.tobytes()).hexdigest() == row["excerpt_sha256"]
    ds = raw[:, 0].astype(float) + 1j * raw[:, 1]
    ep = result["frame_epoch_sample"]
    start = int(ep) - 100
    ds = ds[start : start + 13600]
    ds *= np.exp(
        -2j * np.pi * row["candidate"]["fractional_tracking_cfo_hz"] * np.arange(len(ds)) / 1e7
    )
    ds_epoch = ep - start

    source = ROOT / "docs/research/starlink-literature/local/data/ut-pilots"
    refs = source / "supplement/reference-template"
    frame = json.loads((ROOT / "reports/2026_09_27_ut_header/local/results.json").read_text())[
        "frames"
    ][0]
    ut_raw = np.memmap(
        source / "exemplar250-257/exemplar250-257.bin", dtype="<i2", mode="r"
    ).reshape(-1, 2)
    ut_start = round((frame["acquired_toa_s"] - 10e-6) * 250e6)
    v = ut_raw[ut_start : ut_start + 340000].astype(float)
    ut = v[:, 0] + 1j * v[:, 1]
    ut *= np.exp(-2j * np.pi * (PILOT_CENTER + frame["cfo_hz"]) * np.arange(len(ut)) / 250e6)
    ut = resample_poly(ut, 1, 25)
    captures = [
        (ds, ds_epoch, "DS7 · visit 2022 / RX0 · candidate frame 2"),
        (ut, 100, "UT · frame 250 · filtered from 250 to 10 MS/s"),
    ]
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(3, 2, figsize=(12, 10))
    psds = []
    for col, (x, epoch, title) in enumerate(captures):
        # Same duration, relative frame location, RMS convention and axes.
        segment = x[round(epoch + 88) : round(epoch + 88) + 3000]
        segment = segment / rms(segment)
        ax = axes[0, col]
        ax.plot(np.arange(120) / 10, segment[:120].real, label="I", lw=1)
        ax.plot(np.arange(120) / 10, segment[:120].imag, label="Q", lw=1, alpha=0.8)
        ax.set(
            title=title,
            xlabel="µs from start of OFDM symbol 2",
            ylabel="Amplitude / complex RMS",
            ylim=(-3, 3),
        )
        ax.legend(ncol=2, loc="upper right")
        ax = axes[1, col]
        ax.scatter(segment.real, segment.imag, s=3, alpha=0.25, rasterized=True)
        ax.set(
            xlabel="I / complex RMS",
            ylabel="Q / complex RMS",
            xlim=(-3, 3),
            ylim=(-3, 3),
            title="Time-domain IQ cloud · 300 µs (not a symbol constellation)",
        )
        ax.set_aspect("equal", adjustable="box")
        f, p = welch(segment, fs=1e7, nperseg=512, noverlap=256, return_onesided=False)
        f, p = np.fft.fftshift(f), np.fft.fftshift(p)
        p = 10 * np.log10(np.maximum(p * 1e6, 1e-20))
        psds.append((f, p))
        ax = axes[2, col]
        ax.plot(f / 1e6, p, lw=1.2)
        ax.axvspan(-0.9375, 0.9375, color="tab:orange", alpha=0.15, label="nominal pilot band")
        ax.set(
            xlabel="MHz relative to estimated pilot-band center",
            ylabel="PSD · dB relative to unit total power / MHz",
            xlim=(-5, 5),
        )
        ax.legend(loc="lower left")
    lo = min(p.min() for _, p in psds) - 2
    hi = max(p.max() for _, p in psds) + 2
    for ax in axes[2]:
        ax.set_ylim(lo, hi)
    fig.suptitle(
        "Captured waveform comparison · both 10 MS/s · independently RMS normalized", fontsize=15
    )
    fig.text(
        0.5,
        0.015,
        "UT is digitally band-limited; DS7 retains its hardware passband. "
        "Absolute received powers are not comparable.",
        ha="center",
    )
    fig.tight_layout(rect=(0, 0.035, 1, 0.965))
    fig.savefig(OUT / "iq-waveforms.png", dpi=160)
    plt.close(fig)

    sss = loadmat(refs / "sssVec.mat")["sssVecFull"].ravel()
    template = np.exp(
        0.5j * np.pi * loadmat(refs / "referenceTemplate.mat")["referenceTemplateRotations"]
    )
    bins = np.r_[476:488, 496:508]
    fig, axes = plt.subplots(2, 2, figsize=(10, 9))
    measurements = []
    for col, (x, epoch, title) in enumerate(captures):
        sy = demodulate(x, 1e7, epoch, 0)
        z = sy[1:9, bins] / (sy[0, bins] / sss[bins])
        z /= np.sqrt(np.mean(abs(z) ** 2, axis=1))[:, None]
        unit = z / np.maximum(abs(z), 1e-20)
        q = z * np.exp(-0.25j * np.angle(np.mean(unit**4, axis=1)))[:, None]
        d = z * template[bins, 1:9].T.conj()
        axis = 0.5 * np.angle(np.mean((d / np.maximum(abs(d), 1e-20)) ** 2, axis=1))
        d *= np.exp(-1j * axis)[:, None]
        concentration = abs(np.mean((d / np.maximum(abs(d), 1e-20)) ** 2, axis=1)).mean()
        measurements.append(dict(source=title, header_axis_concentration=float(concentration)))
        for idx, points in enumerate([q, d]):
            ax = axes[idx, col]
            ax.scatter(
                points.real,
                points.imag,
                s=15,
                alpha=0.65,
                c=np.repeat(np.arange(8), 24),
                cmap="viridis",
                vmin=0,
                vmax=7,
            )
            ax.axhline(0, color="grey", lw=0.5)
            ax.axvline(0, color="grey", lw=0.5)
            clipped = int(np.sum((abs(points.real) > 2.5) | (abs(points.imag) > 2.5)))
            ax.set(
                xlim=(-2.5, 2.5), ylim=(-2.5, 2.5), xlabel="I / symbol RMS", ylabel="Q / symbol RMS"
            )
            ax.set_aspect("equal")
            ax.set_title(
                (title.split(" · ")[0] + " · equalized header candidates")
                if idx == 0
                else f"Template removed · axis concentration {concentration:.3f}"
            )
            ax.text(
                0.02,
                0.02,
                f"192 points; {clipped} outside axes",
                transform=ax.transAxes,
                fontsize=8,
            )
    fig.suptitle("Non-pilot subcarriers · symbols 2–9 · 24 bins per symbol", fontsize=15)
    fig.text(
        0.5,
        0.035,
        "SSS equalization; RMS and phase normalized separately per symbol.\n"
        "Top: fourth-power phase alignment. Bottom: template removal + BPSK-axis alignment.\n"
        "DS7 timing/channel transfer remains unqualified; these are not decoded bytes.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0.105, 1, 0.965))
    fig.savefig(OUT / "iq-header-constellations.png", dpi=160)
    plt.close(fig)
    (OUT / "iq-plot-provenance.json").write_text(
        json.dumps(
            dict(
                ds7_excerpt=row["name"],
                ds7_frame=result["frame"],
                ut_frame=250,
                ds7_source_sha256=row["excerpt_sha256"],
                script_sha256=hashlib.sha256(
                    __import__("pathlib").Path(__file__).read_bytes()
                ).hexdigest(),
                bandwidth_sample_rate_hz=10000000,
                header_bins=bins.tolist(),
                measurements=measurements,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
