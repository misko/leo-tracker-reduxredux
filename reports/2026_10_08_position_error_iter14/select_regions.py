"""Truth-free additive selection; flag changed inputs for downstream refitting."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "2026_10_08_position_error_iter06"
sys.path.insert(0, str(SOURCE))
from additive_policy import select  # noqa: E402


def main(partial=False):
    protocol = json.loads((HERE / "protocol.json").read_text())
    cases, missing = [], []
    for label in protocol["labels"]:
        root = SOURCE if label in protocol["reused"] else HERE
        result_path = root / "results" / label / "separation-25.json"
        receipt_path = root / "receipts" / label / "separation-25.json"
        if not result_path.exists() or not receipt_path.exists():
            missing.append(label)
            continue
        if label in protocol["reused"]:
            for name, digest in protocol["reused"][label].items():
                assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == digest
        before = json.loads((root / "baselines" / f"{label}.json").read_text())
        after = json.loads(result_path.read_text())
        receipt = json.loads(receipt_path.read_text())
        assert receipt["identical_grid"] and receipt["point_count"] == 400
        arms = {}
        for arm in ("fitted-c", "zero-c"):
            original = next(a["selected"] for a in before["arms"] if a["name"] == arm)
            additional = next(
                a["selected"] for a in after["methods"][0]["arms"] if a["name"] == arm
            )
            chosen, source = select(original, additional)
            assert chosen is not None
            if original is not None:
                assert chosen["selection_score"] <= original["selection_score"]
            arms[arm] = dict(
                source=source, baseline=original, additional=additional, selected=chosen
            )
        cases.append(
            dict(
                label=label,
                session_id=before["session_id"],
                arms=arms,
                additional_document=str(result_path.relative_to(HERE.parent)),
                additional_file_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
                baseline_document_sha256=before["document_sha256"],
                changed_fitted_region=arms["fitted-c"]["source"] == "additional",
            )
        )
    if not partial:
        assert not missing, f"Incomplete region cohort: {missing}"
        assert len(cases) == 107
    result = dict(
        complete=not missing,
        completed=len(cases),
        expected=107,
        missing=missing,
        changed_fitted_labels=[c["label"] for c in cases if c["changed_fitted_region"]],
        cases=cases,
    )
    output = HERE / ("selection-progress.json" if partial else "selection.json")
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--partial", action="store_true")
    main(parser.parse_args().partial)
