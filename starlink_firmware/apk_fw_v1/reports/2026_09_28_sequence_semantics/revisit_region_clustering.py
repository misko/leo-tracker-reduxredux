"""Bounded, receiver/time-split visit-profile comparisons on common RF coordinates."""

import hashlib
import json
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import dendrogram, leaves_list, linkage
from scipy.spatial.distance import pdist, squareform

BASE = Path(__file__).resolve().parent
OUT = BASE / "local/revisit-regions"


def phase_profile(z):
    """Mean unit phasor per coordinate; arbitrary visit frame alignment is avoided."""
    return (z / np.maximum(abs(z), 1e-12)).mean(axis=0)


def feature_matrix(profiles):
    values = np.asarray(profiles).reshape(len(profiles), -1)
    return np.concatenate([values.real, values.imag], axis=1)


def profile_geometry(profiles):
    x = feature_matrix(profiles)
    centered = x - x.mean(axis=1, keepdims=True)
    norm = np.linalg.norm(centered, axis=1)
    if np.any(norm < 1e-10):
        raise ValueError("Constant profile has undefined correlation")
    corr = centered @ centered.T / np.outer(norm, norm)
    # Euclidean distances between normalized vectors are a valid clustering metric.
    distance = squareform(pdist(centered / norm[:, None]))
    return np.clip(corr, -1, 1), distance


