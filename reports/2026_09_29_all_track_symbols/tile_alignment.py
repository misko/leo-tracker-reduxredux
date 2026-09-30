"""Discovery-frame shift fitting with frozen held-frame and adjacent-tile checks."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from scipy.stats import spearmanr

BASE = Path(__file__).parent


def vector(tile):
    x = np.asarray(tile, dtype=complex).ravel().copy()
    x -= x.mean()
    norm = np.linalg.norm(x)
    if norm < 1e-10:
        raise ValueError("Constant tile")
    return x / norm


def compare(a, b, start, width, dt=0, df=0):
    # Eight available consecutive data carriers; compare the inner six.
    x = vector(a[start : start + width, 1:7])
    y = vector(b[start + dt : start + dt + width, 1 + df : 7 + df])
    return np.vdot(x, y)


def fit(a, b, start, width):
    choices = [(dt, df) for dt in range(-2, 3) for df in range(-1, 2)]
    scores = [compare(a, b, start, width, dt, df) for dt, df in choices]
    best = int(np.argmax(np.abs(scores)))
    dt, df = choices[best]
    rotation = np.exp(-1j * np.angle(scores[best]))
    return dt, df, rotation, float(abs(scores[best]))


def labels(scores, count=4):
    distances = np.sqrt(np.maximum(0, 2 - 2 * np.asarray(scores)))
    tree = linkage(distances, method="average")
    return fcluster(tree, count, criterion="maxclust"), tree


def agreement(a, b):
    """Adjusted Rand index, without an additional sklearn dependency."""
    _, ai = np.unique(a, return_inverse=True)
    _, bi = np.unique(b, return_inverse=True)
    table = np.zeros((ai.max() + 1, bi.max() + 1), dtype=int)
    np.add.at(table, (ai, bi), 1)

    def choose(x):
        return np.sum(x * (x - 1) / 2)

    total = len(a) * (len(a) - 1) / 2
    expected = choose(table.sum(0)) * choose(table.sum(1)) / total
    upper = (choose(table.sum(0)) + choose(table.sum(1))) / 2
    return float((choose(table) - expected) / (upper - expected)) if upper != expected else 1.0


def run():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    source = BASE / "local/clustering.json"
    inventory = json.loads(source.read_text())["tracks"]
    out = BASE / "local/tile-alignment"
    out.mkdir(exist_ok=True)
    report = {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "method_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "value_columns": [
            "discovery_magnitude",
            "held_shifted_real",
            "held_phase_only_real",
            "adjacent_shifted_real",
            "adjacent_phase_only_real",
            "time_shift",
            "carrier_shift",
            "held_shifted_magnitude",
            "held_unshifted_magnitude",
            "adjacent_shifted_magnitude",
        ],
        "edges": {},
    }
    for edge, first in [("upper", 480), ("lower", 536)]:
        candidates = sorted(
            [
                t
                for t in inventory
                if t["status"] == "qualified" and t["rate"] == 10000000 and t["edge"] == edge
            ],
            key=lambda t: (-t["pilot"], t["id"]),
        )
        tracks, arrays, seen = [], [], set()
        for track in candidates:
            key = (track["session"], track["visit"], track["channel"])
            if key in seen:
                continue
            with np.load(track["artifact"]) as data:
                bins = data["bins"]
                core = np.arange(first, first + 8)
                if not np.isin(core, bins).all():
                    continue
                rows = json.loads((Path(track["artifact"]).parent / "results.json").read_text())
                row = next(r for r in rows["rows"] if r["track_id"] == track["track_id"])
                ev = row["receiver_metadata"]["evaluation_frames"]
                assert len(ev) == 2
                assert not np.isin(core, row["receiver_metadata"]["pilot_bins"]).any()
                digest = hashlib.sha256(Path(track["artifact"]).read_bytes()).hexdigest()
                assert digest == row["artifact_sha256"]
                arrays.append(data["z"][ev][:, :, np.searchsorted(bins, core)])
            tracks.append(track)
            seen.add(key)
            if len(tracks) == 24:
                break
        n = len(tracks)
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
        edge_result = dict(tracks=tracks, data_carriers=list(range(first, first + 8)), tiles=[])
        fig, axes = plt.subplots(3, 2, figsize=(11, 12), layout="constrained")
        for wi, width in enumerate([8, 16, 32]):
            # Start index 2 is OFDM symbol 4, leaving a two-symbol search margin.
            start = 2
            records = []
            for i, j in pairs:
                a, b = arrays[i], arrays[j]
                dt, df, rotation, train = fit(a[0], b[0], start, width)
                zero = compare(a[0], b[0], start, width)
                zero_rotation = np.exp(-1j * np.angle(zero))
                records.append(
                    [
                        train,
                        (compare(a[1], b[1], start, width, dt, df) * rotation).real,
                        (compare(a[1], b[1], start, width) * zero_rotation).real,
                        (compare(a[1], b[1], start + width, width, dt, df) * rotation).real,
                        (compare(a[1], b[1], start + width, width) * zero_rotation).real,
                        dt,
                        df,
                        abs(compare(a[1], b[1], start, width, dt, df)),
                        abs(compare(a[1], b[1], start, width)),
                        abs(compare(a[1], b[1], start + width, width, dt, df)),
                    ]
                )
            values = np.asarray(records)
            groups, tree = labels(values[:, 1])
            adjacent_groups, adjacent_tree = labels(values[:, 3])
            gain = values[:, 1] - values[:, 2]
            adjacent_gain = values[:, 3] - values[:, 4]
            item = dict(
                width=width,
                start_ofdm_symbol=4,
                pairs=len(pairs),
                mean_discovery=float(values[:, 0].mean()),
                mean_held_shifted=float(values[:, 1].mean()),
                mean_held_phase_only=float(values[:, 2].mean()),
                mean_gain=float(gain.mean()),
                median_gain=float(np.median(gain)),
                positive_gain_fraction=float(np.mean(gain > 0)),
                adjacent_mean_gain=float(adjacent_gain.mean()),
                adjacent_matrix_spearman=float(spearmanr(values[:, 1], values[:, 3]).statistic),
                adjacent_four_cluster_ARI=agreement(groups, adjacent_groups),
                nonzero_shift_fraction=float(np.mean(np.any(values[:, 5:7] != 0, axis=1))),
                phase_invariant_mean_gain=float(np.mean(values[:, 7] - values[:, 8])),
                phase_invariant_adjacent_spearman=float(
                    spearmanr(values[:, 7], values[:, 9]).statistic
                ),
            )
            categories = {
                "same_session": [
                    k
                    for k, (i, j) in enumerate(pairs)
                    if tracks[i]["session"] == tracks[j]["session"]
                ],
                "different_session": [
                    k
                    for k, (i, j) in enumerate(pairs)
                    if tracks[i]["session"] != tracks[j]["session"]
                ],
                "same_conditional_id_different_session": [
                    k
                    for k, (i, j) in enumerate(pairs)
                    if tracks[i]["norad_id"] is not None
                    and tracks[i]["norad_id"] == tracks[j]["norad_id"]
                    and tracks[i]["session"] != tracks[j]["session"]
                ],
            }
            item["pair_categories"] = {
                name: dict(
                    count=len(indices),
                    mean_held_shifted=float(values[indices, 1].mean()) if indices else None,
                )
                for name, indices in categories.items()
            }
            np.savez(
                out / f"{edge}-{width}.npz",
                pairs=pairs,
                values=values,
                linkage=tree,
                adjacent_linkage=adjacent_tree,
            )
            edge_result["tiles"].append(item)
            axes[wi, 0].scatter(values[:, 2], values[:, 1], s=8, alpha=0.5)
            axes[wi, 0].plot([-1, 1], [-1, 1], color="gray")
            axes[wi, 0].set(
                xlabel="Held frame: phase-only baseline",
                ylabel="Held frame: fitted shifts",
                title=f"{width} symbols × 6 carriers; mean gain {gain.mean():.3f}",
            )
            matrix = squareform(values[:, 1])
            np.fill_diagonal(matrix, 1)
            im = axes[wi, 1].imshow(matrix, vmin=-1, vmax=1, cmap="coolwarm")
            axes[wi, 1].set(
                title="Held-frame similarity; pilot-quality order", xlabel="Track", ylabel="Track"
            )
            fig.colorbar(im, ax=axes[wi, 1])
        fig.suptitle(
            f"{edge.title()} edge: {n} distinct session/visit/channel selections\n"
            "Shift and phase fitted on first evaluation frame, frozen on second"
        )
        fig.savefig(out / f"{edge}.png", dpi=150)
        plt.close(fig)
        report["edges"][edge] = edge_result
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({edge: r["tiles"] for edge, r in report["edges"].items()}, indent=2))


if __name__ == "__main__":
    run()
