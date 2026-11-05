"""Verify all plot values, conditional grid and PNG bytes before publishing report."""

import hashlib
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
ROOT = Path("/srv/bulk/leo/research/algo07v3-20261104")
OUT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(path):
    receipt = json.loads(path.with_suffix(".receipt.json").read_text())
    assert digest(path) == receipt["output"]["sha256"]
    for record in [receipt["tool"], *receipt["modules"].values()]:
        assert digest(record["path"]) == record["sha256"], record["path"]
    for name, sha in receipt["inputs"].items():
        assert digest(name) == sha, name
    return json.loads(path.read_text()), receipt


def main():
    from compare_algo07v3_inclusion import first_difference

    paths = {
        name: ROOT / "presentation003" / name / "result.json" for name in ("reference", "candidate")
    }
    paths.update(
        {
            name: ROOT / "presentation002" / (name + ".json")
            for name in ("retained-reference", "retained-candidate")
        }
    )
    data = {name: checked(path) for name, path in paths.items()}
    for pair in [("reference", "candidate"), ("retained-reference", "retained-candidate")]:
        difference = first_difference(data[pair[0]][0], data[pair[1]][0])
        assert difference is None, difference
    candidate, receipt = data["candidate"]
    assert receipt["complete_grid"] and receipt["evaluated_grid"] == receipt["planned_grid"] == 179
    products = candidate["products"]
    assert set(products) == {
        "ch1-4-all",
        "ch5-8-all",
        "ch1-4-unassociated",
        "ch5-8-unassociated",
        "ch1-4-residuals",
        "ch5-8-residuals",
        "track-rms",
        "position",
    }
    rows = []
    for name, sha in products.items():
        reference = paths["reference"].parent / (name + ".png")
        image = paths["candidate"].parent / (name + ".png")
        assert digest(image) == digest(reference) == sha
        shutil.copyfile(image, OUT / (name + ".png"))
        paths[name] = image
        rows.append(dict(name=name, bytes=image.stat().st_size, sha256=sha, exact=True))
    tests = ROOT / "presentation002/tests-rerun.xml"
    suite = ET.parse(tests).getroot().find("testsuite")
    assert all(suite.attrib[k] == "0" for k in ("failures", "errors", "skipped"))
    selected = data["retained-candidate"][0]["complete_final"]
    assert selected["selected"] == "62025_to_68047"
    summary = dict(
        case="DS26-0084",
        exact_plot_packet=True,
        exact_grid_points=179,
        exact_png_count=8,
        plots=rows,
        selected_model=candidate["packet"]["selected_model"],
        associated_points={
            arm: row["associated_points"] for arm, row in candidate["packet"]["arms"].items()
        },
        observations=len(candidate["packet"]["observations"]),
        selected_likelihood_retention_exact=True,
        retention_case="DS26-0066",
        tests=int(suite.attrib["tests"]),
        observed_seconds={name: item[1]["seconds"] for name, item in data.items()},
        full_pipeline_parity=False,
        publication_qualified=False,
        complete_path_matched_scans=0,
        end_to_end_speedup=None,
    )
    (OUT / "comparison.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    paths["tests"] = tests
    (OUT / "artifact-bindings.json").write_text(
        json.dumps(
            {name: dict(path=str(path), sha256=digest(path)) for name, path in paths.items()},
            indent=2,
        )
        + "\n"
    )
    table = "| Figure | Bytes | Exact PNG match |\n|---|---:|---|\n"
    for row in rows:
        table += f"| [{row['name']}]({row['name']}.png) | {row['bytes']:,} | Yes |\n"
    (OUT / "figures.md").write_text(table)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
