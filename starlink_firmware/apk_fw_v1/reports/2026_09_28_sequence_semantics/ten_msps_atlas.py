"""Bounded full-slice soft-symbol atlas for pilot-selected 10 MS/s excerpts."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from firmware_seed_search import SEED
from phase_model import codebook

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str((BASE.parents[3] / "reports") / "2026_09_28_ds7_ds8_correspondence"))
from native_rate_decode import recover  # noqa: E402
from tcodes import slots  # noqa: E402

OUT = BASE / "local/ten-msps-atlas"


def score(values, predictions):
    return np.mean(values.real[None] * predictions, axis=(1, 2)) / max(
        float(np.sqrt(np.mean(abs(values) ** 2))), 1e-12
    )


def classify(a, b, mapping, words, rng):
    """Fit RX0 even symbols; check disjoint RX0 symbols and RX1 independently."""
    predictions = words[:, mapping]
    first = np.arange(len(a)) % 2 == 0
    covered = len(np.unique(mapping[first])) == 60
    phase = int(np.argmax(score(a[first], predictions[:, first])))
    peer = int(np.argmax(score(b[first], predictions[:, first])))
    held0 = float(score(a[~first], predictions[:, ~first])[phase])
    held1 = float(score(b, predictions)[phase])
    wrong = np.array([rng.permutation(words[phase]) for _ in range(99)])[:, mapping]
    control = float(np.max(score(b, wrong)))
    purity = float(np.mean((a.real**2 + b.real**2) /
                           np.maximum(abs(a)**2 + abs(b)**2, 1e-20)))
    repeat = covered and phase == peer and min(held0, held1) > .25 and held1 > control
    label = 1 if repeat else 2 if purity >= .8 else 3
    return dict(label=label, phase_hypothesis=phase, peer_phase=peer,
                rx0_held=held0, rx1_held=held1, shuffled_max=control,
                real_power_fraction=purity, all_slots_in_discovery=covered)


def main():
    OUT.mkdir(exist_ok=True)
    inv_path = (BASE.parents[3] / "reports") / "2026_09_28_signal_clustering/local/inventory.json"
    inv = json.loads(inv_path.read_text())
    candidates = []
    for path in sorted((BASE / "local").glob("*-soft.npz")):
        name = path.stem.removesuffix("-soft")
        if name.startswith("DS9-"):
            folder = BASE / f"local/ds9-{name[4:]}-10m"
            streams = [dict(row=r, folder=str(folder))
                       for r in json.loads((folder / "inventory.json").read_text())["exports"]]
        elif name.startswith("S") and name[1:].isdigit():
            streams = next(r["streams"] for r in inv if r["signal"] == name)
        else:
            continue
        if any(s["row"]["sample_rate_hz"] != 10000000 for s in streams):
            continue
        d = np.load(path)
        if "binding" in d:
            original = next(r for r in inv if r["signal"] == name)
            assert str(d["binding"]) == hashlib.sha256(
                json.dumps(original, sort_keys=True).encode()).hexdigest()
        else:
            assert str(d["inventory_sha256"]) == hashlib.sha256(
                (Path(streams[0]["folder"]) / "inventory.json").read_bytes()).hexdigest()
        meta = [json.loads(str(d[f"metadata{i}"])) for i in (0, 1)]
        frames = sorted(set(meta[0]["evaluation_frames"]) & set(meta[1]["evaluation_frames"]))
        quality = [min(m["diagnostics"][f]["held_pilot_coherence"] for m in meta) for f in frames]
        candidates.append(dict(name=name, edge=streams[0]["row"]["probe"]["edge"],
                               median_weaker_pilot=float(np.median(quality)), streams=streams))
    chosen = [max((r for r in candidates if r["edge"] == edge),
                  key=lambda r: r["median_weaker_pilot"]) for edge in ("upper", "lower")]
    words = np.array([[1 if b == "1" else -1 for b in w]
                      for w in codebook(list(map(int, SEED)))])
    rng = np.random.default_rng(20261001)
    visits = []
    for choice in chosen:
        name = choice["name"]
        cache = OUT / f"{name}.npz"
        binding = hashlib.sha256(json.dumps(choice, sort_keys=True).encode()).hexdigest()
        if not cache.exists():
            arrays = dict(binding=binding)
            for rx, stream in enumerate(choice["streams"]):
                bins, z, meta = recover(stream["row"], Path(stream["folder"]), 90,
                                        all_supported_bins=True)
                arrays.update({f"bins{rx}": bins, f"z{rx}": z,
                               f"metadata{rx}": json.dumps(meta)})
                print(name, "RX", rx, "frames/carriers", z.shape, flush=True)
            np.savez_compressed(cache, **arrays)
        d = np.load(cache)
        assert str(d["binding"]) == binding
        meta = [json.loads(str(d[f"metadata{i}"])) for i in (0, 1)]
        bins, ix, iy = np.intersect1d(d["bins0"], d["bins1"], return_indices=True)
        pilots = np.union1d(meta[0]["pilot_bins"], meta[1]["pilot_bins"])
        use = ~np.isin(bins, pilots)
        a, b = d["z0"][:, :, ix[use]], d["z1"][:, :, iy[use]]
        frames = sorted(set(meta[0]["evaluation_frames"]) & set(meta[1]["evaluation_frames"]))
        quality = np.array([min(m["diagnostics"][f]["held_pilot_coherence"] for m in meta)
                            for f in frames])
        records, labels = [], np.zeros((len(frames), 10), dtype=int)
        for fi, frame in enumerate(frames):
            for wi, start in enumerate(range(2, 302, 32)):
                end = min(start + 32, 302)
                mapping = slots(bins[use], np.arange(start, end))
                r = classify(a[frame, start-2:end-2], b[frame, start-2:end-2], mapping, words, rng)
                if quality[fi] <= .5:
                    r["label"] = 0
                labels[fi, wi] = r["label"]
                records.append(dict(frame=frame, first_symbol=start, last_symbol=end-1, **r))
        active = np.array(frames)[quality > .5]
        x, y = a[active], b[active]
        # Across-frame centering suppresses fixed-template agreement in this map.
        xc, yc = x - x.mean(axis=0), y - y.mean(axis=0)
        shared = np.real(np.sum(xc.conj() * yc, axis=0)) / np.maximum(
            np.sqrt(np.sum(abs(xc)**2, axis=0) * np.sum(abs(yc)**2, axis=0)), 1e-20)
        old = np.load(BASE / f"local/{name}-soft.npz")
        old_paired = np.intersect1d(old["bins0"], old["bins1"])
        added = ~np.isin(bins[use], old_paired)
        changes = []
        for rx in (0, 1):
            common, new_ix, old_ix = np.intersect1d(d[f"bins{rx}"], old[f"bins{rx}"],
                                                  return_indices=True)
            nz, oz = d[f"z{rx}"][:, :, new_ix], old[f"z{rx}"][:, :, old_ix]
            changes.append(dict(common_bins=len(common),
                                relative_rms_change=float(np.linalg.norm(nz-oz)/np.linalg.norm(oz))))
        np.savez_compressed(OUT / f"{name}-maps.npz", labels=labels, shared=shared,
                            frames=frames, data_bins=bins[use], weaker_pilot=quality)
        visits.append(dict(name=name, edge=choice["edge"], selection=choice["median_weaker_pilot"],
                           source_binding=binding, source_streams=choice["streams"],
                           cache_sha256=hashlib.sha256(cache.read_bytes()).hexdigest(),
                           receiver_shapes=[list(d[f"z{i}"].shape) for i in (0, 1)],
                           common_bins=bins.tolist(), pilot_bins=pilots.tolist(),
                           paired_data_bins=bins[use].tolist(), qualified_frames=active.tolist(),
                           calibration_change=changes,
                           added_paired_bins=bins[use][added].tolist(),
                           added_carrier_mean_correlation=float(shared[:, added].mean()),
                           original_carrier_mean_correlation=float(shared[:, ~added].mean()),
                           label_counts={str(k): int((labels == k).sum()) for k in range(4)},
                           windows=records))
        print(name, visits[-1]["label_counts"], flush=True)
    output = dict(candidates=[{k: v for k, v in r.items() if k != "streams"} for r in candidates],
                  visits=visits, labels={0: "pilot quality insufficient",
                                       1: "known-repeat compatible",
                                       2: "binary-like unresolved", 3: "mixed/uncertain"},
                  limitation="Pilot-selected cached subset, not strongest globally. Symbols2..301 "
                  "and all supported in-channel bins within +/-0.45Fs including pilots retained. "
                  "Pilot calibration and SSS linear channel extrapolation are models. No PSS "
                  "or guard-interval recovery claimed. Uses paired data intersection; "
                  "single-receiver bins remain stored. Repeat classification is not message/FEC "
                  "decoding. Unresolved or mixed labels do not establish higher-order QAM. "
                  "Upper/lower visits are not simultaneous and cannot form a combined RF frame.")
    (OUT / "atlas.json").write_text(json.dumps(output, indent=2) + "\n")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    fig, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
    for row, visit in enumerate(visits):
        maps = np.load(OUT / f"{visit['name']}-maps.npz")
        axes[row, 0].imshow(maps["labels"], aspect="auto", vmin=0, vmax=3,
                            cmap=ListedColormap(["#bbbbbb", "#2a9d8f", "#e9c46a", "#735d9c"]))
        axes[row, 0].set(title=f"{visit['name']} {visit['edge']}: region classification",
                         xlabel="32-symbol window (last window shorter)",
                         ylabel="Evaluation frame index")
        image = axes[row, 1].imshow(maps["shared"].T, aspect="auto", vmin=-1, vmax=1,
                                   cmap="coolwarm", extent=[2, 302, len(maps["data_bins"]), 0])
        axes[row, 1].set(title="Centered cross-receiver soft correlation",
                         xlabel="OFDM symbol", ylabel="Observed data-carrier index")
    fig.colorbar(image, ax=axes[:, 1], label="Correlation across qualified frames")
    fig.suptitle("Green: known-repeat compatible | Yellow: binary-like | Purple: mixed/uncertain")
    fig.savefig(OUT / "atlas.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
