"""Prove selected regional inputs match the archived downstream baseline arms."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    selection = json.loads((HERE / "selection.json").read_text())
    assert selection["complete"] and selection["completed"] == 107
    rows = []
    for case in selection["cases"]:
        path = HERE.parent / "2026_10_08_position_error_iter13/results" / f"{case['label']}.json"
        old = json.loads(path.read_text())
        assert old["session_id"] == case["session_id"]
        matches = {}
        for arm in ("fitted-c", "zero-c"):
            archived = next(r["selected"] for r in old["baseline_arms"] if r["name"] == arm)
            matches[arm] = archived == case["arms"][arm]["selected"]
        rows.append(
            dict(
                label=case["label"],
                downstream_result_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                regional_selected_matches_archived=matches,
                requires_downstream_refit=not matches["fitted-c"],
                zero_c_fallback_baseline_changed=not matches["zero-c"],
            )
        )
    result = dict(
        count=len(rows),
        rows=rows,
        refit_labels=[r["label"] for r in rows if r["requires_downstream_refit"]],
        changed_zero_c_baseline_labels=[
            r["label"] for r in rows if r["zero_c_fallback_baseline_changed"]
        ],
        scope=(
            "Exact selected-result equality against saved downstream baseline arms; "
            "upstream source/observation bindings remain in the frozen protocols. "
            "This is a staged replay audit, not a cold end-to-end execution."
        ),
    )
    (HERE / "downstream-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
