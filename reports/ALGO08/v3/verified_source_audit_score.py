"""Authenticate already published saved products and price only the late source tail."""

import argparse
from hashlib import file_digest, sha256
from io import BytesIO
import json
from pathlib import Path
from time import perf_counter_ns, process_time_ns


ORIGINAL = Path("/dev/shm/leo-v3-combined-successor-cairo-01/DS30-0016")
RESULT = "b47d6753614a20feb577bb2246eabf21a94b027a46d8a928cb014874aa1960d7"
ROOT = Path(__file__).resolve().parents[3]


def sidecar(path):
    envelope = json.loads(path.read_bytes())
    document = envelope["document"]
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if "sha256:" + sha256(encoded).hexdigest() != envelope["sha256"]:
        raise ValueError(f"The sidecar cannot verify its document: {path.name}")
    return document


def check(root):
    from PIL import Image

    data = (ORIGINAL/"result.json").read_bytes()
    if sha256(data).hexdigest() != RESULT:
        raise ValueError("The qualified reference changed")
    expected = json.loads(data)
    run = expected["science"]["receipt"]["run_id"]
    session = expected["science"]["receipt"]["session_id"]
    report = Path("fast-scan-reports")/f"{run}.json"
    terminal = Path("fast-scan-automatic-work")/run/"terminal.json"
    detector, = (ORIGINAL/"candidate/fast-scan-automatic-work").glob("*/detections.json")
    stage = Path("fast-scan-standard-v2")/run/"final-error-v7"
    paths = [report, terminal, detector.relative_to(ORIGINAL/"candidate"), Path("fast-scan-inputs")/f"{session}.json",
             stage/"manifest.json", stage/"position-path.json", stage/"position-grid.json"]
    candidate = root/"candidate"
    files = {}
    for file in paths:
        first, second = ((item/file).read_bytes() for item in (ORIGINAL/"candidate", candidate))
        files[str(file)] = dict(identical=first == second, sha256=sha256(second).hexdigest(), bytes=len(second))
    detail = json.loads((candidate/stage/"manifest.json").read_bytes())
    expected_details = expected["witness"]["evidence"]["detail"]
    images = {}
    evidence = expected["witness"]["evidence"]
    for name, entry in evidence["images"].items():
        photo = entry["sha256"].removeprefix("sha256:")
        media = (candidate/stage/f"{photo}.png").read_bytes()
        with Image.open(BytesIO(media)) as image:
            image.load()
            images[name] = dict(sha256=sha256(media).hexdigest(), rgba_sha256=sha256(image.convert("RGBA").tobytes()).hexdigest(),
                                size=list(image.size))
        if any(images[name][field] != (entry[field].removeprefix("sha256:") if field.endswith("sha256") else entry[field])
               for field in images[name]):
            raise ValueError("The actual encoded or decoded figure changed")
    grid = sidecar(candidate/stage/"position-grid.json")
    original_grid = sidecar(ORIGINAL/"candidate"/stage/"position-grid.json")
    original_grid_elapsed = original_grid.pop("elapsed_seconds")
    grid_elapsed = grid.pop("elapsed_seconds")
    path = sidecar(candidate/stage/"position-path.json")
    owner_maps = {arm: row["owner_sha256"] for arm, row in detail["arms"].items()}
    checks = dict(documents=all(item["identical"] for name, item in files.items() if not name.endswith("/position-grid.json")),
                  figure_count=len(images) == 8, grid=grid == original_grid and grid["matched_c_grid"] and len(grid["points"]) == 179,
                  paths_bind_actual_position=all(doc["binding"]["position_png_sha256"].removeprefix("sha256:") ==
                                                 images["position"]["sha256"] for doc in (grid, path)),
                  both_arms=detail["arms"] == {arm: {name: value for name, value in row.items() if name != "evaluation_error_m"}
                                               for arm, row in expected_details["arms"].items()},
                  owner_maps=owner_maps == evidence["owner_maps"],
                  original_authority=detail["raw_authority"] == expected["science"]["published"]["raw_authority"],
                  original_native=detail["input_sha256"] == expected["science"]["native_sha256"])
    if not all(checks.values()):
        raise ValueError(f"Failed durable product comparison: {checks}")

    trace = json.loads((root/"source-audit.json").read_bytes())
    seen = {row["label"]: row["source_sha256"] for row in trace["events"] if row["kind"] == "source_read"}
    late_sources = []
    # This is a separately charged digest-only replay. The observed solver's
    # final attestation did not complete, and these times are not in its trace.
    for name, old_hash in sorted(expected["witness"]["source_sha256"].items()):
        file = ROOT/name
        begin, wall = process_time_ns(), perf_counter_ns()
        with file.open("rb") as stream:
            digest = file_digest(stream, "sha256").hexdigest()
        late_sources.append(dict(name=name, cpu_ns=process_time_ns()-begin, wall_ns=perf_counter_ns()-wall,
                                 previous_observed=seen.get(str(file)) == digest,
                                 matches_archived=digest == old_hash.removeprefix("sha256:"), size=file.stat().st_size))
    return dict(qualified=True, checks=checks, images=images, files=files, owner_maps=owner_maps, arms=detail["arms"],
                grid_elapsed_seconds={"candidate": grid_elapsed, "archived": original_grid_elapsed},
                ordered_owner_roles_available=False, late_sources=late_sources, original_result=RESULT,
                repeated_from_original_trace=sum(row["previous_observed"] for row in late_sources),
                source_audit_sha256=sha256((root/"source-audit.json").read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = check(args.root)
    with args.output.open("x") as handle:
        json.dump(result, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")
