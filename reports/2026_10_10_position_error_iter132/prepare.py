"""Metadata-only inference projections; no recording reconstruction or fits."""

import hashlib
import json
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def prepare():
    old = json.loads((HERE.parent / "2026_10_10_position_error_iter130/protocol.json").read_text())
    search = json.loads(
        (HERE.parent / "2026_10_09_position_error_iter129/protocol.json").read_text()
    )
    prior = json.loads(
        (HERE.parent / "2026_10_09_position_error_iter107/protocol.json").read_text()
    )
    loader = runpy.run_path(
        str(HERE.parent / "2026_10_09_position_error_iter131/inference_loader.py")
    )
    projection = runpy.run_path(str(HERE / "reconstruct.py"))["regional_document"]
    port = runpy.run_path(str(HERE.parent / "2026_10_09_position_error_iter107/report.py"))
    search_by = {m["label"]: m for m in search["members"]}
    historical = {port["member_label"](m): m for m in prior["members"]}
    directory = HERE / "inputs"
    directory.mkdir(exist_ok=True)
    bindings = []
    for member in old["members"]:
        label = member["member"]["inventory_label"]
        s = search_by[label]
        h = historical[label]
        expected = json.loads(
            (
                HERE.parent / "2026_10_09_position_error_iter107/results" / label / "baseline.json"
            ).read_text()
        )["input_binding"]
        document = loader["inference_document"](
            json.loads((ROOT / s["binding"]["document_path"]).read_text())
        )
        archive = json.loads((ROOT / member["b7_source"]).read_text())
        source = archive["region_sources"]["fitted-c"]
        regional = (
            port["evaluation_document"](h)
            if source == "baseline"
            else json.loads((ROOT / member["regions"][source]).read_text())
        )
        clean_archive = {
            "region_sources": archive["region_sources"],
            "reasons": {"removed_satellites": archive["reasons"]["removed_satellites"]},
            "raw": {
                stage: {
                    "fitted-c": {
                        k: archive["raw"][stage]["fitted-c"][k]
                        for k in ("converged", "vector", "clock_coefficients")
                    }
                }
                for stage in ("B3", "B4", "B4W", "B5")
            },
            "stages": {
                "B7": {
                    a: {
                        k: archive["stages"]["B7"][a][k]
                        for k in ("vector", "clock_coefficients", "objective")
                    }
                    for a in ("fitted-c", "zero-c")
                }
            },
        }
        payload = {"document": document, "regional": projection(regional), "archive": clean_archive}
        path = directory / f"{label}.json"
        with path.open("x") as stream:
            json.dump(payload, stream, indent=2, allow_nan=False)
            stream.write("\n")
        docpath = directory / f"{label}-document.json"
        with docpath.open("x") as stream:
            json.dump(document, stream, indent=2, allow_nan=False)
            stream.write("\n")
        bindings.append(
            {
                "label": label,
                "dataset": s["dataset"],
                "session_id": s["membership"]["session_id"],
                "document_path": str(docpath.relative_to(ROOT)),
                "document_sha256": hashlib.sha256(docpath.read_bytes()).hexdigest(),
                "projection_path": str(path.relative_to(ROOT)),
                "projection_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "model_identity": h["model_identity"],
                "expected_input_binding": expected,
            }
        )
    with (HERE / "bindings.json").open("x") as stream:
        json.dump({"members": bindings}, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    prepare()
