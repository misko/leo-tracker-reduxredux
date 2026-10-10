"""Metadata-only clean document projection; no recording or objective calls."""

import hashlib
import json
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    inference = runpy.run_path(
        str(HERE.parent / "2026_10_09_position_error_iter131/inference_loader.py")
    )["inference_document"]
    bindings = json.loads((HERE / "bindings.json").read_text())["members"]
    directory = HERE / "documents"
    directory.mkdir(exist_ok=True)
    for binding in bindings:
        source = binding["compatible_documents"][0]
        path = ROOT / source["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("Preparation source changed")
        document = inference(json.loads(path.read_text()))
        for field in (
            "session_id",
            "input_manifest_sha256",
            "analysis_manifest_sha256",
            "evidence_sha256",
        ):
            expected = (
                binding["session_id"] if field == "session_id" else binding["model_identity"][field]
            )
            if document[field] != expected:
                raise ValueError("Inference document identity mismatch")
        output = directory / (binding["label"] + ".json")
        with output.open("x") as stream:
            json.dump(document, stream, indent=2, allow_nan=False)
            stream.write("\n")
        binding["document_path"] = str(output.relative_to(ROOT))
        binding["document_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
        # Preparation-only source document identities do not gate inference.
        del binding["compatible_documents"]
    with (HERE / "parity-bindings.json").open("x") as stream:
        json.dump(dict(members=bindings), stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
