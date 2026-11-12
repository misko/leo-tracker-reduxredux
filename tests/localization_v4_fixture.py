from leo.contracts.digests import canonical_digest
from leo.contracts.localization_v4 import MODEL
from tests.localization_v3_fixture import evidence_fixture as v3_fixture


def evidence_fixture():
    evidence, pngs = v3_fixture()
    manifest = dict(
        schema_version=1, algorithm=MODEL, source="/source.c", binary="/binary.so",
        wrapper="/wrapper.py", source_sha256="1" * 64, binary_sha256="2" * 64,
        wrapper_sha256="3" * 64, original_sha256="4" * 64,
        provider=dict(path="/provider.so", sha256="5" * 64, threads=1,
                      integer_bytes=4, configuration="synthetic LP64 provider"),
    )
    binding = canonical_digest(manifest)
    evidence["model_version"] = MODEL
    evidence["provenance"].update(
        algorithm=MODEL,
        native_backend=dict(
            manifest=manifest, manifest_sha256=binding,
            receipts=[dict(pid=123, algorithm=MODEL, backend_manifest_sha256=binding,
                           provider=manifest["provider"],
                           counts=dict(calls=2, activated=1, fallback_unsupported=1))],
        ),
    )
    return evidence, pngs
