"""Held-symbol test of local mixtures of known repeating-pattern predictions."""

import hashlib
import json
from pathlib import Path

import numpy as np
from decode_tracks import SEED, codebook, slots
from recover import references
from state_residuals import ATLAS, shared

BASE = Path(__file__).parent


def design(words, phases, bins, symbols, offsets):
    mapping = slots(bins, symbols)
    return np.stack(
        [words[phases][:, (mapping + dc - 16 * dt) % 60] for dt, dc in offsets], axis=-1
    ).astype(float)


def fit_predict(x, y, train):
    coefficients, ranks = [], []
    for features, observed in zip(x, y, strict=True):
        fit, _, rank, _ = np.linalg.lstsq(
            features[train].reshape(-1, x.shape[-1]), observed[train].ravel(), rcond=1e-6
        )
        coefficients.append(fit)
        ranks.append(int(rank))
    coefficients = np.array(coefficients)
    return np.einsum("fsck,fk->fsc", x, coefficients), coefficients, ranks


def physical_design(words, phases, bins, offsets, edge):
    """Restore source/target template phase ratios, including adjacent pilots."""
    sss, template, pilot = references(edge)
    pilot_bins = np.arange(488, 496) if edge == "upper" else np.arange(528, 536)
    symbols = np.arange(2, 302)
    columns = []
    for dt, dc in offsets:
        source_bins = bins + dc
        source_symbols = symbols + dt
        values = np.zeros((len(phases), len(symbols), len(bins)), dtype=complex)
        valid = (source_symbols >= 2) & (source_symbols <= 301)
        for j, carrier in enumerate(source_bins):
            if carrier in pilot_bins:
                values[:, valid, j] = pilot[source_symbols[valid] - 2, carrier - pilot_bins[0]]
            else:
                mapping = slots(np.array([carrier]), source_symbols[valid])[:, 0]
                values[:, valid, j] = (
                    words[phases][:, mapping] * template[carrier, source_symbols[valid] - 1]
                )
            values[:, source_symbols == 1, j] = sss[carrier]
        values *= template[bins, 1:].T.conj()[None]
        columns.append(values)
    return np.stack(columns, axis=-1)


def measure(a, b, x, predictions, coefficients, start, stop):
    ra, rb = [z[:, start:stop] - p[:, start:stop] for z, p in zip((a, b), predictions, strict=True)]
    controls = []
    for shift in range(1, len(a)):
        null_prediction = np.einsum(
            "fsck,fk->fsc", x[:, start:stop], np.roll(coefficients[1], shift, axis=0)
        )
        null = np.roll(b[:, start:stop], shift, axis=0) - null_prediction
        controls.append(shared(ra, null))
    return dict(
        first_symbol=start + 2,
        last_symbol=stop + 1,
        residual_shared=shared(ra, rb),
        control_mean=float(np.mean(controls)),
        control_max=float(np.max(controls)),
        removed_energy=[
            float(1 - np.sum(abs(r) ** 2) / np.sum(abs(z[:, start:stop]) ** 2))
            for r, z in [(ra, a), (rb, b)]
        ],
    )


def main():
    source = ATLAS / "atlas.json"
    atlas = json.loads(source.read_text())
    out = BASE / "local/neighbor-model"
    out.mkdir(exist_ok=True)
    words = np.array(
        [[1 if bit == "1" else -1 for bit in word] for word in codebook(list(map(int, SEED)))]
    )
    result = dict(
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        atlas_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        visits=[],
    )
    models = {
        "scalar": [(0, 0)],
        "carrier5": [(0, c) for c in range(-2, 3)],
        "time_carrier15": [(t, c) for t in range(-1, 2) for c in range(-2, 3)],
    }
    models["physical15"] = models["time_carrier15"]
    for visit in atlas["visits"]:
        path = ATLAS / f"{visit['name']}.npz"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == visit["cache_sha256"]
        data = np.load(path)
        m = [json.loads(str(data[f"metadata{rx}"])) for rx in range(2)]
        bins = np.intersect1d(data["bins0"], data["bins1"])
        bins = bins[~np.isin(bins, np.union1d(m[0]["pilot_bins"], m[1]["pilot_bins"]))]
        state = {
            w["frame"]: w["phase_hypothesis"]
            for w in visit["windows"]
            if w["first_symbol"] == 194 and w["label"] == 1
        }
        frames = [f for f in visit["qualified_frames"] if f in state]
        phases = np.array([state[f] for f in frames])
        a, b = [
            data[f"z{rx}"][frames][:, :, np.searchsorted(data[f"bins{rx}"], bins)]
            for rx in range(2)
        ]
        summaries = []
        for name, offsets in models.items():
            x = (
                physical_design(words, phases, bins, offsets, visit["edge"])
                if name == "physical15"
                else design(words, phases, bins, np.arange(2, 302), offsets)
            )
            fits = [fit_predict(x, z, slice(224, 256)) for z in (a, b)]
            predictions = [f[0] for f in fits]
            coefficients = [f[1] for f in fits]
            regions = [
                measure(a, b, x, predictions, coefficients, start, stop)
                for start, stop in [(0, 6), (6, 32), (32, 128), (128, 192), (256, 288)]
            ]
            summaries.append(dict(model=name, offsets=offsets, regions=regions, ranks=fits[0][2]))
            np.savez_compressed(
                out / f"{visit['name']}-{name}.npz",
                frames=frames,
                bins=bins,
                phases=phases,
                coefficients=coefficients,
                residual0=a - predictions[0],
                residual1=b - predictions[1],
            )
        result["visits"].append(dict(name=visit["name"], frames=len(frames), models=summaries))
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    for visit in result["visits"]:
        print(visit["name"])
        for model in visit["models"]:
            print(
                model["model"],
                "rank",
                min(model["ranks"]),
                max(model["ranks"]),
                json.dumps(model["regions"][-1]),
                flush=True,
            )


if __name__ == "__main__":
    main()
