"""Version-one native ALGO07v4 scientific evidence and receipt."""

from leo.contracts import localization_v3
from leo.contracts.digests import canonical_digest
from leo.contracts.localization_v3 import validate_identity as validate_identity

MODEL = "algo07v4-native-v1"


def validate_evidence(evidence):
    localization_v3._validate_evidence(evidence, MODEL)
    try:
        provenance = evidence["provenance"]
        backend = provenance["native_backend"]
        manifest = backend["manifest"]
        for name in ("source", "binary", "wrapper"):
            if not isinstance(manifest[name], str) or not manifest[name].startswith("/"):
                raise ValueError("Native source and binary provenance required")
            localization_v3.require_digest("sha256:" + manifest[name + "_sha256"])
        provider = manifest["provider"]
        localization_v3.require_digest("sha256:" + provider["sha256"])
        localization_v3.require_digest("sha256:" + manifest["original_sha256"])
        if (
            provenance["algorithm"] != MODEL
            or manifest["algorithm"] != MODEL
            or manifest["schema_version"] != 1
            or provider["threads"] != 1
            or provider["integer_bytes"] != 4
            or backend["manifest_sha256"] != canonical_digest(backend["manifest"])
            or any(
                row["algorithm"] != MODEL
                or row["backend_manifest_sha256"] != backend["manifest_sha256"]
                for row in backend["receipts"]
            )
        ):
            raise ValueError("Native evidence algorithm/backend binding differs")
        pids = set()
        for row in backend["receipts"]:
            counts = row["counts"]
            if (
                type(row["pid"]) is not int or row["pid"] <= 0 or row["pid"] in pids
                or row["provider"] != provider
                or any(type(value) is not int or value < 0 for value in counts.values())
                or counts["calls"] != counts["activated"] + sum(
                    value for name, value in counts.items() if name.startswith("fallback_")
                )
            ):
                raise ValueError("Process-owned native activation receipt required")
            pids.add(row["pid"])
    except (KeyError, TypeError) as error:
        raise ValueError("Native evidence provenance required") from error
    return evidence


def validate(receipt):
    return localization_v3._validate(receipt, MODEL)
