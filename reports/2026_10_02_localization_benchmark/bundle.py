"""Read one frozen localization benchmark bundle through the prototype Data port."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
COMMON_PATH = ROOT.parent / "2026_10_02_coherent_localization" / "common.py"
ARRAY_NAMES = (
    "times",
    "measured",
    "rf",
    "receiver",
    "channel",
    "group",
    "margin",
    "nodes",
    "position",
    "velocity",
    "numbers",
    "initial",
)


def _load_common():
    spec = importlib.util.spec_from_file_location("coherent_localization_common", COMMON_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load coherent localization adapter from {COMMON_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_COMMON = _load_common()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Data(_COMMON.Data):
    """Bundle-backed adapter with the same numerical interface as ``common.Data``."""

    def __init__(self, directory: str | Path):
        directory = Path(directory)
        manifest_path = directory / "bundle.json"
        archive_path = directory / "bundle.npz"
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("schema") != "coherent-localization-bundle/v1":
            raise ValueError("Unsupported localization bundle schema")
        expected_digest = manifest.get("artifacts", {}).get("bundle_npz_sha256")
        if expected_digest and sha256_file(archive_path) != expected_digest:
            raise ValueError("bundle.npz digest does not match bundle.json")
        with np.load(archive_path, allow_pickle=False) as arrays:
            missing = sorted(set(ARRAY_NAMES) - set(arrays.files))
            if missing:
                raise ValueError(f"bundle.npz lacks arrays: {', '.join(missing)}")
            for name in ARRAY_NAMES:
                setattr(self, name, arrays[name].copy())
        self.session_id = manifest["session_id"]
        self.tracks = [
            {
                **track,
                "rows": np.asarray(track["rows"], dtype=int),
                "candidate_indices": np.asarray(track["candidate_indices"], dtype=int),
            }
            for track in manifest["tracks"]
        ]
        self.provenance = manifest["provenance"]
        self.join_receipt = manifest.get("track_mapping", {})
        self._validate()

    def _validate(self) -> None:
        observation_count = len(self.times)
        if observation_count == 0 or not np.all(np.isfinite(self.times)):
            raise ValueError("times must be a nonempty finite vector")
        for name in ("measured", "rf", "receiver", "channel", "group", "margin"):
            if getattr(self, name).shape != (observation_count,):
                raise ValueError(f"{name} does not align with times")
        for name in ("measured", "rf", "margin"):
            if not np.all(np.isfinite(getattr(self, name))):
                raise ValueError(f"{name} must be finite")
        for name in ("receiver", "channel", "group"):
            values = getattr(self, name)
            if not np.issubdtype(values.dtype, np.integer):
                raise ValueError(f"{name} must contain integers")
        if not set(int(value) for value in self.receiver).issubset({0, 1}):
            raise ValueError("receiver values must be 0 or 1")
        if np.any(self.channel < 1) or np.any(self.group < 0):
            raise ValueError("channel and group indices must be nonnegative with positive channels")
        spacing = np.diff(self.nodes)
        if (
            self.nodes.ndim != 1
            or len(self.nodes) < 2
            or not np.all(np.isfinite(self.nodes))
            or not np.all(spacing > 0)
            or not np.allclose(spacing, spacing[0], rtol=0.0, atol=1e-12)
        ):
            raise ValueError("nodes must be a finite, strictly increasing, uniformly spaced vector")
        candidate_count = len(self.numbers)
        if candidate_count != 64:
            raise ValueError("bundle must contain exactly 64 candidates")
        if not np.issubdtype(self.numbers.dtype, np.integer):
            raise ValueError("candidate catalogue numbers must be integers")
        expected_state_shape = (candidate_count, len(self.nodes), 3)
        if (
            self.position.shape != expected_state_shape
            or self.velocity.shape != expected_state_shape
        ):
            raise ValueError("state arrays do not align with numbers and nodes")
        if not np.all(np.isfinite(self.position)) or not np.all(np.isfinite(self.velocity)):
            raise ValueError("candidate states must be finite")
        if self.initial.shape != (6 + candidate_count,):
            raise ValueError(
                "initial must contain position, two RX lines, and one shift per candidate"
            )
        if not np.all(np.isfinite(self.initial)):
            raise ValueError("initial must be finite")
        if len(set(int(value) for value in self.numbers)) != candidate_count:
            raise ValueError("candidate catalogue numbers must be unique")
        expected_candidates = np.arange(candidate_count)
        for track in self.tracks:
            rows = track["rows"]
            candidates = track["candidate_indices"]
            if rows.ndim != 1 or np.any(rows < 0) or np.any(rows >= observation_count):
                raise ValueError("track rows fall outside the raw observation arrays")
            if not np.array_equal(candidates, expected_candidates):
                raise ValueError("every track must expose the complete candidate bank")


__all__ = ["Data", "sha256_file"]
