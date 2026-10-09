"""Bind full immutable membership to archived or completed baseline inputs."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter45"))
# isort: off
from complete_members import load_case as load_document  # noqa: E402
from baseline import load_case as load_ds17  # noqa: E402
from inputs import load_case as load_ds16  # noqa: E402
from leo.contracts.digests import canonical_digest  # noqa: E402
from leo.storage.regional_position_v2 import Hard60Store  # noqa: E402
# isort: on


class BaselinePending(Exception):
    pass


def read(path):
    return json.loads(path.read_text())


def load(binding):
    member = binding["member"]
    kind = binding["kind"]
    previous = binding["previous_candidate"]
    if kind == "legacy_ds16":
        case = load_ds16(binding["legacy_label"])
        baseline = (
            read(REPORTS.parent / binding["baseline_path"])
            if binding["baseline_path"]
            else case.document
        )
        receipt = read(
            REPORTS
            / "2026_10_08_hard60_bounded_recovery/cohort"
            / f"{binding['legacy_label']}.json"
        )
        for arm in baseline["methods"][0]["arms"]:
            expected = receipt["arms"][arm["name"]]["actual"]
            for key in (
                "objective",
                "selection_score",
                "horizontal_error_m",
                "source_basin",
                "satellites",
            ):
                assert arm["selected"][key] == expected[key], (member["inventory_label"], key)
    elif kind == "legacy_ds17":
        case = load_ds17(member["inventory_label"])
        baseline = read(REPORTS.parent / binding["baseline_path"])
    else:
        root = Path("/srv/bulk/leo")
        if kind == "completion":
            path = REPORTS.parent / binding["completion_path"]
            if not path.exists():
                raise BaselinePending(f"Completion receipt not ready: {path}")
            receipt = read(path)
            if receipt["status"] != "complete":
                raise BaselinePending(f"Completion receipt remains {receipt['status']}: {path}")
            if receipt["baseline_mode"] == "isolated_standard_baseline":
                root = REPORTS / "2026_10_08_position_error_iter45/local/standard-baselines"
            previous = receipt["extension"]["operational"]
        if binding["baseline_path"]:
            baseline = read(REPORTS.parent / binding["baseline_path"])
        else:
            published = Hard60Store(root).status(member["session_id"]).manifest
            if published is None:
                raise BaselinePending("Previously published baseline is unavailable")
            baseline = published.document.model_dump(mode="json")
            assert canonical_digest(baseline) == binding["baseline_document_digest"]
        case = load_document(baseline, root)
    assert baseline["session_id"] == member["session_id"]
    assert baseline["input_manifest_sha256"] == binding["effective_input_digest"]
    assert baseline["analysis_manifest_sha256"] == case.document["analysis_manifest_sha256"]
    return case, baseline, previous
