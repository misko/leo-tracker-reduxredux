"""Test frozen public parity and discovery-only pair relations on DS10."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent


def learn_pairs(values):
    bits = values.real >= 0
    p = bits.mean(axis=0)
    valid = (p >= .2) & (p <= .8)
    rows = []
    for i in np.flatnonzero(valid):
        for j in np.flatnonzero(valid):
            if j <= i:
                continue
            parity = bits[:, i] ^ bits[:, j]
            target = int(parity.mean() > .5)
            accuracy = float((parity == target).mean())
            if accuracy >= .9:
                rows.append(dict(i=int(i), j=int(j), parity=target, train_agreement=accuracy))
    return rows


def measure(bits, parity):
    bits = np.asarray(bits, dtype=np.uint8)
    observed = np.bitwise_xor.reduce(bits, axis=1) == parity
    baseline = (1 + (-1) ** parity * np.prod(1 - 2 * bits.mean(axis=0))) / 2
    controls = []
    for k in range(1, len(bits)):
        shifted = bits.copy()
        shifted[:, 0] = np.roll(bits[:, 0], k)
        controls.append(float((np.bitwise_xor.reduce(shifted, axis=1) == parity).mean()))
    return dict(count=len(bits), agreement=float(observed.mean()),
                independent_baseline=float(baseline),
                shifted_mean=float(np.mean(controls)), shifted_max=float(np.max(controls)),
                varying_constituents=int(np.any(bits != bits[0], axis=0).sum()))


def main():
    reference = BASE.parent / "2026_09_28_sequence_semantics/local/lower_edge_parity.json"
    equations = [r for r in json.loads(reference.read_text())["rows"]
                 if r["evaluation_count"] == 39 and r["evaluation_errors"] == 0]
    visits, cached = [], {}
    for path in sorted((BASE / "local/paired").glob("*/*-data-soft.npz")):
        summary = json.loads((path.parent / "summary.json").read_text())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == summary["header"]["sha256"]
        header = summary["header"]
        if "evaluation_frames" not in header:
            continue
        with np.load(path) as data:
            assert np.array_equal(data["bins0"], data["bins1"])
            bins, a, b = data["bins0"], data["z0"], data["z1"]
        train, test = header["discovery_frames"], header["evaluation_frames"]
        coords = [(s + 2, int(k)) for s in range(6) for k in bins]
        lookup = {c: i for i, c in enumerate(coords)}
        x, y = a[test, :6].reshape(len(test), -1), b[test, :6].reshape(len(test), -1)
        cached[path.parent.name] = (lookup, x, y)
        pairs = learn_pairs(a[train, :6].reshape(len(train), -1)) if len(train) >= 12 else []
        rows = []
        for rule in pairs:
            i, j, parity = rule["i"], rule["j"], rule["parity"]
            rows.append(dict(**rule, coordinates=[coords[i], coords[j]],
                             rx1=measure(y[:, [i, j]].real >= 0, parity),
                             cross_rx=measure(np.column_stack([x[:, i], y[:, j]]).real >= 0,
                                              parity)))
        frozen = []
        for eq in equations:
            if not all(tuple(c) in lookup for c in eq["coordinates"]):
                continue
            indices = [lookup[tuple(c)] for c in eq["coordinates"]]
            frozen.append(dict(coordinates=eq["coordinates"], parity=eq["parity"],
                               rx0=measure(x[:, indices].real >= 0, eq["parity"]),
                               rx1=measure(y[:, indices].real >= 0, eq["parity"])))
        visits.append(dict(visit=path.parent.name, source_sha256=digest,
                           train_frames=train, test_frames=test, learned_pairs=rows,
                           pair_discovery_abstains=len(train) < 12, frozen_parity=frozen))
    transfers = []
    for donor in visits:
        if not donor["learned_pairs"]:
            continue
        for target in visits:
            if donor["visit"] == target["visit"]:
                continue
            lookup, x, y = cached[target["visit"]]
            rows = []
            for rule in donor["learned_pairs"]:
                i, j = [lookup[tuple(c)] for c in rule["coordinates"]]
                rows.append(dict(coordinates=rule["coordinates"], parity=rule["parity"],
                                 rx0=measure(x[:, [i, j]].real >= 0, rule["parity"]),
                                 rx1=measure(y[:, [i, j]].real >= 0, rule["parity"]),
                                 cross_rx=measure(
                                     np.column_stack([x[:, i], y[:, j]]).real >= 0,
                                     rule["parity"])))
            transfers.append(dict(donor=donor["visit"], target=target["visit"], rows=rows))
    result = dict(visits=visits, transfers=transfers,
                  reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="No local parity fitting for the public relation. Pair search uses "
                  "RX0 discovery only, >=12 frames, variable coordinates, >=90% agreement; "
                  "all selected pairs reported. Evaluation frames reused by prior analyses. "
                  "Dependent pairs/frames, descriptive controls; no FEC or message claim.")
    out = BASE / "local/within-visit/early-redundancy.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    for r in visits:
        print(r["visit"], "pairs", len(r["learned_pairs"]), "frozen", r["frozen_parity"])
        if r["learned_pairs"]:
            for key in ("rx1", "cross_rx"):
                print(key, {k: float(np.mean([p[key][k] for p in r["learned_pairs"]]))
                            for k in ("agreement", "independent_baseline", "shifted_mean")})


if __name__ == "__main__":
    main()
