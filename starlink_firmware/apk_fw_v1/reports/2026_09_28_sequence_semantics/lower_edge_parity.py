"""Discover weight-two/three reference checks inside DS9 carrier coverage."""

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
from header_rank_relations import column_words
from local_reference_parity import measure
from scipy.io import loadmat

BASE = Path(__file__).resolve().parent


def discover(bits, valid):
    counts = bits.sum(axis=0)
    eligible = valid.all(axis=0) & (counts >= 2) & (counts <= len(bits) - 2)
    vectors = column_words(bits ^ bits[0])
    groups = {}
    for i in np.flatnonzero(eligible):
        groups.setdefault(vectors[i], []).append(int(i))
    rows = []
    for ids in groups.values():
        rows.extend(list(itertools.combinations(ids, 2)))
    active = np.flatnonzero(eligible)
    for a, b in itertools.combinations(active, 2):
        for c in groups.get(vectors[a] ^ vectors[b], []):
            if c > b:
                rows.append((int(a), int(b), c))
    return rows, int(eligible.sum())


def main():
    source = BASE / "local/header-reference-0-77.npz"
    tp = (
        BASE.parents[3]
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
        / "reference-template/referenceTemplate.mat"
    )
    local_paths = [BASE / f"local/DS9-{tag}-soft.npz" for tag in ("middle", "last")]
    archives = [np.load(p) for p in local_paths]
    common = set.intersection(*(set(a[f"bins{rx}"]) for a in archives for rx in range(2)))
    bins = np.array(sorted(common))
    template = loadmat(tp)["referenceTemplateRotations"]
    z = np.load(source)["symbols"][:, :, bins] * np.exp(-0.5j * np.pi * template[bins, 1:7].T)
    bits = (z.real >= 0).astype(np.uint8).reshape(78, -1)
    valid = ((abs(z.imag) < 0.05) & (abs(abs(z.real) - 1) < 0.05)).reshape(78, -1)
    candidates, active = discover(bits[:39], valid[:39])
    rows = []
    for positions in candidates:
        parity = int(np.bitwise_xor.reduce(bits[0, list(positions)]))
        q = valid[39:, list(positions)].all(axis=1)
        errors = int(
            ((np.bitwise_xor.reduce(bits[39:, list(positions)], axis=1) != parity) & q).sum()
        )
        row = dict(
            coordinates=[(p // len(bins) + 2, int(bins[p % len(bins)])) for p in positions],
            parity=parity,
            evaluation_count=int(q.sum()),
            evaluation_errors=errors,
        )
        if q.all() and not errors:
            transfers = []
            for path, a in zip(local_paths, archives, strict=True):
                meta = [json.loads(str(a[f"metadata{i}"])) for i in range(2)]
                frames = sorted(
                    set(meta[0]["evaluation_frames"]) & set(meta[1]["evaluation_frames"])
                )
                frames = [
                    f
                    for f in frames
                    if min(m["diagnostics"][f]["held_pilot_coherence"] for m in meta) > 0.5
                ]
                for rx in range(2):
                    lookup = {int(b): i for i, b in enumerate(a[f"bins{rx}"])}
                    values = np.stack(
                        [
                            a[f"z{rx}"][frames, s - 2, lookup[b]].real >= 0
                            for s, b in row["coordinates"]
                        ],
                        axis=1,
                    ).astype(np.uint8)
                    transfers.append(dict(signal=path.stem, receiver=rx, **measure(values, parity)))
            row["local_transfers"] = transfers
        rows.append(row)
    summary = dict(
        carriers=bins.tolist(),
        discovery_eligible_positions=active,
        discovery_relations=len(rows),
        fully_qualified_exact_evaluation=sum("local_transfers" in r for r in rows),
    )
    output = dict(
        summary=summary,
        rows=rows,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, tp, *local_paths)
        },
        limitation="Weight2/3 checks only; first39 reference frames select, later39 "
        "validate. Each discovery coordinate has at least2 of each bit. Local "
        "45-frame evaluation sets used for other exploratory work. No semantics "
        "or independent BER; correlated noise can reproduce relations.",
    )
    (BASE / "local/lower_edge_parity.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
