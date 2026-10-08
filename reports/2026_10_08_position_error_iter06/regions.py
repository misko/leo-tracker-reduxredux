"""Replay the identical sampled grid with wider final-basin separation.

Only separation changes. Cached operations are borrowed only where their
inputs do not depend on separation; new regional calibrations/finals run fully.
No reference location enters selection or the runner.
"""

import json
import sys
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026_10_08_hard60_bounded_recovery"))
sys.path.insert(0, str(HERE.parent / "2026_10_08_position_error_iter01"))
from baseline import load_case as load_ds17  # noqa: E402
from inputs import ExperimentCheckpoints, json_value, write_json  # noqa: E402
from inputs import load_case as load_ds16  # noqa: E402

from leo.application.hard60_runner import Hard60Configuration, run_hard60  # noqa: E402
from leo.application.regional_position_report import regional_position_document  # noqa: E402
from leo.application.regional_position_runner import RegionalSliceExpired  # noqa: E402
from leo.cli.regional_position import configuration  # noqa: E402
from leo.contracts.digests import canonical_digest  # noqa: E402


class ReplayCheckpoints:
    def __init__(self, case, cache, prefix, borrowed):
        self.case, self.cache, self.prefix, self.borrowed = case, cache, prefix, borrowed

    def get(self, key):
        assert key.startswith(self.prefix)
        existing = self.cache.get(key)
        if existing is not None:
            return existing
        stage = key.removeprefix(self.prefix)
        if not stage.startswith("recovery:"):
            try:
                existing = self.case.checkpoint(stage)
            except KeyError:
                existing = None
            if existing is not None:
                self.borrowed.add(stage)
                return existing
        return None

    def put(self, key, value):
        self.cache.put(key, value)


def run(label, separations):
    if label.startswith("NEW-"):
        from newer_inputs import load_newer

        case = load_newer(label)
    else:
        case = load_ds17(label) if label.startswith("DS17-") else load_ds16(label)
    original = case.document
    baseline = original
    if label.startswith("DS17-"):
        baseline = json.loads(
            (
                HERE.parent / "2026_10_08_position_error_iter01/baseline" / f"{label}.json"
            ).read_text()
        )
    elif label in ("S14", "S27"):
        baseline = json.loads(
            (
                HERE.parent / "2026_10_08_hard60_bounded_recovery" / f"{label}-document.json"
            ).read_text()
        )
    baseline_path = HERE / "baselines" / f"{label}.json"
    baseline_receipt = dict(
        label=label,
        session_id=baseline["session_id"],
        document_sha256=canonical_digest(baseline),
        arms=baseline["methods"][0]["arms"],
    )
    if baseline_path.exists():
        assert json.loads(baseline_path.read_text()) == baseline_receipt
    else:
        write_json(baseline_path, baseline_receipt)
    for separation in separations:
        name = f"separation-{separation:g}"
        path = HERE / "results" / label / f"{name}.json"
        if path.exists():
            print(label, name, "already completed", flush=True)
            continue
        config = replace(Hard60Configuration(), basin_separation_km=separation)
        prefix = canonical_digest(json_value(config)) + ":"
        cache = ExperimentCheckpoints(
            HERE / "checkpoints" / label / name,
            dict(original=canonical_digest(original), config=json_value(config)),
        )
        borrowed = set()

        result = None
        # Each slice is bounded and resumable; no radio acquisition is started.
        for _ in range(4):
            try:
                result = run_hard60(
                    case.prepared.observations,
                    case.bank,
                    case.prior,
                    case.prepared.bootstrap_tracks,
                    ReplayCheckpoints(case, cache, prefix, borrowed),
                    configuration=config,
                    maximum_seconds=500,
                )
                break
            except RegionalSliceExpired as error:
                print(label, name, "checkpointed slice", str(error), flush=True)
        if result is None:
            raise TimeoutError("four bounded slices exhausted")
        doc_config = configuration()
        doc_config["run"] = json_value(config)
        document = regional_position_document(
            result,
            session_id=original["session_id"],
            input_digest=original["input_manifest_sha256"],
            analysis_digest=original["analysis_manifest_sha256"],
            evidence_digest=original["evidence_sha256"],
            configuration=doc_config,
            windows=original["windows"],
            reference=(original["reference_latitude_deg"], original["reference_longitude_deg"]),
            reference_evidence="Existing reference applied after model selection only",
            diagnostics={k: original["diagnostics"][k] for k in ("bank", "snapshot_sha256")},
        ).model_dump(mode="json")
        # Verify identical raw search evaluation coordinates and budgets.
        before = original["methods"][0]["points"]
        after = document["methods"][0]["points"]

        def coords(rows):
            return [(p["east_km"], p["north_km"], p["spacing_km"]) for p in rows]

        assert coords(before) == coords(after)
        write_json(path, document)
        write_json(
            HERE / "receipts" / label / f"{name}.json",
            dict(
                label=label,
                separation_km=separation,
                identical_grid=True,
                point_count=len(after),
                borrowed_stages=sorted(borrowed),
                source_document_sha256=canonical_digest(original),
                candidate_document_sha256=canonical_digest(document),
            ),
        )
        print(
            label,
            name,
            [
                (a["name"], a["selected"]["horizontal_error_m"] / 1000)
                for a in document["methods"][0]["arms"]
            ],
            flush=True,
        )


if __name__ == "__main__":
    run(sys.argv[1], [float(s) for s in sys.argv[2:]])
