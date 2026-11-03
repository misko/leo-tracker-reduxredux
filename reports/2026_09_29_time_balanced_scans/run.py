import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SOURCE = HERE.parent / "2026_09_29_receiver_holdout/run.py"
spec = importlib.util.spec_from_file_location("receiver_runner", SOURCE)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def main(key):
    started = time.monotonic()
    manifest_path = HERE / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for name, digest in manifest["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    unit = next(u for u in manifest["sets"] if u["unit"] == key)
    inputs = [r["input"] for r in unit["scans"]]
    hashes = {}
    for entry in inputs:
        for artifact in entry["artifacts"]:
            path = Path(artifact["path"])
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert "sha256:" + digest == artifact["sha256"]
            hashes[str(path.relative_to(ROOT))] = digest
    docs = helper.baseline.load_documents(dict(config=manifest["config"], inputs=inputs))
    model = helper.TrendMixturePosition(docs, manifest["config"], helper.baseline.Stationary, 0.2)
    starts = []
    for east in (-2.0, 0.0, 2.0):
        x = np.zeros(2 + len(docs))
        x[0] = east
        starts.append(helper.fit_model(model, x))
    valid = [r for r in starts if r["qualified"]]
    selected = None
    if valid:
        selected = dict(max(valid, key=lambda r: r["score"]))
        x = np.array(selected["x"])
        scored = model.evaluate(x, gradient=False, held=True)
        selected.update(
            estimate_deg=list(model.models[0].coordinates(x[:3])),
            held_score=sum(r["held_log_score"] for r in scored["rows"]),
        )
    paths = [
        manifest_path,
        HERE / "run.py",
        SOURCE,
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        ROOT / "tools/ds7_baseline_adapter.py",
        HERE.parent / "2026_09_29_unassociated_trend/trend_mixture.py",
        HERE.parent / "2026_09_29_frequency_contrast/contrast_position.py",
    ]
    hashes.update(
        {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    )
    result = dict(
        unit=key,
        dataset=unit["dataset"],
        arm=unit["arm"],
        start_span_hours=unit["start_span_hours"],
        starts=starts,
        selected=selected,
        tracks=sum(len(d["tracks"]) for d in docs),
        observations=sum(len(t["y"]) for d in docs for t in d["tracks"]),
        sessions=[d["session_id"] for d in docs],
        elapsed_seconds=time.monotonic() - started,
        hashes=hashes,
    )
    (HERE / f"{key}.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(key, selected is not None, result["elapsed_seconds"], flush=True)


if __name__ == "__main__":
    import sys

    main(sys.argv[1])
