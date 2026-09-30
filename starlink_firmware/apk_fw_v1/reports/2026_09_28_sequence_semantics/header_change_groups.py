"""Discover noncontiguous co-change edges; freeze selection before evaluation."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def residuals(changes, common):
    centered = changes.astype(float) - changes.mean(axis=0)
    common = common - common.mean()
    power = common @ common
    if power > 1e-12:
        centered -= common[:, None] * ((common @ centered) / power)[None, :]
    norm = np.linalg.norm(centered, axis=0)
    return centered / np.maximum(norm, 1e-12)


def discover(changes, threshold=0.8):
    """Collapse identical change traces; select each representative's best edge."""
    _, representatives = np.unique(changes.T, axis=0, return_index=True)
    representatives = np.sort(representatives)
    matrix = residuals(changes[:, representatives], changes[:, representatives].mean(axis=1))
    scores = matrix.T @ matrix
    np.fill_diagonal(scores, -np.inf)
    edges = set()
    if len(representatives) > 1:
        for i, j in enumerate(np.argmax(scores, axis=1)):
            if scores[i, j] >= threshold:
                edges.add(tuple(sorted((int(i), int(j)))))
    return representatives, sorted(edges), matrix


def components(n, edges):
    parents = list(range(n))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    for i, j in edges:
        parents[root(j)] = root(i)
    groups = {}
    for i in range(n):
        groups.setdefault(root(i), []).append(i)
    return sorted((g for g in groups.values() if len(g) > 1), key=len, reverse=True)


def main():
    source = BASE / "local/header-reference-0-77.npz"
    template_path = (
        BASE.parents[3] / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    bins = np.array([k for k in range(2, 1022)
                     if k not in range(488, 496) and k not in range(528, 536)])
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(source)["symbols"][:, :, bins] * np.exp(-0.5j * np.pi * template[bins, 1:7].T)
    valid = ((abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)).reshape(78, -1)
    bits = (z.real >= 0).reshape(78, -1)
    train = bits[1:39] ^ bits[:38]
    test = bits[40:78] ^ bits[39:77]
    counts = train.sum(axis=0)
    selected = np.flatnonzero(valid[:39].all(axis=0) & (counts >= 6) & (counts <= 32))
    representatives, edges, fitted = discover(train[:, selected])
    coordinates = selected[representatives]
    test_good = valid[39:].all(axis=0)
    common = test[:, coordinates[test_good[coordinates]]].mean(axis=1)
    evaluation = residuals(test[:, coordinates], common)
    rng = np.random.default_rng(20260930)
    controls = []
    # Preserve each coordinate's number and temporal ordering of transitions,
    # while independently rotating their alignment with other coordinates.
    for _ in range(20):
        shuffled = np.column_stack([
            np.roll(test[:, p], rng.integers(1, len(test))) for p in coordinates
        ])
        controls.append(residuals(shuffled, shuffled[:, test_good[coordinates]].mean(axis=1)))

    raw_path = BASE / "local/pilot_referenced_header_bits.npz"
    raw = np.load(raw_path)
    raw_bins = {int(b): i for i, b in enumerate(raw["bins"])}
    state_path = BASE / "local/shared_header_coordinates.json"
    states = np.array(json.loads(state_path.read_text())["reference_state_indices"])
    same_state = states[40:] == states[39:-1]

    def coord(index):
        p = int(coordinates[index])
        return dict(symbol=p // len(bins) + 2, fft_bin=int(bins[p % len(bins)]))

    rows = []
    for i, j in edges:
        qualified = bool(test_good[coordinates[i]] and test_good[coordinates[j]])
        ca, cb = coord(i), coord(j)
        raw_values = np.column_stack([
            raw["bits"][:, c["symbol"] - 2, raw_bins[c["fft_bin"]]] for c in (ca, cb)
        ])
        raw_valid = np.column_stack([
            raw["valid"][:, c["symbol"] - 2, raw_bins[c["fft_bin"]]] for c in (ca, cb)
        ]).all(axis=1)
        raw_pairs = raw_valid[1:] & raw_valid[:-1]
        raw_changes = (raw_values[1:] ^ raw_values[:-1])[raw_pairs]
        within_state = test[same_state][:, [coordinates[i], coordinates[j]]]
        rows.append(dict(
            i=i, j=j, a=ca, b=cb,
            discovery=float(fitted[:, i] @ fitted[:, j]), qualified=qualified,
            evaluation=float(evaluation[:, i] @ evaluation[:, j]) if qualified else None,
            controls=[float(c[:, i] @ c[:, j]) for c in controls] if qualified else [],
            evaluation_transition_counts=[int(test[:, coordinates[k]].sum()) for k in (i, j)],
            raw_qualified_transitions=int(raw_pairs.sum()),
            raw_change_counts=raw_changes.sum(axis=0).astype(int).tolist(),
            raw_change_disagreements=int((raw_changes[:, 0] != raw_changes[:, 1]).sum()),
            same_state_evaluation_transitions=int(same_state.sum()),
            same_state_change_counts=within_state.sum(axis=0).astype(int).tolist(),
            same_state_disagreements=int((within_state[:, 0] != within_state[:, 1]).sum()),
        ))
    groups = components(len(representatives), edges)
    good = [r for r in rows if r["qualified"]]
    summary = dict(
        selected_positions=len(selected), unique_discovery_change_traces=len(representatives),
        edges=len(edges), components=len(groups), component_sizes=[len(g) for g in groups],
        qualified_evaluation_edges=len(good),
        evaluation_median=float(np.median([r["evaluation"] for r in good])) if good else None,
        evaluation_at_least_08=sum(r["evaluation"] >= 0.8 for r in good),
        control_at_least_08=[sum(r["controls"][i] >= 0.8 for r in good) for i in range(20)],
    )
    output = dict(
        summary=summary, edges=rows,
        components=[[coord(i) for i in group] for group in groups],
        input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in (source, template_path, raw_path, state_path)},
        limitation="Exploratory new assay on previously studied frames, not pristine "
        "holdout. Edges selected only on frames0..38, evaluated39..77. Adjacent XOR "
        "cancels fixed masks. Copy/complement traces collapsed in discovery. Global "
        "change-rate projection cannot remove all mode confounding. Correlated "
        "changes are not parity checks, codeword boundaries or semantic decoding. "
        "Circular controls preserve within-trace dependence but not joint modes. "
        "State labels from prior all-frame exploration are post-hoc diagnostics only.",
    )
    (BASE / "local/header_change_groups.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    axes[0].scatter([r["discovery"] for r in good], [r["evaluation"] for r in good],
                    s=20, alpha=0.65)
    axes[0].axhline(0.8, color="gray", linestyle="--")
    axes[0].set(xlabel="Discovery residual correlation", ylabel="Evaluation residual correlation",
                title="Most selected links do not transfer", ylim=(-0.5, 1.05))
    for number, row in enumerate((r for r in good if r["evaluation"] >= 0.8), 1):
        points = [row["a"], row["b"]]
        axes[1].plot([c["fft_bin"] for c in points], [c["symbol"] for c in points],
                     "o-", label=f"Pair {number}")
    axes[1].set(xlabel="Native FFT bin", ylabel="OFDM symbol",
                title="Three remaining pairs; no codeword boundary", yticks=range(2, 8))
    axes[1].legend()
    fig.savefig(BASE / "local/header_change_groups.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
