"""Fixed-coordinate, cross-receiver comparisons within existing DS10 visits."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parents[1] / "starlink_firmware/apk_fw_v1/reports/2026_09_28_sequence_semantics"))
from local_header_recovery import audit, select_positions  # noqa: E402


def agreement_matrix(x, y, keep):
    """Rows use RX0-only masks, including for all off-diagonal controls."""
    counts = keep.sum(axis=(1, 2))
    matches = np.array([
        [int(((a.real >= 0) == (b.real >= 0))[mask].sum()) for b in y]
        for a, mask in zip(x, keep, strict=True)
    ])
    return matches, np.broadcast_to(counts[:, None], matches.shape).copy()


def aggregate(matches, counts, mask):
    n = int(counts[mask].sum())
    return dict(pairs=int(mask.sum()), decisions=n,
                agreement=float(matches[mask].sum() / n) if n else None)


def correlation(a, b):
    a, b = a.ravel(), b.ravel()
    a, b = a - a.mean(), b - b.mean()
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.vdot(a, b).real / denom) if denom else None


def analyze(path):
    h = audit(path)
    if "evaluation_frames" not in h:
        return None
    summary_path = path.parent / "summary.json"
    source = json.loads(summary_path.read_text())
    assert h["sha256"] == source["header"]["sha256"]
    with np.load(path) as d:
        assert np.array_equal(d["bins0"], d["bins1"])
        a, b = d["z0"], d["z1"]
    frames = np.array(h["evaluation_frames"])
    variable, threshold = select_positions(a[h["discovery_frames"], :6])
    x, y = a[frames, :6], b[frames, :6]
    keep = variable[None] & (abs(x.real) / np.maximum(abs(x), 1e-20) >= threshold)
    matches, counts = agreement_matrix(x, y, keep)
    diagonal = np.eye(len(frames), dtype=bool)
    lag = abs(frames[:, None] - frames[None, :])
    phases = {w["frame"]: w["phase_hypothesis"] for w in source["windows"]
              if w["label"] == 1}
    states = []
    for start, stop in [(0, 6), (6, 32), (32, 128), (128, 192)]:
        groups = {"same": [], "different": []}
        fs = sorted(phases)
        for i, f in enumerate(fs):
            for g in fs[i + 1:]:
                value = (correlation(a[f, start:stop], b[g, start:stop])
                         + correlation(a[g, start:stop], b[f, start:stop])) / 2
                groups["same" if phases[f] == phases[g] else "different"].append(value)
        states.append(dict(symbols=[start + 2, stop + 1], **{
            k: dict(pairs=len(v), mean=float(np.mean(v)) if v else None)
            for k, v in groups.items()}))
    result = dict(
        visit=path.parent.name, source_sha256=h["sha256"],
        summary_sha256=hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        recovered_frames=len(a), qualified_frames=h["qualified_frames"],
        discovery_frames=h["discovery_frames"], evaluation_frames=frames.tolist(),
        variable_coordinates=int(variable.sum()),
        same_frame=aggregate(matches, counts, diagonal),
        different_frame=aggregate(matches, counts, ~diagonal),
        coordinate_bias_baseline=h["matched"]["coordinate_baseline"],
        lag_summary=[dict(frame_lag=int(k), milliseconds=float(k / 750 * 1000),
                          **aggregate(matches, counts, lag == k))
                     for k in np.unique(lag) if k],
        state_conditioned=states,
    )
    return result, dict(frames=frames, matches=matches, counts=counts, keep=keep)


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = BASE / "local/within-visit"
    out.mkdir(exist_ok=True)
    rows = []
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    for ax, visit in zip(axes, [1085, 1150, 1162], strict=True):
        name = f"DS10-F010-v{visit}"
        r, arrays = analyze(BASE / f"local/paired/{name}/{name}-data-soft.npz")
        rows.append(r)
        np.savez_compressed(out / f"{name}.npz", **arrays)
        values = np.divide(arrays["matches"], arrays["counts"],
                           out=np.full(arrays["counts"].shape, np.nan),
                           where=arrays["counts"] > 0)
        im = ax.imshow(values, vmin=.3, vmax=1, cmap="viridis")
        ticks = np.arange(0, len(arrays["frames"]), max(1, len(arrays["frames"]) // 5))
        ax.set_xticks(ticks, arrays["frames"][ticks])
        ax.set_yticks(ticks, arrays["frames"][ticks])
        ax.set(title=name, xlabel="RX1 physical frame index", ylabel="RX0 physical frame index")
    fig.colorbar(im, ax=axes, label="Early sign agreement (RX0-selected positions)")
    fig.savefig(out / "early-frame-agreement.png", dpi=180)
    payload = dict(
        visits=rows, method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitations="Template-relative signs, not validated message bits. Frames and pairs "
        "are dependent; descriptive controls, no significance claims. No verified satellite ID. "
        "Early comparison uses held-out frames; state analysis uses all jointly qualified "
        "state-classified frames and disjoint symbol regions. No alignment search.",
    )
    (out / "summary.json").write_text(json.dumps(payload, indent=2) + "\n")
    for r in rows:
        print(json.dumps({k: v for k, v in r.items() if k != "lag_summary"}))


if __name__ == "__main__":
    main()
