import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from corpus_port import BoundCorpusLoader


def fake_loader(document):
    return (
        None,
        None,
        None,
        (),
        dict(
            input_digest=document["input_manifest_sha256"],
            evidence_digest=document["evidence_sha256"],
        ),
    )


def binding(tmp_path, extra=None):
    document = dict(
        session_id="synthetic",
        input_manifest_sha256="input",
        analysis_manifest_sha256="analysis",
        evidence_sha256="evidence",
    )
    document.update(extra or {})
    path = tmp_path / "document.json"
    path.write_text(json.dumps(document))
    source = Path(__file__).resolve()
    return dict(
        session_id="synthetic",
        document_path=str(path),
        document_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        loader_source=str(source),
        loader_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )


def test_bound_existing_loader_port_and_document_identity(tmp_path):
    b = binding(tmp_path)
    loader = BoundCorpusLoader(tmp_path, fake_loader)
    assert loader(b)["identity"]["evidence_sha256"] == "evidence"
    b["document_sha256"] = "changed"
    with pytest.raises(ValueError, match="document changed"):
        loader(b)


def test_reference_fields_rejected_before_loader(tmp_path):
    b = binding(tmp_path, dict(reference={"latitude": 1}))
    with pytest.raises(ValueError, match="evaluation field"):
        BoundCorpusLoader(tmp_path, fake_loader)(b)
