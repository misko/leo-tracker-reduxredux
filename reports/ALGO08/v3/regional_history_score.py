"""Verify a four-process saved-history comparison against the original selective publication."""

import hashlib
import json
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def one(root, name):
    path, = root.rglob(name)
    return path


def scientific(root):
    from PIL import Image

    products = {name: digest(one(root, name).read_bytes())
                for name in ("detections.json", "terminal.json", "position-path.json", "manifest.json")}
    grid = json.loads(one(root, "position-grid.json").read_text())["document"]
    grid.pop("elapsed_seconds")
    if grid["evaluated_points"] != len(grid["points"]) or not grid["matched_c_grid"]:
        raise ValueError("Incomplete calibration grid")
    research = json.loads((root / "joint-research-receipt.json").read_text())
    products.update(grid=digest(encode(grid)), grid_points=len(grid["points"]),
                    rows=digest(encode(research["selected_rows"])),
                    owner_counts={k: len(v) for k, v in research["selected_rows"].items()})
    images = {}
    for path in root.rglob("*.png"):
        with Image.open(path) as image:
            pixels = image.convert("RGBA")
            images[path.name] = dict(encoded=digest(path.read_bytes()), dim=list(pixels.size),
                                     decoded=digest(pixels.tobytes()))
    if len(images) != 8:
        raise ValueError("Expected the eight distinct official PNGs")
    return products | {"images": images}


def compare(root, reference):
    expected = scientific(reference / "selective")
    binding = digest((reference / "binding.json").read_bytes())
    runs = []
    for label in ("candidate-1", "baseline-1", "baseline-2", "candidate-2"):
        case = root / label
        if digest((case / "binding.json").read_bytes()) != binding or scientific(case / "selective") != expected:
            raise ValueError(f"{label} changed the input or scientific output")
        worker = json.loads((case / "selective/continued-cfo-worker.json").read_text())
        if worker["waveform_calls"] or worker["handoffs"] != 1:
            raise ValueError("Expected one saved handoff and no acquisition")
        wall, user, system, blocks, faults = (case / "process.time").read_text().split()
        work = json.loads((case / "history-rows.json").read_text())
        runs.append(dict(label=label, wall_s=float(wall), user_s=float(user), system_s=float(system),
                         input_blocks=int(blocks), major_faults=int(faults), scope=work,
                         solve=worker["solve"]["cpu_s"], saved=worker["complete_saved"]))
    return dict(binding_sha256=binding, products=expected, runs=runs)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("reference", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.root, args.reference), indent=2, sort_keys=True))
