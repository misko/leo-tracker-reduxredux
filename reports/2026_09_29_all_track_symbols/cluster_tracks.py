"""Full track census hierarchies, with quality-qualified views kept separate."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import dendrogram, leaves_list, linkage
from scipy.spatial.distance import pdist

BASE = Path(__file__).parent
OUT = BASE / "local"
REGIONS = [(0, 6), (6, 32), (32, 128), (128, 300)]


def phase_distribution(z, regions=REGIONS, bins=16):
    """Equal region weights; invariant to frame order and positive amplitude."""
    if not np.isfinite(z).all() or z.ndim != 3 or min(z.shape) == 0:
        raise ValueError("Finite nonempty frame/symbol/carrier observations required")
    parts = []
    for start, stop in regions:
        values = z[:, start:stop]
        if not values.size:
            raise ValueError("Region is not covered")
        # Center histogram bins on the real axis; do not split tiny +/- phase
        # noise around BPSK signs across the branch cut or a bin boundary.
        phase = (np.angle(values) + np.pi / bins) % (2 * np.pi)
        counts = np.histogram(phase, bins=bins, range=(0, 2 * np.pi))[0]
        parts.append(counts / counts.sum() / len(regions))
    return np.concatenate(parts)


def mean_phase(z):
    return np.mean(z / np.maximum(abs(z), 1e-12), axis=0)


def hellinger_features(probabilities):
    p = np.asarray(probabilities)
    if np.any(p < 0) or not np.allclose(p.sum(axis=1), 1):
        raise ValueError("Normalized nonnegative distributions required")
    return np.sqrt(p) / np.sqrt(2)


def normalized_phase_features(profiles):
    x = np.asarray(profiles).reshape(len(profiles), -1)
    x = np.concatenate([x.real, x.imag], axis=1)
    x -= x.mean(axis=1, keepdims=True)
    n = np.linalg.norm(x, axis=1)
    if np.any(n < 1e-10):
        raise ValueError("Constant profiles cannot enter correlation clustering")
    return x / n[:, None]


def mean_bit_features(probabilities, words):
    if any(len(word) != 60 or set(word) - {"0", "1"} for word in words):
        raise ValueError("Only fully observed 60-bit words can enter bit-profile clustering")
    p = np.asarray(probabilities)
    hellinger_features(p)  # Validate normalization and signs.
    if p.shape[1] != len(words):
        raise ValueError("Word basis does not match distributions")
    basis = np.array([[1 if bit == "1" else -1 for bit in word] for word in words])
    return p @ basis / (2 * np.sqrt(60))


def hierarchy(name, features, tracks, metric_description, maximum=1):
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    folder = OUT / "clusters" / name
    folder.mkdir(parents=True, exist_ok=True)
    labels = [r["id"] for r in tracks]
    if len(labels) < 2:
        return dict(name=name, tracks=len(labels), status="insufficient_tracks")
    distances = pdist(features, metric="euclidean")
    if not np.isfinite(distances).all():
        raise ValueError("Nonfinite distance")
    tree = linkage(distances, method="average")
    order = leaves_list(tree)
    # Full hierarchy and all pairwise distances remain machine-readable.
    np.save(folder / "condensed_distances.npy", distances.astype(np.float32))
    np.save(folder / "features.npy", features)
    np.save(folder / "linkage.npy", tree)
    (folder / "labels.json").write_text(json.dumps(labels, indent=2) + "\n")
    with (folder / "ordered_tracks.csv").open("w") as stream:
        fields = [
            "leaf",
            "id",
            "dataset",
            "unit",
            "track_id",
            "receiver",
            "rate",
            "edge",
            "channel",
            "span_s",
            "status",
            "pilot",
            "known_words",
            "norad_id",
            "satellite_name",
            "rf_hz",
            "cfo_hz",
            "start_utc_ns",
            "end_utc_ns",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for leaf, i in enumerate(order):
            writer.writerow(dict(leaf=leaf, **{k: tracks[i].get(k) for k in fields if k != "leaf"}))
    # Large matrices are displayed as mean distances between contiguous leaf blocks.
    blocks = np.array_split(order, min(160, len(order)))
    display = np.zeros((len(blocks), len(blocks)))
    # Use only modest temporary arrays, even for a 12,000-leaf hierarchy.
    from scipy.spatial.distance import cdist

    for i, a in enumerate(blocks):
        for j in range(i, len(blocks)):
            display[i, j] = display[j, i] = cdist(features[a], features[blocks[j]]).mean()
    fig, axes = plt.subplots(
        1, 3, figsize=(16, 6), width_ratios=[1.1, 0.22, 1.4], layout="constrained"
    )
    dendrogram(
        tree,
        orientation="left",
        no_labels=True,
        color_threshold=0,
        above_threshold_color="#315a80",
        ax=axes[0],
    )
    axes[0].set(
        xlabel="Average-linkage distance",
        ylabel="All track leaves",
        title=f"Full hierarchy: {len(tracks):,} tracks",
    )
    # Dendrogram's bottom-to-top leaf order matches origin=lower below.
    flags = np.array(
        [
            [
                {"DS7": 0, "DS8": 1, "DS9": 2}[tracks[i]["dataset"]],
                3 if tracks[i]["status"] == "qualified" else 4,
            ]
            for i in order
        ]
    )
    axes[1].imshow(
        flags,
        origin="lower",
        aspect="auto",
        interpolation="nearest",
        cmap=ListedColormap(["#377eb8", "#ff7f00", "#4daf4a", "#009e73", "#aaaaaa"]),
        vmin=0,
        vmax=4,
    )
    axes[1].set(
        xticks=[0, 1], xticklabels=["Dataset", "Quality"], yticks=[], title="Track metadata"
    )
    axes[1].tick_params(axis="x", rotation=90)
    im = axes[2].imshow(
        display,
        origin="lower",
        aspect="auto",
        vmin=0,
        vmax=max(min(maximum, float(display.max())), 1e-12),
        cmap="viridis_r",
    )
    axes[2].set(
        title="Ordered distances" if len(tracks) <= 160 else "Mean distances by ordered leaf block",
        xlabel="Leaf index" if len(tracks) <= 160 else "Contiguous leaf block",
        ylabel="Leaf index" if len(tracks) <= 160 else "Contiguous leaf block",
    )
    fig.colorbar(im, ax=axes[2], shrink=0.7, label="Distance (observed display range)")
    fig.suptitle(
        name.replace("_", " ")
        + "\n"
        + metric_description
        + "\nMetadata: DS7 blue / DS8 orange / DS9 green; qualified teal / insufficient gray",
        fontsize=10,
    )
    fig.savefig(folder / "hierarchy.png", dpi=160)
    plt.close(fig)
    summary = dict(
        name=name,
        tracks=len(tracks),
        status="complete",
        metric=metric_description,
        quality=dict(Counter(r["status"] for r in tracks)),
        datasets=dict(Counter(r["dataset"] for r in tracks)),
        exact_zero_distance_fraction=float(np.mean(distances < 1e-10)),
        maximum_distance_fraction=float(np.mean(distances >= maximum - 1e-8)),
        mean_distance=float(distances.mean()),
        distance_quantiles=np.quantile(distances, [0.05, 0.5, 0.95]).tolist(),
        plotted_blocks=len(blocks),
    )
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    import matplotlib

    matplotlib.use("Agg")
    census = json.loads((OUT / "census.json").read_text())
    pending = [
        c["unit"]
        for c in census["captures"]
        if not (OUT / "decoded" / c["unit"] / "results.json").exists()
    ]
    if pending and not args.allow_partial:
        raise RuntimeError(f"Decode census incomplete: {len(pending)} recordings pending")
    annotations = BASE.parent / "2026_09_27_ds7_satellite_annotations/local/track-annotations.json"
    prior = {(r["session_id"], r["track_id"]): r for r in json.loads(annotations.read_text())}
    tracks, profiles, early, word_profiles, missing, errors = [], [], [], [], [], []
    for capture in census["captures"]:
        path = OUT / "decoded" / capture["unit"] / "results.json"
        if not path.exists():
            missing.append(capture["unit"])
            continue
        if args.allow_partial and not path.with_name("windows.json").exists():
            missing.append(capture["unit"])
            continue
        result = json.loads(path.read_text())
        window_result = json.loads(path.with_name("windows.json").read_text())
        assert window_result["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        by_index = {r["index"]: r for r in window_result["rows"]}
        assert len(result["rows"]) == len(capture["tracks"])
        assert {r["track_id"] for r in result["rows"]} == {t["track_id"] for t in capture["tracks"]}
        for row in result["rows"]:
            source_track = capture["tracks"][row["index"]]
            assert source_track["track_id"] == row["track_id"]
            info = {
                k: row.get(k)
                for k in ("track_id", "receiver", "channel", "span_s", "status", "edge")
            }
            label = prior.get((capture["session"], row["track_id"]), {})
            info.update(
                id=f"{capture['unit']}-T{row['index']:04d}",
                unit=capture["unit"],
                dataset=capture["dataset"],
                rate=capture["rate"],
                norad_id=label.get("norad_id")
                if label.get("status") == "likely_conditional"
                else None,
                identity_status=label.get("status"),
                satellite_name=label.get("satellite_name")
                if label.get("status") == "likely_conditional"
                else None,
                rf_hz=row.get("actual_rf_hz"),
                cfo_hz=row.get("candidate", {}).get("fractional_tracking_cfo_hz"),
                start_utc_ns=capture["start_utc_ns"] + round(min(source_track["times_s"]) * 1e9),
                end_utc_ns=capture["start_utc_ns"] + round(max(source_track["times_s"]) * 1e9),
                session=capture["session"],
                artifact=row.get("artifact"),
                visit=row.get("visit"),
            )
            if "artifact" not in row:
                errors.append(info)
                continue
            artifact = Path(row["artifact"])
            assert hashlib.sha256(artifact.read_bytes()).hexdigest() == row["artifact_sha256"]
            d = np.load(artifact)
            m = row["receiver_metadata"]
            ev = m["evaluation_frames"]
            quality = [m["diagnostics"][f]["held_pilot_coherence"] for f in ev]
            info["pilot"] = float(min(quality))
            keep = ~np.isin(d["bins"], m["pilot_bins"])
            z = d["z"][ev][:, :, keep]
            try:
                profile = phase_distribution(z)
            except ValueError as exc:
                errors.append(dict(**info, analysis_error=str(exc)))
                continue
            bins = d["bins"][keep]
            core = np.array(
                [486, 487, 496, 497] if row["edge"] == "upper" else [526, 527, 536, 537]
            )
            ep = None
            if np.isin(core, bins).all() and row["status"] == "qualified":
                ep = mean_phase(z[:, :6, np.searchsorted(bins, core)])
            windows = by_index[row["index"]]["windows"]
            words = [w["known_phase"] for w in windows if w["known_phase"] is not None]
            wp = [w["word"] for w in windows if w["accepted"]]
            info["known_words"] = len(words)
            info["accepted_words"] = len(wp)
            tracks.append(info)
            profiles.append(profile)
            early.append(ep)
            word_profiles.append(wp)
    profiles = np.array(profiles)
    results = [
        hierarchy(
            "all_recovered_phase_shapes",
            hellinger_features(profiles),
            tracks,
            "Phase-distribution Hellinger distance; includes low-quality signals, NOT identity",
        )
    ]
    qualified = [i for i, r in enumerate(tracks) if r["status"] == "qualified"]
    if len(qualified) >= 2:
        results.append(
            hierarchy(
                "qualified_phase_shapes",
                hellinger_features(profiles[qualified]),
                [tracks[i] for i in qualified],
                "Pilot-qualified phase-distribution Hellinger distance; not message correlation",
            )
        )
    for edge in ("upper", "lower"):
        selected = [i for i, p in enumerate(early) if p is not None and tracks[i]["edge"] == edge]
        if len(selected) >= 2:
            results.append(
                hierarchy(
                    f"{edge}_early_profiles",
                    normalized_phase_features([early[i] for i in selected]),
                    [tracks[i] for i in selected],
                    "Symbols 2–7, four common data carriers; normalized phase-profile distance",
                    maximum=2,
                )
            )
    selected = [i for i, p in enumerate(word_profiles) if p and tracks[i]["status"] == "qualified"]
    if len(selected) >= 2:
        basis = sorted({word for i in selected for word in word_profiles[i]})
        counts = np.array([[Counter(word_profiles[i])[word] for word in basis] for i in selected])
        probabilities = counts / counts.sum(axis=1, keepdims=True)
        # For singleton words, this metric is sqrt(Hamming distance / 60).
        # For multiple words it compares mean bit profiles, not payload identity.
        mean_bits = mean_bit_features(probabilities, basis)
        results.append(
            hierarchy(
                "qualified_mean_word_bits",
                mean_bits,
                [tracks[i] for i in selected],
                "Mean 60-bit candidate profiles; singleton distance = sqrt(Hamming/60); "
                "not identity",
            )
        )
        results.append(
            hierarchy(
                "qualified_observed_word_distributions",
                hellinger_features(probabilities),
                [tracks[i] for i in selected],
                "Observed word-distribution Hellinger distance (including unconfirmed deviations); "
                "windows from two evaluation frames",
            )
        )
        (OUT / "clusters/qualified_observed_word_distributions/word_basis.json").write_text(
            json.dumps(basis, indent=2) + "\n"
        )
        (OUT / "clusters/qualified_mean_word_bits/word_basis.json").write_text(
            json.dumps(basis, indent=2) + "\n"
        )
    output = dict(
        expected_tracks=census["tracks"],
        recovered_tracks=len(tracks),
        qualified_tracks=len(qualified),
        missing_captures=missing,
        errors=errors,
        tracks=tracks,
        hierarchies=results,
        limitations="One pilot-selected excerpt and four frames per receiver track, "
        "not every recorded visit. All-recovered tree includes failed pilot gates and "
        "can cluster noise/calibration. Qualified trees do not prove decoded bits or "
        "identity. Two evaluation frames per track, common SSS calibration. Known words "
        "are single-receiver even/odd checked candidates, not receiver-confirmed payload. "
        "Receiver tracks and revisits are dependent. Prior IDs are conditional annotations.",
    )
    (OUT / "clustering.json").write_text(json.dumps(output, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in output.items() if k not in ("tracks", "errors", "hierarchies")}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
