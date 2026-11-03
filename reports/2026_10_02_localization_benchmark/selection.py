import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT.parent / "2026_09_30_ds11_post_ds10/local/manifest.json"
SEED = 2026100216
MODEL_NAMES = (
    "track_independent",
    "track_constant",
    "track_linear",
    "glrt_fixed_8",
    "glrt_fixed_16",
    "glrt_fixed_32",
    "glrt_fixed_64",
    "glrt_free_16",
    "glrt_timing_3s",
    "glrt_timing_10s",
    "anchors",
    "extensions",
    "coherent_timing",
)


def select(captures, count=16, seed=SEED):
    identifiers = sorted(row["session_id"] for row in captures)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Population contains duplicate scan IDs")
    return random.Random(seed).sample(identifiers, count)


def main():
    raw = MANIFEST.read_bytes()
    manifest = json.loads(raw)
    assert manifest["dataset_id"] == "DS11"
    selected = select(manifest["captures"])
    receipt = {
        "schema": "coherent-localization-benchmark-selection/v1",
        "original_sample": "scan-fw-4971402f107cf8e1",
        "dataset": "DS11",
        "seed": SEED,
        "method": "random.Random(seed).sample(sorted unique capture session IDs,16)",
        "population": len(manifest["captures"]),
        "selected": selected,
        "selection_policy": (
            "Uniform without replacement; no fit-quality or outcome filtering; "
            "failed exports/fits remain in denominator and are not replaced"
        ),
        "unit": "one complete capture session; no pooling between selected scans",
        "manifest": str(MANIFEST.relative_to(ROOT.parent.parent)),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "models": list(MODEL_NAMES),
        "training": "all available observations; no heldout partition",
        "scope": (
            "conditional prototype comparison; inherited known-site candidate evidence "
            "is not a blind localization validation"
        ),
    }
    output = ROOT / "selection.json"
    if output.exists():
        if json.loads(output.read_text()) != receipt:
            raise ValueError("Refusing to change an already frozen selection")
    else:
        output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
