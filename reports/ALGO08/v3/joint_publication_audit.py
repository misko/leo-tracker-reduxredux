"""Verify raw pair and saved replay artifacts independently of the publication clocks."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from tools.pipeline_eval.qualification.paired_publication import evidence
from joint_publication import artifacts


def audit(pair_root, saved_root, output):
    from joint_raw_smoke import SOURCE

    pair = json.loads((pair_root / "pair.json").read_bytes())
    saved = json.loads((saved_root / "joint-research-receipt.json").read_bytes())
    archived = json.loads(SOURCE.read_bytes())["runs"]["candidate"]
    fit = json.loads(gzip.decompress((Path(__file__).parent / "measurements/blind-joint-repair.json.gz").read_bytes()))
    repaired = fit["receipts"]["south-containing"]["result"]
    output.mkdir(exist_ok=True)
    science = {}
    for name, root, receipt, expected in (
        ("baseline", pair_root / "baseline", pair["runs"]["baseline"]["receipt"], archived["scientific_digests"]),
        ("candidate", pair_root / "candidate", pair["runs"]["candidate"]["receipt"], repaired["science"]),
        ("saved", saved_root, saved["receipt"], repaired["science"]),
    ):
        data = evidence(root, receipt, started_ns=0, read_only=True)
        if data["scientific_digests"] != expected:
            raise ValueError(f"{name} scientific position evidence differs from its saved comparator")
        science[name] = data["scientific_digests"]
        decoded = artifacts(root, receipt)
        original = pair["runs"]["candidate" if name == "saved" else name]["evidence"]
        image_records = {name: dict(record, size=list(record["size"])) for name, record in decoded["images"].items()}
        if image_records != original["images"]:
            raise ValueError(f"{name} decoded image or encoded image digest changed")
        if name != "saved":
            store = FastStandardAnalysisStore(root)
            (output / f"joint-{name}-position.png").write_bytes(
                store.artifact(receipt["run_id"], "position", decoded["images"]["position"]["sha256"]))
    if pair["runs"]["candidate"]["receipt"]["terminal_sha256"] != saved["receipt"]["terminal_sha256"]:
        raise ValueError("Raw and replayed candidate terminals differ")
    pin = sha256((pair_root / "pair.json").read_bytes()).hexdigest()
    summary = dict(raw_pair_sha256=pin, scientific=science, raw_and_saved_all_images_equal=True,
                   raw_and_saved_terminals_equal=True)
    (output / "joint-south-audit.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("pair_root", "saved_root", "output"):
        cli.add_argument(name, type=Path)
    audit(**vars(cli.parse_args()))
