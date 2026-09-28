"""Evaluate frozen reference parity equations on existing local receiver caches."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent


def measure(bits, parity):
    if not len(bits):
        return dict(count=0, agreement=None, independent_baseline=None)
    observed = np.bitwise_xor.reduce(bits, axis=1)
    bias = np.prod(1 - 2 * bits.mean(axis=0))
    return dict(
        count=len(bits),
        agreement=float(np.mean(observed == parity)),
        independent_baseline=float((1 + (-1) ** parity * bias) / 2),
        varying_constituents=int(np.any(bits != bits[0], axis=0).sum()),
    )


def main():
    source = BASE / "local/header_rank_relations.json"
    equations = json.loads(source.read_text())["raw_transfers"]
    audit_path = BASE / "local/local_header_recovery.json"
    visits = json.loads(audit_path.read_text())["rows"]
    rows, coverage = [], []
    for visit in visits:
        path = BASE / "local" / f"{visit['signal']}-soft.npz"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == visit["sha256"]
        data = np.load(path)
        common = set(data["bins0"]) & set(data["bins1"])
        candidates = [r for r in equations if all(b in common for s, b in r["coordinates"])]
        coverage.append(
            dict(
                signal=visit["signal"],
                equations=len(candidates),
                evaluation_frames=len(visit.get("evaluation_frames", [])),
            )
        )
        if "evaluation_frames" not in visit:
            continue
        for equation in candidates:
            receivers = []
            observed_parities = []
            for rx in range(2):
                mapping = {int(b): i for i, b in enumerate(data[f"bins{rx}"])}
                coordinates = equation["coordinates"]
                values = data[f"z{rx}"][visit["evaluation_frames"]]
                z = np.stack([values[:, s, mapping[b]] for s, b in coordinates], axis=1)
                bits = (z.real >= 0).astype(np.uint8)
                # Gate uses this receiver's axis confidence, never parity satisfaction.
                gate = (abs(z.real) / np.maximum(abs(z), 1e-20) > 0.9).all(axis=1)
                receivers.append(
                    dict(
                        all=measure(bits, equation["parity"]),
                        axis_gated=measure(bits[gate], equation["parity"]),
                    )
                )
                observed_parities.append(np.bitwise_xor.reduce(bits, axis=1))
            rows.append(
                dict(
                    signal=visit["signal"],
                    coordinates=equation["coordinates"],
                    parity=equation["parity"],
                    receivers=receivers,
                    receiver_parity_agreement=float(
                        np.mean(observed_parities[0] == observed_parities[1])
                    ),
                )
            )
    pooled = []
    keys = sorted(set(tuple(tuple(c) for c in r["coordinates"]) for r in rows))
    for key in keys:
        members = [r for r in rows if tuple(tuple(c) for c in r["coordinates"]) == key]
        summary = []
        for rx in range(2):
            values = [r["receivers"][rx]["all"] for r in members]
            count = sum(v["count"] for v in values)
            summary.append(
                dict(
                    count=count,
                    agreement=sum(v["count"] * v["agreement"] for v in values) / count,
                    independent_baseline=sum(v["count"] * v["independent_baseline"] for v in values)
                    / count,
                )
            )
        pooled.append(dict(coordinates=key, parity=members[0]["parity"], receivers=summary))
    output = dict(
        coverage=coverage,
        rows=rows,
        pooled=pooled,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, audit_path)
        },
        limitation="Frozen reference equations; local frames reserved by earlier "
        "audit, already used for other analyses. No local parity fitting. Marginal "
        "baseline assumes independent constituent signs; noise can destroy parity "
        "and high-order parity amplifies sign errors. Agreement is not decoded BER.",
    )
    (BASE / "local/local_reference_parity.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(coverage, indent=2))
    for signal in sorted(set(r["signal"] for r in rows)):
        subset = [r for r in rows if r["signal"] == signal]
        print(
            signal,
            json.dumps(
                [
                    dict(coordinates=r["coordinates"], parity=r["parity"], receivers=r["receivers"])
                    for r in subset
                ]
            ),
        )


if __name__ == "__main__":
    main()
