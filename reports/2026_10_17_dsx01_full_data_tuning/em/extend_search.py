"""Two final authorized penalty trials; preserve all preceding search records."""

from dataclasses import replace
from pathlib import Path
import json

from tune_full_data_tracklets import run_search
from leo.analysis.polynomial_tracklets import TrackConfig
from finish_search import validate_selected


def main():
    folder = Path(__file__).resolve().parent
    previous = json.loads((folder / "search.json").read_text())
    before = json.loads((folder / "selected.json").read_text())
    (folder / "first-ten-search.json").write_text(json.dumps(previous, indent=2))
    configs = [
        (f"slope08000-pen{penalty:02d}-degree4", replace(
            TrackConfig(), max_slope_hz_s=8000, track_penalty=penalty,
        )) for penalty in (48, 64)
    ]
    run_search("em", configs, output=folder.parent)
    extra = json.loads((folder / "search.json").read_text())
    records = previous + extra
    selected = max((r for r in records if "rank" in r), key=lambda r: tuple(r["rank"]))
    for filename in ("search.json", "ranked-search.json"):
        (folder / filename).write_text(json.dumps(records, indent=2))
    (folder / "selected.json").write_text(json.dumps(selected, indent=2))
    print("FINAL_SELECTED", json.dumps(selected), flush=True)
    if selected["name"] != before["name"]:
        validate_selected(folder, selected)


if __name__ == "__main__":
    main()
