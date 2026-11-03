import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from run import helper

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "2026_09_29_marginal_timing_fit"))
from timing_model import training_scores  # noqa: E402


def main(key):
    started = time.monotonic()
    original_path = HERE / f"{key}.json"
    original = json.loads(original_path.read_text())
    for name, digest in original["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    manifest = json.loads((HERE / "manifest.json").read_text())
    unit = next(u for u in manifest["sets"] if u["unit"] == key)
    docs = helper.baseline.load_documents(
        dict(config=manifest["config"], inputs=[r["input"] for r in unit["scans"]])
    )
    model = helper.TrendMixturePosition(docs, manifest["config"], helper.baseline.Stationary, 0.2)
    singles = [
        helper.TrendMixturePosition([d], manifest["config"], helper.baseline.Stationary, 0.2)
        for d in docs
    ]
    starts = []
    grid = np.array(manifest["config"]["timing_grid_s"])
    replay = 0.0
    for east in (-2.0, 0.0, 2.0):
        x = np.zeros(10)
        x[0] = east
        scores_by_scan = []
        for di, one in enumerate(singles):
            scores, _ = training_scores(one, x[:2], grid)
            index = int(np.argmax(scores))
            x[di + 2] = grid[index]
            scalar = one.evaluate([east, 0.0, grid[index]], gradient=False)["score"]
            replay = max(replay, abs(scalar - scores[index]))
            scores_by_scan.append(scores.tolist())
        assert replay < 1e-7
        fit = helper.fit_model(model, x)
        starts.append(dict(fit, initial=x.tolist(), timing_grid_scores=scores_by_scan))
    valid = [dict(r, start_family="cold") for r in original["starts"] if r["qualified"]]
    valid += [dict(r, start_family="timing_grid") for r in starts if r["qualified"]]
    selected = max(valid, key=lambda r: r["score"]) if valid else None
    if selected:
        x = np.array(selected["x"])
        scored = model.evaluate(x, gradient=False, held=True)
        selected.update(
            estimate_deg=list(model.models[0].coordinates(x[:3])),
            held_score=sum(r["held_log_score"] for r in scored["rows"]),
        )
        assert selected["score"] >= original["selected"]["score"] - 1e-8
    paths = [
        original_path,
        HERE / "grid_run.py",
        HERE / "TIMING-START-AUDIT.md",
        HERE.parent / "2026_09_29_marginal_timing_fit/timing_model.py",
    ]
    result = dict(
        unit=key,
        dataset=unit["dataset"],
        arm=unit["arm"],
        selected=selected,
        additional_starts=starts,
        scalar_replay_error=replay,
        elapsed_seconds=time.monotonic() - started,
        primary_training_score=original["selected"]["score"],
        start_span_hours=unit["start_span_hours"],
        tracks=original["tracks"],
        observations=original["observations"],
        sessions=original["sessions"],
        hashes={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
    )
    (HERE / f"grid_{key}.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(
        key,
        selected["score"] - original["selected"]["score"],
        selected["start_family"],
        result["elapsed_seconds"],
        flush=True,
    )


if __name__ == "__main__":
    main(sys.argv[1])
