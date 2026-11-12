"""Prebuilt native artifact binding and process-owned activation receipts."""

import atexit
import json
import os
import re
from multiprocessing.util import Finalize
from pathlib import Path

from leo.analysis.localization_v4 import native_bound
from leo.contracts.digests import canonical_digest

ALGORITHM = "algo07v4-native-v1"


def _local(path):
    path = Path(path).resolve()
    if path.is_relative_to("/mnt/qnap01"):
        raise ValueError("QNAP is read-only")
    return path


def build_native(output):
    output = _local(output)
    binary = native_bound.build(output)
    manifest_path = binary.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    _, _, provider = native_bound.provider()
    manifest.update(
        schema_version=1,
        algorithm=ALGORITHM,
        original_sha256=native_bound.ORIGINAL_SHA256,
        provider=provider,
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    validate_manifest(manifest)
    return manifest_path


def read_manifest(value):
    return json.loads(Path(value).read_bytes()) if isinstance(value, (str, Path)) else value


def validate_manifest(manifest, *, check_provider=False, check_artifacts=True):
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or manifest.get("algorithm") != ALGORITHM
        or manifest.get("original_sha256") != native_bound.ORIGINAL_SHA256
        or manifest.get("flags") != list(native_bound.FLAGS)
        or manifest.get("sanitized") is not False
        or manifest.get("ABI") != "SciPy LAPACKE LP64; C int32/char ABI; column-major=102"
        or not {"source", "source_sha256", "wrapper", "wrapper_sha256",
                "binary", "binary_sha256", "provider"} <= set(manifest)
    ):
        raise ValueError("Qualified ALGO07v4 native build manifest required")
    for name, expected in (
        ("source", native_bound.SOURCE),
        ("wrapper", Path(native_bound.__file__)),
        ("binary", None),
    ):
        if not isinstance(manifest[name], str):
            raise ValueError("Absolute native artifact path required")
        path = Path(manifest[name])
        if not isinstance(manifest[name + "_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", manifest[name + "_sha256"]
        ):
            raise ValueError("Native artifact digest required")
        if not path.is_absolute() or (
            check_artifacts and expected is not None and path.resolve() != expected.resolve()
        ):
            raise ValueError("Native build source binding differs")
        if check_artifacts and native_bound.digest(path) != manifest[name + "_sha256"]:
            raise ValueError("Native build artifact binding differs")
    binary = Path(manifest["binary"])
    if check_artifacts and read_manifest(binary.parent / "manifest.json") != manifest:
        raise ValueError("Native manifest differs from its binary build")
    provider = manifest["provider"]
    if (
        not isinstance(provider, dict)
        or set(provider) != {"path", "sha256", "configuration", "threads",
                            "integer_bytes", "symbols"}
        or not isinstance(provider["path"], str)
        or not Path(provider["path"]).is_absolute()
        or not isinstance(provider["sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", provider["sha256"])
        or not isinstance(provider["configuration"], str)
        or provider["symbols"] != ["scipy_LAPACKE_" + name
                                   for name in ("dpotrf", "dpotrs", "dpotri", "dpocon")]
    ):
        raise ValueError("Explicit SciPy LP64 provider provenance required")
    if (
        provider["threads"] != 1
        or provider["integer_bytes"] != 4
        or "USE64BITINT" in provider["configuration"]
        or (check_artifacts and native_bound.digest(provider["path"]) != provider["sha256"])
    ):
        raise ValueError("Single-thread SciPy LP64 provider binding required")
    if check_provider and native_bound.provider()[2] != provider:
        raise ValueError("Loaded SciPy provider differs from native build")
    return manifest


class ProcessBound:
    """Each PID initializes its own native layouts and reports only its calls."""

    def __init__(self, manifest, receipts):
        self.manifest = validate_manifest(read_manifest(manifest), check_provider=True)
        self.receipts = _local(receipts)
        self.receipts.mkdir(parents=True, exist_ok=False)
        self.pid = None
        self.backend = None

    def __call__(self, *args, **kwargs):
        pid = os.getpid()
        if self.pid != pid:
            validate_manifest(self.manifest, check_provider=True)
            self.backend = native_bound.NativeBound(self.manifest["binary"])
            self.pid = pid
            atexit.register(self.flush)
            self.finalizer = Finalize(None, self.flush, exitpriority=10)
        return self.backend(*args, **kwargs)

    def flush(self):
        if self.pid != os.getpid() or self.backend is None:
            return
        receipt = dict(
            pid=self.pid,
            algorithm=ALGORITHM,
            backend_manifest_sha256=canonical_digest(self.manifest),
            provider=self.backend.provider_info,
            counts=dict(self.backend.counts),
        )
        path = self.receipts / (str(self.pid) + ".json")
        temporary = path.with_suffix(".partial")
        temporary.write_text(json.dumps(receipt, sort_keys=True, allow_nan=False) + "\n")
        temporary.replace(path)

    def provenance(self):
        self.flush()
        receipts = [json.loads(p.read_bytes()) for p in sorted(self.receipts.glob("*.json"))]
        binding = canonical_digest(self.manifest)
        if any(r["backend_manifest_sha256"] != binding for r in receipts):
            raise ValueError("Activation receipts belong to another backend")
        return dict(manifest=self.manifest, manifest_sha256=binding, receipts=receipts)
