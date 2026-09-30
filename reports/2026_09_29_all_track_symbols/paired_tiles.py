"""Within-frame split-symbol validation of paired-receiver tile alignment."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent
ATLAS = BASE.parent / "2026_09_28_sequence_semantics/local/ten-msps-atlas"


def corr(x, y):
    x, y = x.ravel().astype(complex), y.ravel().astype(complex)
    x, y = x - x.mean(), y - y.mean()
    return np.vdot(x, y) / max(np.linalg.norm(x) * np.linalg.norm(y), 1e-12)


def evaluate(a, b, width):
    """Even reference symbols fit; odd reference symbols validate, no wrap."""
    reference = a[2 : 2 + width, 1:7]
    fits = []
    for dt in range(-2, 3):
        for df in range(-1, 2):
            candidate = b[2 + dt : 2 + dt + width, 1 + df : 7 + df]
            value = corr(reference[::2], candidate[::2])
            fits.append((abs(value), dt, df, np.exp(-1j * np.angle(value))))
    _, dt, df, rotation = max(fits, key=lambda x: x[0])
    target = b[2 + dt : 2 + dt + width, 1 + df : 7 + df]
    baseline = b[2 : 2 + width, 1:7]
    zero_rotation = np.exp(-1j * np.angle(corr(reference[::2], baseline[::2])))
    raw_score = corr(reference[1::2], baseline[1::2]).real
    shifted_score = (corr(reference[1::2], target[1::2]) * rotation).real
    phase_score = (corr(reference[1::2], baseline[1::2]) * zero_rotation).real
    # Keep observations on their original real axis; these are not corrected bits.
    signs = reference[1::2].real >= 0
    peer = baseline[1::2].real >= 0
    return dict(
        time_shift=dt,
        carrier_shift=df,
        raw=float(raw_score),
        phase_only=float(phase_score),
        shifted=float(shifted_score),
        sign_agreement=float(np.mean(signs == peer)),
        real_signs="".join("1" if s else "0" for s in signs.ravel()),
        peer_real_signs="".join("1" if s else "0" for s in peer.ravel()),
    )


def main():
    inventory_path = ATLAS / "atlas.json"
    inventory = json.loads(inventory_path.read_text())
    out = BASE / "local/paired-tiles"
    out.mkdir(exist_ok=True)
    result = dict(
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        atlas_sha256=hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
        visits=[],
    )
    for visit in inventory["visits"]:
        path = ATLAS / f"{visit['name']}.npz"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == visit["cache_sha256"]
        data = np.load(path)
        metas = [json.loads(str(data[f"metadata{rx}"])) for rx in range(2)]
        first = 480 if visit["edge"] == "upper" else 536
        bins = np.arange(first, first + 8)
        frames = visit["qualified_frames"]
        arrays = []
        epochs = []
        for rx, stream in enumerate(visit["source_streams"]):
            row = stream["row"]
            assert np.isin(bins, data[f"bins{rx}"]).all()
            assert not np.isin(bins, metas[rx]["pilot_bins"]).any()
            assert set(frames) <= set(metas[rx]["evaluation_frames"])
            assert all(metas[rx]["diagnostics"][f]["held_pilot_coherence"] > 0.5 for f in frames)
            arrays.append(data[f"z{rx}"][frames][:, :, np.searchsorted(data[f"bins{rx}"], bins)])
            c = row["candidate"]
            epochs.append(
                (
                    row["excerpt_start_in_visit"]
                    + c["integer_epoch_sample"]
                    + c["fractional_epoch_offset_samples"]
                )
                / row["sample_rate_hz"]
            )
        assert abs(epochs[0] - epochs[1]) < 1 / 1500
        summaries = []
        for width in (8, 16, 32):
            matched = [evaluate(a, b, width) for a, b in zip(*arrays, strict=True)]
            controls = []
            # Every nonzero cyclic frame shift, with the full fitting procedure repeated.
            for shift in range(1, len(frames)):
                rows = [
                    evaluate(a, b, width)
                    for a, b in zip(arrays[0], np.roll(arrays[1], shift, axis=0), strict=True)
                ]
                controls.append(
                    {
                        key: float(np.mean([r[key] for r in rows]))
                        for key in ("raw", "phase_only", "shifted", "sign_agreement")
                    }
                )
            summary = dict(
                width=width,
                frames=len(frames),
                held_decisions=len(frames) * width * 3,
                zero_shift_fraction=float(
                    np.mean([r["time_shift"] == r["carrier_shift"] == 0 for r in matched])
                ),
            )
            for key in ("raw", "phase_only", "shifted", "sign_agreement"):
                summary[key] = dict(
                    matched_mean=float(np.mean([r[key] for r in matched])),
                    control_mean=float(np.mean([r[key] for r in controls])),
                    control_max=float(np.max([r[key] for r in controls])),
                )
            (out / f"{visit['name']}-{width}.json").write_text(
                json.dumps(
                    dict(frames=frames, bins=bins.tolist(), matched=matched, controls=controls),
                    indent=2,
                )
            )
            summaries.append(summary)
        common = np.intersect1d(data["bins0"], data["bins1"])
        common = common[
            ~np.isin(common, np.union1d(metas[0]["pilot_bins"], metas[1]["pilot_bins"]))
        ]
        full = [
            data[f"z{rx}"][frames][:, :, np.searchsorted(data[f"bins{rx}"], common)]
            for rx in range(2)
        ]
        phase_by_frame = {
            w["frame"]: w["phase_hypothesis"]
            for w in visit["windows"]
            if w["first_symbol"] == 194 and w["label"] == 1
        }
        phases = np.array([phase_by_frame.get(f, -1) for f in frames])
        state_results = []
        rng = np.random.default_rng(20260929)
        for start, stop in [(0, 6), (6, 32), (32, 128), (128, 192), (192, 224)]:
            pairs = [
                (i, j)
                for i in range(len(frames))
                for j in range(i + 1, len(frames))
                if phases[i] >= 0 and phases[j] >= 0
            ]
            scores = np.array(
                [
                    (
                        corr(full[0][i, start:stop], full[1][j, start:stop]).real
                        + corr(full[0][j, start:stop], full[1][i, start:stop]).real
                    )
                    / 2
                    for i, j in pairs
                ]
            )
            pair_array = np.asarray(pairs)
            same = phases[pair_array[:, 0]] == phases[pair_array[:, 1]]
            np.savez(
                out / f"{visit['name']}-state-{start + 2}-{stop + 1}.npz",
                frames=frames,
                bins=common,
                phases=phases,
                pairs=pair_array,
                scores=scores,
                same_state=same,
            )
            controls = []
            eligible = np.flatnonzero(phases >= 0)
            for _ in range(199):
                shuffled = phases.copy()
                shuffled[eligible] = rng.permutation(phases[eligible])
                mask = shuffled[pair_array[:, 0]] == shuffled[pair_array[:, 1]]
                controls.append(float(scores[mask].mean() - scores[~mask].mean()))
            state_results.append(
                dict(
                    first_symbol=start + 2,
                    last_symbol=stop + 1,
                    same_pairs=int(same.sum()),
                    different_pairs=int((~same).sum()),
                    same_mean=float(scores[same].mean()),
                    different_mean=float(scores[~same].mean()),
                    difference=float(scores[same].mean() - scores[~same].mean()),
                    shuffled_difference_quantiles=np.quantile(
                        controls, [0.025, 0.5, 0.975]
                    ).tolist(),
                )
            )
        result["visits"].append(
            dict(
                name=visit["name"],
                edge=visit["edge"],
                epoch_difference_s=epochs[0] - epochs[1],
                tiles=summaries,
                state_comparison=state_results,
            )
        )
        print(json.dumps(result["visits"][-1], indent=2), flush=True)
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
    for visit in result["visits"]:
        rows = visit["state_comparison"][:4]
        axes[0].plot(range(4), [r["same_mean"] for r in rows], "o-", label=visit["name"])
        axes[1].plot(range(4), [r["difference"] for r in rows], "o-", label=visit["name"])
    for ax in axes:
        ax.set(
            xticks=range(4),
            xticklabels=["2–7", "8–33", "34–129", "130–193"],
            xlabel="OFDM symbol region",
        )
        ax.axhline(0, color="gray", linewidth=0.8)
        ax.legend()
    axes[0].set(ylabel="Mean cross-frame / cross-RX correlation", title="Same known tail state")
    axes[1].set(
        ylabel="Same-state minus different-state correlation", title="State-associated gain"
    )
    fig.suptitle("Known state selected separately at symbols 194–225; all 28 common data carriers")
    fig.savefig(out / "state-comparison.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
