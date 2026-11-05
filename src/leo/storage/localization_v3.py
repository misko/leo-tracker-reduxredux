"""Immutable standalone scientific evidence, committed before UI publication."""

import json
import os
import uuid
from pathlib import Path

from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.fast_standard_analysis import MODEL as POLICY_MODEL
from leo.contracts.localization_v3 import MODEL, validate, validate_evidence, validate_identity
from leo.storage.fast_scan import immutable_json, safe_id
from leo.storage.localization_v3_codec import pack, unpack
from leo.storage.uri import confined_path


class LocalizationV3Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        if self.root.is_relative_to("/mnt/qnap01"):
            raise ValueError("Standalone results must be local")
        self.root.mkdir(parents=True, exist_ok=True)

    def _folder(self, run_id):
        return confined_path(
            self.root, self.root / "localization-v3-v1" / safe_id(run_id), must_exist=False
        )

    def save(self, evidence, pngs):
        validate_evidence(evidence)
        identity = evidence["identity"]
        validate_identity(identity)
        if evidence["status"] != "figures_ready":
            raise ValueError("Completed numerical and presentation evidence required")
        packet = evidence["presentation"]
        raw = pack(evidence, pngs)
        receipt = validate(
            dict(
                schema_version=1,
                model_version=MODEL,
                policy_model_version=POLICY_MODEL,
                state="complete",
                **identity,
                result_sha256=sha256_digest(raw),
                result_bytes=len(raw),
                selected_model=packet["selected_model"],
                arms=packet["arms"],
                glrt_points=len(packet["observations"]),
            )
        )
        folder = self._folder(identity["run_id"])
        folder.mkdir(parents=True, exist_ok=True)
        target = confined_path(
            self.root, folder / (receipt["result_sha256"][7:] + ".zip"), must_exist=False
        )
        temporary = target.with_name(target.name + "." + uuid.uuid4().hex + ".partial")
        try:
            with temporary.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
                descriptor = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except FileExistsError:
                if target.read_bytes() != raw:
                    raise ValueError("Scientific archive digest collision") from None
        finally:
            temporary.unlink(missing_ok=True)
        immutable_json(
            confined_path(self.root, folder / "manifest.json", must_exist=False), receipt
        )
        return dict(receipt=receipt, sha256=canonical_digest(receipt))

    def load(self, run_id):
        folder = self._folder(run_id)
        manifest = confined_path(self.root, folder / "manifest.json", must_exist=True)
        receipt = validate(json.loads(manifest.read_bytes()))
        if receipt["run_id"] != run_id:
            raise ValueError("Standalone result belongs to another run")
        path = confined_path(
            self.root, folder / (receipt["result_sha256"][7:] + ".zip"), must_exist=True
        )
        raw = path.read_bytes()
        if len(raw) != receipt["result_bytes"] or sha256_digest(raw) != receipt["result_sha256"]:
            raise ValueError("Standalone archive integrity failure")
        evidence, pngs = unpack(raw)
        validate_evidence(evidence)
        identity = {k: receipt[k] for k in ("run_id", "session_id", "input_sha256")}
        packet = evidence["presentation"]
        if (
            evidence["identity"] != identity
            or evidence["status"] != "figures_ready"
            or packet["arms"] != receipt["arms"]
            or packet["selected_model"] != receipt["selected_model"]
            or len(packet["observations"]) != receipt["glrt_points"]
        ):
            raise ValueError("Standalone archive differs from its receipt")
        return dict(receipt=receipt, sha256=canonical_digest(receipt), evidence=evidence, pngs=pngs)
