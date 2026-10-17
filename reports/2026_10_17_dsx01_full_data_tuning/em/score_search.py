"""Apply the shared full-data-only score to the saved EM trials."""

from pathlib import Path
import json

from evaluate_polynomial_tracklets import (
    DEFAULT_INPUT, REPO, digest, json_default, load_observations, save_results,
)
from tune_full_data_tracklets import (
    annotate_full_data_quality, audit_real_result, candidate_record,
)
from leo.analysis.polynomial_tracklets import TrackConfig


def main():
    output = Path(__file__).resolve().parent
    rows, provenance = load_observations(DEFAULT_INPUT)
    records = []
    for path in sorted(output.glob("*/trial.json")):
        trial = json.loads(path.read_text())
        if trial["status"] != "complete":
            records.append(trial)
            continue
        folder = path.parent
        summary = json.loads((folder / "results.json").read_text())
        exports = json.loads((folder / "exports.json").read_text())
        summary, exports = annotate_full_data_quality(summary, exports)
        audit_real_result(rows, summary, exports, TrackConfig(**summary["config"]))
        summary["method"] = "em"
        summary["provenance"] = dict(provenance, source_hashes={
            str(p.relative_to(REPO)): digest(p) for p in (
                REPO / "src/leo/analysis/em_tracklets.py",
                REPO / "src/leo/analysis/tracklet_fitting.py",
                REPO / "src/leo/analysis/polynomial_tracklets.py",
                REPO / "tools/tune_full_data_tracklets.py",
            )
        })
        save_results(output / "trials" / trial["name"], summary, exports)
        record = candidate_record(trial["name"], summary)
        record["cpu_s"] = trial["cpu_s"]
        records.append(record)
        print(json.dumps(record, default=json_default), flush=True)
    (output / "ranked-search.json").write_text(json.dumps(records, indent=2))
    winner = max((r for r in records if "rank" in r), key=lambda r: tuple(r["rank"]))
    (output / "selected.json").write_text(json.dumps(winner, indent=2))
    print("SELECTED", json.dumps(winner, default=json_default))


if __name__ == "__main__":
    main()
