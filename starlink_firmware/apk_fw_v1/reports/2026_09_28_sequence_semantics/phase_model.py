"""Test an explicit cyclic-phase generator for the recovered 60-bit vocabulary."""

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
OUT = BASE / "local"
CLUSTER = (BASE.parents[3] / "reports") / "2026_09_28_signal_clustering/local"
JOINT = (BASE.parents[3] / "reports") / "2026_09_28_ds7_ds8_correspondence/local"


def derive_seed(unit_word):
    """Solve B1[i] = 1 XOR S[i] XOR S[i+1], fixing unobservable S[0]=0."""
    if len(unit_word) != 60 or set(unit_word) - {"0", "1"}:
        raise ValueError("A complete 60-bit word is required")
    seed = [0]
    for bit in unit_word[:-1]:
        seed.append(seed[-1] ^ int(bit) ^ 1)
    if (1 ^ seed[-1] ^ seed[0]) != int(unit_word[-1]):
        raise ValueError("Word does not close cyclically")
    return np.array(seed, dtype=np.uint8)


def codebook(seed):
    seed = np.asarray(seed, dtype=np.uint8)
    return ["".join(map(str, 1 ^ seed ^ np.roll(seed, -k))) for k in range(len(seed))]


def main():
    source = CLUSTER / "observations.csv"
    with source.open() as stream:
        rows = [r for r in csv.DictReader(stream) if r["accepted"] == "True"]
    # Explicit discovery observations. Chosen after inspecting catalogue structure;
    # this is an exploratory generator test, not a prospective blind discovery.
    basis = [
        next(r for r in rows if r["signal"] == "UT-ref" and int(r["frame"]) == f) for f in [89, 117]
    ]
    assert basis[0]["word"][1:] + basis[0]["word"][:1] == basis[1]["word"]
    seed = derive_seed(basis[1]["word"])
    words = codebook(seed)
    assert len(set(words)) == 60
    lookup = {w: k for k, w in enumerate(words)}
    decoded = []
    for r in rows:
        decoded.append(
            dict(
                signal=r["signal"],
                frame=int(r["frame"]),
                word=r["word"],
                phase_index=lookup.get(r["word"]),
                family_id=r["family_id"],
                strict=r["strict_pilot_accepted"] == "True",
            )
        )
    with (OUT / "phase_indices.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(decoded[0]))
        writer.writeheader()
        writer.writerows(decoded)
    validations = []
    for path in sorted(OUT.glob("*-windows.json")):
        data = json.loads(path.read_text())
        good = [r for r in data["results"] if r["accepted"]]
        wrong = [r for r in good if r["word"] not in lookup]
        validations.append(
            dict(
                signal=data["signal"],
                observations=len(good),
                exact_generator_matches=len(good) - len(wrong),
                unmatched=[
                    dict(
                        frame=r["frame"],
                        first_symbol=r["first_symbol"],
                        word=r["word"],
                        strict=r.get("strict_pilot"),
                        nearest_hamming=min(
                            sum(a != b for a, b in zip(r["word"], w, strict=True)) for w in words
                        ),
                    )
                    for r in wrong
                ],
            )
        )
    exact = np.array(
        [[sum(a != b for a, b in zip(x, y, strict=True)) for y in words] for x in words]
    )
    families = defaultdict(list)
    for r in decoded:
        if r["phase_index"] is not None:
            families[r["family_id"]].append(r["phase_index"])
    result = dict(
        generator="B_k[i] = 1 XOR S[i] XOR S[(i+k) mod 60]",
        seed="".join(map(str, seed)),
        seed_ones=int(seed.sum()),
        gauge="S[0]=0; complementing S leaves every generated word unchanged",
        training_observations=[
            dict(signal=r["signal"], frame=int(r["frame"]), word=r["word"]) for r in basis
        ],
        discovery_scope="Exploratory whole-catalogue inspection suggested the model. "
        "Two UT words determine the seed; other words test its algebraic predictions. "
        "Previously inspected observations are not a prospective holdout.",
        generated_words=words,
        total_observations=len(rows),
        exact_matches=sum(r["phase_index"] is not None for r in decoded),
        observed_states=sorted({r["phase_index"] for r in decoded if r["phase_index"] is not None}),
        ds_observations=sum(r["signal"] != "UT-ref" for r in decoded),
        ut_observations=sum(r["signal"] == "UT-ref" for r in decoded),
        phase_counts=dict(sorted(Counter(r["phase_index"] for r in decoded).items())),
        families={f: sorted(set(k)) for f, k in families.items()},
        minimum_code_distance=int(exact[np.triu_indices(60, 1)].min()),
        window_validation=validations,
        interpretation="A 60-state cyclic phase representation of the tessellation pattern, "
        "not evidence that a literal six-bit field is transmitted. "
        "State selection, protocol role, satellite identity and UTC remain unknown.",
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [source, *sorted(OUT.glob("*-windows.json"))]
        },
    )
    (OUT / "phase_model.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ["generated_words", "families", "input_sha256", "phase_counts"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