def main():
    OUT.mkdir(exist_ok=True)
    inventory = json.loads(
        (BASE.parents[3] / "reports/2026_09_28_signal_clustering/local/inventory.json")
        .read_text()
    )
    inventory = {v["signal"]: v for v in inventory}
    visits, excluded = [], []
    for path in sorted((BASE / "local").glob("*-soft.npz")):
        name = path.stem.removesuffix("-soft")
        if name in inventory:
            source = inventory[name]
            info = {k: source[k] for k in ("signal", "session", "visit", "edge", "norad_id")}
            info["rate"] = source["streams"][0]["row"]["sample_rate_hz"]
        elif name.startswith("DS9-"):
            ip = BASE / f"local/ds9-{name[4:]}-10m/inventory.json"
            row = json.loads(ip.read_text())["exports"][0]
            info = dict(
                signal=name,
                session=row["session_id"],
                visit=row["probe"]["visit_index"],
                edge=row["probe"]["edge"],
                norad_id=None,
                rate=row["sample_rate_hz"],
            )
        else:
            continue
        d = np.load(path)
        if name in inventory:
            assert (
                str(d["binding"])
                == hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
            )
        else:
            assert str(d["inventory_sha256"]) == hashlib.sha256(ip.read_bytes()).hexdigest()
        m = [json.loads(str(d[f"metadata{i}"])) for i in (0, 1)]
        frames = sorted(set(m[0]["evaluation_frames"]) & set(m[1]["evaluation_frames"]))
        frames = [
            f for f in frames if min(v["diagnostics"][f]["held_pilot_coherence"] for v in m) > 0.5
        ]
        info.update(qualified_frames=frames, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if len(frames) < 16:
            excluded.append(info)
            continue
        bins, ix, iy = np.intersect1d(d["bins0"], d["bins1"], return_indices=True)
        mask = ~np.isin(bins, np.union1d(m[0]["pilot_bins"], m[1]["pilot_bins"]))
        visits.append(
            dict(info=info, bins=bins[mask], z=[d["z0"][:, :, ix[mask]], d["z1"][:, :, iy[mask]]])
        )
    regions = [
        ("early_2_7", 0, 6),
        ("early_8_33", 6, 32),
        ("early_34_129", 32, 128),
        ("later_130_301", 128, 300),
    ]
    results = []
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(15, 9), layout="constrained")
    for cohort, edge, edge_index in (
        ("upper_10m", "upper", 0),
        ("upper_mixed", "upper", None),
        ("lower_10m", "lower", 1),
    ):
        group = [
            v
            for v in visits
            if v["info"]["edge"] == edge
            and (cohort == "upper_mixed" or v["info"]["rate"] == 10000000)
        ]
        common = sorted(set.intersection(*(set(v["bins"].tolist()) for v in group)))
        names = [v["info"]["signal"] for v in group]
        labels = [
            f"{n} | {v['info']['rate'] / 1e6:g}M | {v['info']['norad_id'] or '?'}"
            for n, v in zip(names, group, strict=True)
        ]
        for region, start, stop in regions:
            profiles = [[], []]
            repeatability = []
            for v in group:
                frames = v["info"]["qualified_frames"]
                split = len(frames) // 2
                indices = np.searchsorted(v["bins"], common)
                for part, (rx, fs) in enumerate(((0, frames[:split]), (1, frames[split:]))):
                    profiles[part].append(phase_profile(v["z"][rx][fs, start:stop][:, :, indices]))
                c, _ = profile_geometry([profiles[0][-1], profiles[1][-1]])
                repeatability.append(float(c[0, 1]))
            discovery, distances = profile_geometry(profiles[0])
            evaluation, _ = profile_geometry(profiles[1])
            tree = linkage(squareform(distances, checks=False), method="average")
            rms_distance = squareform(pdist(feature_matrix(profiles[1]))) / np.sqrt(
                2 * len(common) * (stop - start)
            )
            pairs = []
            for i, j in combinations(range(len(group)), 2):
                a, b = group[i]["info"], group[j]["info"]
                pairs.append(
                    dict(
                        a=names[i],
                        b=names[j],
                        discovery=float(discovery[i, j]),
                        evaluation=float(evaluation[i, j]),
                        same_prior_identity=(a["norad_id"] == b["norad_id"])
                        if a["norad_id"] and b["norad_id"]
                        else None,
                        same_session=a["session"] == b["session"],
                        same_rate=a["rate"] == b["rate"],
                        evaluation_rms_distance=float(rms_distance[i, j]),
                    )
                )
            # Descriptive receiver/time split consistency, not a significance test.
            nearest_discovery = np.argmin(distances + np.eye(len(group)) * 10, axis=1)
            nearest_eval = np.argmax(evaluation - np.eye(len(group)) * 10, axis=1)
            results.append(
                dict(
                    edge=edge,
                    cohort=cohort,
                    region=region,
                    common_bins=common,
                    names=names,
                    discovery=discovery.tolist(),
                    evaluation=evaluation.tolist(),
                    tree=tree.tolist(),
                    within_visit_split_correlation=repeatability,
                    nearest_neighbor_split_agreement=float(
                        np.mean(nearest_discovery == nearest_eval)
                    ),
                    pairs=pairs,
                )
            )
            np.savez_compressed(
                OUT / f"{cohort}-{region}.npz", discovery=profiles[0], evaluation=profiles[1]
            )
            if region == "early_2_7":
                primary = [v for v in group if v["info"]["rate"] == 10000000]
                primary_names = [v["info"]["signal"] for v in primary]
                primary_ix = [names.index(n) for n in primary_names]
                primary_tree = linkage(
                    squareform(distances[np.ix_(primary_ix, primary_ix)], checks=False),
                    method="average",
                )
                # Equal-size subsets of each held-out half; descriptive sensitivity only.
                rng = np.random.default_rng(20261002)
                draws = []
                count = min(len(v["info"]["qualified_frames"]) / 2 for v in primary)
                count = min(10, int(count))
                for _ in range(200):
                    sampled = []
                    for v in primary:
                        fs = v["info"]["qualified_frames"]
                        fs = rng.choice(fs[len(fs) // 2 :], count, replace=False)
                        ix = np.searchsorted(v["bins"], common)
                        sampled.append(phase_profile(v["z"][1][fs, :6][:, :, ix]))
                    draws.append(profile_geometry(sampled)[0])
                draws = np.array(draws)
                results[-1]["balanced_evaluation"] = dict(
                    names=primary_names,
                    frames_per_visit=count,
                    repetitions=200,
                    mean=draws.mean(axis=0).tolist(),
                    quantiles=np.quantile(draws, [0.025, 0.975], axis=0).tolist(),
                    discovery_tree=primary_tree.tolist(),
                )
                if edge == "upper":
                    i, j, k = [primary_names.index(n) for n in ("S13", "S22", "S23")]
                    results[-1]["balanced_evaluation"]["same_pair_strictly_best_fraction"] = float(
                        np.mean(draws[:, j, k] > np.maximum(draws[:, i, j], draws[:, i, k]))
                    )
                if edge_index is None:
                    continue
                dendrogram(tree, labels=labels, ax=axes[edge_index, 0], leaf_rotation=65)
                axes[edge_index, 0].set(
                    title=f"{edge}: early-region discovery hierarchy",
                    ylabel="Normalized Euclidean distance",
                )
                order = leaves_list(tree)
                for col, matrix, title in (
                    (1, discovery, "RX0 earlier frames"),
                    (2, evaluation, "RX1 later frames"),
                ):
                    ax = axes[edge_index, col]
                    im = ax.imshow(matrix[np.ix_(order, order)], vmin=-1, vmax=1, cmap="coolwarm")
                    ax.set(
                        xticks=range(len(order)),
                        xticklabels=np.array(names)[order],
                        yticks=range(len(order)),
                        yticklabels=np.array(names)[order],
                        title=title,
                    )
                    ax.tick_params(axis="x", rotation=60)
                    for i, oi in enumerate(order):
                        for j, oj in enumerate(order):
                            ax.text(
                                j, i, f"{matrix[oi, oj]:.2f}", ha="center", va="center", fontsize=9
                            )
    fig.colorbar(im, ax=axes[:, 1:], label="Mean unit-phasor profile correlation", shrink=0.7)
    fig.suptitle(
        "OFDM symbols 2–7: visit profiles, not aligned message bits; NORAD labels are tentative"
    )
    fig.savefig(OUT / "clustering.png", dpi=160)
    plt.close(fig)
    output = dict(
        visits=[v["info"] for v in visits],
        excluded=excluded,
        results=results,
        limitation="Cached subset. Common original carriers, not expanded atlas calibration. "
        "No cross-edge coordinate equivalence assumed. Known structure not subtracted; "
        "region boundaries fixed before comparisons. Correlation of average phase profiles "
        "is not correlation of synchronized bits or evidence of identity. Discovery and "
        "evaluation use different receivers and disjoint chronological subsets of decoder "
        "evaluation frames, but share recording/calibration. No pristine holdout. "
        "Known repeat-state mixtures can confound comparisons. Balanced subset ranges "
        "are sensitivity ranges, not confidence intervals. Pairs dependent; no p-values.",
    )
    (OUT / "results.json").write_text(json.dumps(output, indent=2) + "\n")
    for r in results:
        print(r["edge"], r["region"], "split", np.round(r["within_visit_split_correlation"], 3))
        for p in r["pairs"]:
            if p["same_prior_identity"] is not None:
                print(p)


if __name__ == "__main__":
    main()
