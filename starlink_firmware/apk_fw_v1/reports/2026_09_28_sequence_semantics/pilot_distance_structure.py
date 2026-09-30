"""Soft receiver reproducibility versus pilot distance and across cached visits."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent


def soft_correlations(a, b):
    """Per-coordinate centered phase correlations; no hard slicing or bit fitting."""
    a = a / np.maximum(abs(a), 1e-12)
    b = b / np.maximum(abs(b), 1e-12)
    results = []
    for x, y in ((a, b), (a.real, b.real), (a.imag, b.imag)):
        x, y = x - x.mean(axis=0), y - y.mean(axis=0)
        denom = np.sqrt((abs(x) ** 2).sum(axis=0) * (abs(y) ** 2).sum(axis=0))
        results.append(np.divide(
            (x.conj() * y).sum(axis=0).real, denom,
            out=np.full(denom.shape, np.nan), where=denom > 1e-10,
        ))
    return np.array(results)


def correlation(a, b):
    if len(a) < 3 or np.std(a) < 1e-10 or np.std(b) < 1e-10:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def main():
    prior = json.loads((BASE / "local/local_header_recovery.json").read_text())
    visits, profiles = [], {}
    for record in prior["rows"]:
        if "discovery_frames" not in record:
            continue
        name = record["signal"]
        path = BASE / f"local/{name}-soft.npz"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
        d = np.load(path)
        bins, ix, iy = np.intersect1d(d["bins0"], d["bins1"], return_indices=True)
        a, b = d["z0"][:, :6, ix], d["z1"][:, :6, iy]
        m = [json.loads(str(d[f"metadata{i}"])) for i in range(2)]
        assert m[0]["pilot_bins"] == m[1]["pilot_bins"]
        pilots = np.array(m[0]["pilot_bins"])
        distance = np.min(abs(bins[:, None] - pilots[None]), axis=1)
        side = np.where(bins < min(pilots), -1, 1)
        tr, ev = record["discovery_frames"], record["evaluation_frames"]
        frequency = (a[tr].real >= 0).mean(axis=0)
        variable = (frequency >= 0.2) & (frequency <= 0.8)
        discovery, evaluation = soft_correlations(a[tr], b[tr]), soft_correlations(a[ev], b[ev])
        controls = np.array([soft_correlations(a[ev], np.roll(b[ev], k, axis=0))
                             for k in range(1, len(ev))])
        control_mean = np.nanmean(controls, axis=0)
        rows, groups = [], []
        for s, k in zip(*np.nonzero(variable), strict=True):
            values = np.r_[discovery[:, s, k], evaluation[:, s, k], control_mean[:, s, k]]
            if not np.isfinite(values).all():
                continue
            rows.append(dict(symbol=int(s + 2), fft_bin=int(bins[k]),
                             distance=int(distance[k]), side=int(side[k]),
                             discovery=discovery[:, s, k].tolist(),
                             evaluation=evaluation[:, s, k].tolist(),
                             shifted_mean=control_mean[:, s, k].tolist()))
        for lo, hi in [(1, 2), (3, 4), (5, 8), (9, 12)]:
            subset = [r for r in rows if lo <= r["distance"] <= hi]
            if subset:
                groups.append(dict(
                    distance=[lo, hi], coordinates=len(subset),
                    evaluation=np.mean([r["evaluation"] for r in subset], axis=0).tolist(),
                    shifted_mean=np.mean([r["shifted_mean"] for r in subset], axis=0).tolist(),
                ))
        # Center within each symbol and side so their fixed differences cannot
        # alone create a pilot-distance association.
        dx, dy = [], []
        for symbol in range(2, 8):
            for flank in (-1, 1):
                sub = [r for r in rows if r["symbol"] == symbol and r["side"] == flank]
                if len(sub) >= 3:
                    x = np.array([r["distance"] for r in sub], float)
                    y = np.array([r["evaluation"][0] for r in sub])
                    dx.extend(x - x.mean())
                    dy.extend(y - y.mean())
        visit_controls = np.nanmean(controls[:, :, variable], axis=2)
        visits.append(dict(signal=name, sha256=record["sha256"],
                           discovery_frames=tr, evaluation_frames=ev, pilot_bins=pilots.tolist(),
                           groups=groups, coordinates=rows,
                           mean_evaluation=np.mean(
                               [r["evaluation"] for r in rows], axis=0).tolist(),
                           mean_shifted=np.mean([r["shifted_mean"] for r in rows], axis=0).tolist(),
                           shifted_visit_95=np.quantile(visit_controls, .95, axis=0).tolist(),
                           shifted_visit_max=np.max(visit_controls, axis=0).tolist(),
                           within_symbol_side_distance_correlation=correlation(dx, dy)))
        profiles[name] = {(r["symbol"], r["fft_bin"]): r for r in rows}
    transfers = []
    rng = np.random.default_rng(20260930)
    for source, p in profiles.items():
        for target, q in profiles.items():
            if source == target:
                continue
            common = sorted(p.keys() & q.keys())
            if len(common) < 12:
                continue
            x = np.array([p[c]["discovery"][0] for c in common])
            y = np.array([q[c]["evaluation"][0] for c in common])
            symbols = np.array([c[0] for c in common])
            baseline = []
            for _ in range(100):
                shuffled = y.copy()
                for symbol in np.unique(symbols):
                    mask = symbols == symbol
                    shuffled[mask] = rng.permutation(y[mask])
                baseline.append(correlation(x, shuffled))
            transfers.append(dict(source=source, target=target, coordinates=len(common),
                                  correlation=correlation(x, y),
                                  within_symbol_permutation_median=float(np.median(baseline)),
                                  within_symbol_permutation_95=float(np.quantile(baseline, .95))))
    output = dict(visits=visits, transfers=transfers,
                  excluded_visits=[r["signal"] for r in prior["rows"]
                                   if "discovery_frames" not in r],
                  metric_order=["centered_complex_phase", "centered_real_phase",
                                "centered_imag_phase"],
                  limitation="Existing bounded visit caches, not exhaustive DS7/8/9. "
                  "Discovery uses RX0 variable signs only. Evaluation keeps all soft "
                  "values at selected coordinates. Cross-visit transfer compares "
                  "reliability profiles, not unsynchronized message bits. Correlation "
                  "is not BER or proof of transmitted data. Descriptive permutations "
                  "do not preserve frequency dependence or correct multiple searches. "
                  "Mean over all nonzero circular shifts equals minus matched "
                  "correlation divided by (frames-1) after centering; that mean "
                  "is not independent corroboration. Shift maxima/quantiles are "
                  "also reported. Previously studied recordings, not pristine holdout.")
    (BASE / "local/pilot_distance_structure.json").write_text(json.dumps(output, indent=2) + "\n")
    for row in visits:
        print(json.dumps({k: row[k] for k in ["signal", "mean_evaluation", "mean_shifted",
                                            "within_symbol_side_distance_correlation"]}))
    print("Cross-visit comparisons:", len(transfers))
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for v in visits:
        axes[0].plot([np.mean(g["distance"]) for g in v["groups"]],
                     [g["evaluation"][0] for g in v["groups"]], "o-", label=v["signal"])
    axes[0].set(xlabel="Distance from nearest pilot bin",
                ylabel="Mean centered complex correlation",
                title="Soft reproducibility versus pilot distance", ylim=(-.1, 1))
    axes[0].legend(fontsize=8)
    names = list(profiles)
    grid = np.full((len(names), len(names)), np.nan)
    for r in transfers:
        grid[names.index(r["source"]), names.index(r["target"])] = r["correlation"]
    im = axes[1].imshow(grid, vmin=-1, vmax=1, cmap="coolwarm")
    axes[1].set(xticks=range(len(names)), xticklabels=names, yticks=range(len(names)),
                yticklabels=names, xlabel="Target evaluation", ylabel="Source discovery",
                title="Reliability-profile transfer (blank = unavailable)")
    axes[1].tick_params(axis="x", rotation=60)
    fig.colorbar(im, ax=axes[1], label="Coordinate-profile correlation")
    fig.savefig(BASE / "local/pilot_distance_structure.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
