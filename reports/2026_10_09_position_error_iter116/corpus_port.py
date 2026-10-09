"""Narrow adapter to the existing verified five-value whole-prior corpus loader."""

import hashlib
import inspect
import json
from pathlib import Path


class BoundCorpusLoader:
    """Inject immutable105 load_case; no historical error-equality loader needed.

    A preparation step must supply a sanitized public document with exact hashes.
    No CLI or implicit recording enumeration occurs here.
    """

    def __init__(self, repository, load_case):
        self.repository, self.load_case = Path(repository), load_case

    def __call__(self, binding):
        source = Path(inspect.getsourcefile(self.load_case)).resolve()
        if source != (self.repository / binding["loader_source"]).resolve():
            raise ValueError("unexpected corpus loader source")
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["loader_sha256"]:
            raise ValueError("corpus loader source changed")
        path = self.repository / binding["document_path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != binding["document_sha256"]:
            raise ValueError("public document changed")
        document = json.loads(path.read_text())

        def check(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if (
                        "reference" in key.lower()
                        or "error_m" in key.lower()
                        or "error_km" in key.lower()
                    ):
                        raise ValueError("evaluation field in inference document")
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)

        check(document)
        if document["session_id"] != binding["session_id"]:
            raise ValueError("session mismatch")
        observations, bank, prior, tracks, verified = self.load_case(document)
        if (
            verified["input_digest"] != document["input_manifest_sha256"]
            or verified["evidence_digest"] != document["evidence_sha256"]
        ):
            raise ValueError("loader evidence mismatch")
        return dict(
            observations=observations,
            bank=bank,
            prior=prior,
            tracks=tracks,
            identity={
                field: document[field]
                for field in (
                    "input_manifest_sha256",
                    "analysis_manifest_sha256",
                    "evidence_sha256",
                )
            },
        )
