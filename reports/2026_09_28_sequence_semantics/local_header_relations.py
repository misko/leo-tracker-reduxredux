"""Select a soft header-position relation on RX0; evaluate without reselection."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent


def normalized(values):
    return values.real / np.maximum(abs(values), 1e-20)


def correlation(a, b):
    a, b = a - np.mean(a), b - np.mean(b)
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a @ b / denominator) if denominator > 1e-12 else None


def select_pair(values):
    frequency = (values >= 0).mean(axis=0)
    active = np.flatnonzero((frequency >= 0.2) & (frequency <= 0.8))
    if len(active) < 2:
        return None
    centered = values[:, active] - values[:, active].mean(axis=0)
    centered /= np.maximum(np.linalg.norm(centered, axis=0), 1e-20)
    matrix = centered.T @ centered
    left, right = np.triu_indices(len(active), 1)
    winner = np.argmax(abs(matrix[left, right]))
    a, b = left[winner], right[winner]
    return dict(
        left=int(active[a]),
        right=int(active[b]),
        discovery_correlation=float(matrix[a, b]),
        searched_pairs=len(left),
    )


def evaluate(x, y, pair):
    a, b = pair["left"], pair["right"]
    polarity = 1 if pair["discovery_correlation"] >= 0 else -1
    rows = {}
    for name, left, right in [
        ("rx0", x[:, a], x[:, b]),
        ("rx1", y[:, a], y[:, b]),
        ("cross01", x[:, a], y[:, b]),
        ("cross10", y[:, a], x[:, b]),
    ]:
        value = correlation(left, right)
        p, q = float(np.mean(left >= 0)), float(np.mean(polarity * right >= 0))
        rows[name] = dict(
            oriented_correlation=None if value is None else polarity * value,
            sign_agreement=float(np.mean((left >= 0) == (polarity * right >= 0))),
            positive_fractions=[p, q],
            independent_sign_baseline=p * q + (1 - p) * (1 - q),
        )
    return rows


def main():
    audit = json.loads((BASE / "local/local_header_recovery.json").read_text())
    rows = []
    for item in audit["rows"]:
        if "discovery_frames" not in item:
            continue
        path = BASE / "local" / f"{item['signal']}-soft.npz"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
        archive = np.load(path)
        bins, i, j = np.intersect1d(archive["bins0"], archive["bins1"], return_indices=True)
        streams = [
            normalized(archive[f"z{k}"][:, :6, indices]).reshape(len(archive[f"z{k}"]), -1)
            for k, indices in enumerate((i, j))
        ]
        train, held = item["discovery_frames"], item["evaluation_frames"]
        pair = select_pair(streams[0][train])
        if pair is None:
            continue
        coordinates = [
            dict(
                ofdm_symbol=pair[key] // len(bins) + 2, native_bin=int(bins[pair[key] % len(bins)])
            )
            for key in ("left", "right")
        ]
        evaluation = evaluate(streams[0][held], streams[1][held], pair)
        # One frozen pair per visit; permutation reference uses held-out RX1 only.
        rng = np.random.default_rng(280928)
        a, b = streams[1][held, pair["left"]], streams[1][held, pair["right"]]
        observed = evaluation["rx1"]["oriented_correlation"]
        polarity = np.sign(pair["discovery_correlation"])
        null = [correlation(a, rng.permutation(b)) for _ in range(999)]
        null = [polarity * value for value in null if value is not None]
        row = dict(
            signal=item["signal"],
            source_sha256=item["sha256"],
            discovery_frames=train,
            evaluation_frames=held,
            pair=pair,
            coordinates=coordinates,
            evaluation=evaluation,
            rx1_one_sided_permutation_p=None
            if observed is None
            else (1 + sum(v >= observed for v in null)) / (1 + len(null)),
        )
        rows.append(row)
        print(json.dumps(row))
    transfers = []
    for source in rows:
        for target in audit["rows"]:
            if "evaluation_frames" not in target or target["signal"] == source["signal"]:
                continue
            archive = np.load(BASE / "local" / f"{target['signal']}-soft.npz")
            coords = source["coordinates"]
            if not all(c["native_bin"] in archive[f"bins{k}"] for c in coords for k in range(2)):
                continue
            values = []
            for k in range(2):
                positions = [
                    int(np.flatnonzero(archive[f"bins{k}"] == c["native_bin"])[0]) for c in coords
                ]
                z = archive[f"z{k}"][target["evaluation_frames"]]
                values.append(
                    normalized(
                        np.stack(
                            [
                                z[:, c["ofdm_symbol"] - 2, p]
                                for c, p in zip(coords, positions, strict=True)
                            ],
                            axis=1,
                        )
                    )
                )
            pair = dict(
                left=0, right=1, discovery_correlation=source["pair"]["discovery_correlation"]
            )
            transfers.append(
                dict(
                    source=source["signal"],
                    target=target["signal"],
                    evaluation=evaluate(*values, pair),
                )
            )
    output = dict(
        rows=rows,
        transfers=transfers,
        limitation="One exploratory selected pair per visit. "
        "Frame permutation assumes exchangeable frames and does not address "
        "temporal dependence; six visits are examined. Correlation does not "
        "identify a code, parity constraint, plaintext, or satellite field.",
    )
    (BASE / "local/local_header_relations.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
