"""Verify owned paths, exact PNGs and the fresh numerical-to-rendered run."""

import hashlib
import json
import math
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
ROOT = Path("/srv/bulk/leo/research/algo07v3-20261104")
RUN = ROOT / "presentation004"
OUT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(path):
    receipt = json.loads(path.with_suffix(".receipt.json").read_text())
    assert digest(path) == (receipt.get("output_sha256") or receipt["output"]["sha256"])
    for record in receipt.get("modules", {}).values():
        assert digest(record["path"]) == record["sha256"], record["path"]
    for key in ("inputs", "additional_inputs", "tool_sources"):
        for name, sha in receipt.get(key, {}).items():
            source = Path(name)
            if not source.is_absolute():
                source = Path(receipt.get("source", REPO)) / source
            assert digest(source) == sha, source
    for key in ("tool", "recovery_catalogue", "reassociation_history_bank"):
        if receipt.get(key):
            record = receipt[key]
            assert digest(record["path"]) == record["sha256"], record["path"]
    return json.loads(path.read_text()), receipt


def main():
    from compare_algo07v3_inclusion import first_difference

    from leo.presentation.fast_standard_analysis import render_position

    paths = {name: RUN / name / "result.json" for name in ("reference", "candidate")}
    paths["fresh"] = RUN / "fresh-candidate.json"
    data = {name: checked(path) for name, path in paths.items()}
    difference = first_difference(data["reference"][0], data["candidate"][0])
    assert difference is None, difference
    previous = ROOT / "reassociation-final002/prefix-candidate.json"
    assert digest(previous) == "af528e2a1fee4385fb6706107bf64b1cdb5e3a4e69211b40d547a8c6c931a9dd"
    fresh, receipt = data["fresh"]
    difference = first_difference(
        json.loads(previous.read_text()), {k: v for k, v in fresh.items() if k != "presentation"}
    )
    assert difference is None, difference
    for _name, packet in (
        ("fixture", data["candidate"][0]["packet"]),
        ("fresh", fresh["presentation"]["packet"]),
    ):
        assert packet["position_grid"]["complete"]
        assert packet["position_grid"]["evaluated_points"] == 179
        assert packet["position_grid"]["planned_points"] == 179
        assert packet["selected_model"] == packet["position_path"]["selected_model"]
    products = data["candidate"][0]["products"]
    assert len(products) == len(fresh["presentation"]["products"]) == 8
    artifacts = {}
    for name, sha in products.items():
        original = paths["reference"].parent / (name + ".png")
        candidate = paths["candidate"].parent / (name + ".png")
        assert digest(original) == digest(candidate) == sha
        # Previously published exact fixture PNGs are linked, not duplicated.
        previous_image = OUT.parent / "2026_11_05_algo07v3_presentation" / (name + ".png")
        assert digest(previous_image) == sha
        artifacts["fixture-" + name] = dict(path=str(candidate), sha256=sha)
    for name, sha in fresh["presentation"]["products"].items():
        image = RUN / "fresh-artifacts" / (name + ".png")
        assert digest(image) == sha
        shutil.copyfile(image, OUT / (name + ".png"))
        artifacts["fresh-" + name] = dict(path=str(image), sha256=sha)
    tests = RUN / "tests.xml"
    suite = ET.parse(tests).getroot().find("testsuite")
    assert all(suite.attrib[k] == "0" for k in ("failures", "errors", "skipped"))
    selected = fresh["reassociation_complete"]["recovery"]
    assert selected["selected"] is None and selected["final"] == selected["baseline"]
    summary = dict(
        fixture_case="DS26-0084",
        fixture_exact=True,
        fixture_owned_path=True,
        exact_png_count=8,
        fixture_grid_locations=179,
        fresh_case="DS26-0002",
        earlier_numerics_exact=True,
        fresh_png_count=8,
        fresh_grid_locations=179,
        fresh_associated={
            a: r["associated_points"] for a, r in fresh["presentation"]["packet"]["arms"].items()
        },
        fresh_observations=len(fresh["presentation"]["packet"]["observations"]),
        fresh_selected_model=fresh["presentation"]["packet"]["selected_model"],
        observed_seconds={name: r[1]["seconds"] for name, r in data.items()},
        tests=int(suite.attrib["tests"]),
        publication_qualified=False,
        native_input_to_publication_qualified=False,
        full_pipeline_parity=False,
        complete_path_matched_scans=0,
        end_to_end_speedup=None,
    )
    paths.update(previous=previous, tests=tests)
    artifacts.update(
        {name: dict(path=str(path), sha256=digest(path)) for name, path in paths.items()}
    )
    for name in ("position-grid", "position-path"):
        path = RUN / "fresh-artifacts" / (name + ".json")
        artifacts[name] = dict(path=str(path), sha256=digest(path))
        shutil.copyfile(path, OUT / (name + ".json"))

    # A separately labelled report image adds confirmed GPS only after every
    # scientific output and original qualification PNG has been verified.
    def numbers(value):
        if isinstance(value, dict):
            if value.get("type") == "float":
                return float.fromhex(value["hex"])
            return {k: numbers(v) for k, v in value.items()}
        if isinstance(value, list):
            return [numbers(v) for v in value]
        return value

    arms = numbers(fresh["presentation"]["packet"]["arms"])
    reference = dict(latitude_deg=37.849061591561885, longitude_deg=-122.48574968092912)
    summary["evaluation_only_error_m"] = {}
    for arm, row in arms.items():
        lat, lon = map(math.radians, row["endpoint_latlon"])
        a, b = map(math.radians, (reference["latitude_deg"], reference["longitude_deg"]))
        h = (
            math.sin((lat - a) / 2) ** 2
            + math.cos(a) * math.cos(lat) * math.sin((lon - b) / 2) ** 2
        )
        summary["evaluation_only_error_m"][arm] = 12742017.6 * math.asin(math.sqrt(h))
    image = render_position(
        arms,
        title="DS26-0002 · ALGO07v3 standalone qualification",
        selected_model=summary["fresh_selected_model"],
        evaluation_reference=reference,
        position_grid=json.loads((OUT / "position-grid.json").read_text()),
        position_path=json.loads((OUT / "position-path.json").read_text()),
    )
    (OUT / "position-evaluation.png").write_bytes(image)
    (OUT / "comparison.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (OUT / "artifact-bindings.json").write_text(json.dumps(artifacts, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
