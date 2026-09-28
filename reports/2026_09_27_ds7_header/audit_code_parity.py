"""Evaluate a frozen even-parity hypothesis on additional DS7 frames."""

import hashlib
import json
from pathlib import Path


def canonical_rotation(word):
    return min(word[i:] + word[:i] for i in range(len(word)))


def main():
    out = Path(__file__).parent / "local"
    hypothesis_path = out / "even-parity-hypothesis.json"
    hypothesis = json.loads(hypothesis_path.read_text())
    sources = {group: out / group / "tcodes.json" for group in hypothesis["discovery_frames"]}
    records = {group: json.loads(p.read_text())["results"] for group, p in sources.items()}
    discovery = [
        row["combined_word"]
        for group, frames in hypothesis["discovery_frames"].items()
        for row in records[group]
        if row["frame"] in frames
    ]
    old_classes = set(map(canonical_rotation, discovery))
    validation = []
    for row in records[hypothesis["validation_group"]]:
        if row["frame"] not in hypothesis["validation_frames"]:
            continue
        word = row["combined_word"]
        validation.append(
            dict(
                frame=row["frame"],
                candidate_passed=row["repeated_code_candidate"],
                receiver_agreement=row["receiver_bit_agreement"],
                rx0_even_parity=row["rx0_word"].count("1") % 2 == 0,
                rx1_even_parity=row["rx1_word"].count("1") % 2 == 0,
                word=word,
                previously_unseen_rotation_class=canonical_rotation(word) not in old_classes,
            )
        )
    assert [r["frame"] for r in validation] == hypothesis["validation_frames"]
    passed = all(
        r["candidate_passed"]
        and r["receiver_agreement"] == 1
        and r["rx0_even_parity"]
        and r["rx1_even_parity"]
        for r in validation
    )
    result = dict(
        hypothesis_sha256=hashlib.sha256(hypothesis_path.read_bytes()).hexdigest(),
        input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources.values()},
        validation=validation,
        all_specified_frames_pass=passed,
        new_rotation_classes=len({canonical_rotation(r["word"]) for r in validation} - old_classes),
        interpretation="A validated even-parity relation in tested repeated codes. "
        "It is not an established designated parity field, packet CRC, satellite ID, or timestamp.",
        limitation="Repeated and cyclically related words are dependent observations; "
        "do not treat each passing frame as an independent fair-bit trial.",
    )
    (out / "even-parity-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("validation", "input_sha256")}))


if __name__ == "__main__":
    main()
