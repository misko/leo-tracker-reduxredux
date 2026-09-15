"""Verify a packaged host detector before constructing its numerical engine."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from leo.analysis.host_decision import NativeHostDecision
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from leo.scanner.host_adaptive import HostDecisionConfigurationV1, HostDecisionConfigurationV2


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _verified_file(root: Path, relative: str, digest: str) -> Path:
    path = root / relative
    if (
        not relative
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
        or not path.resolve().is_relative_to(root.resolve())
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > 16 * 1024 * 1024
        or _sha(path.read_bytes()) != digest
    ):
        raise ValueError(f"host detector release file failed verification: {relative}")
    return path


@dataclass(frozen=True, slots=True)
class HostDecisionRelease:
    configuration: HostDecisionConfigurationV1 | HostDecisionConfigurationV2
    library: Path

    def create_engine(self) -> NativeHostDecision:
        return NativeHostDecision(
            self.library, source_rate_hz=self.configuration.source_rate_hz
        )

    def bind(self, configuration: HostDecisionConfigurationV2) -> HostDecisionRelease:
        configuration = HostDecisionConfigurationV2.model_validate(configuration)
        if (
            configuration.detector_manifest_sha256
            != self.configuration.detector_manifest_sha256
        ):
            raise ValueError("host detector configuration changed release identity")
        return HostDecisionRelease(configuration, self.library)


def load_host_decision_release(manifest: Path, expected_sha256: str) -> HostDecisionRelease:
    """A source-bound immutable release; no runtime compilation or RF access."""
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 1024 * 1024:
        raise ValueError("host detector release manifest is unavailable")
    raw = manifest.read_bytes()
    if _sha(raw) != expected_sha256:
        raise ValueError("host detector release manifest digest differs")
    value = json.loads(raw)
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "files", "sources", "templates_sha256"}
        or value["schema"] != "leo-host-decision-release-v1"
        or not isinstance(value["files"], dict)
        or set(value["files"]) != {"decision.so", "build.json", "qualification-seal.json"}
        or not isinstance(value["sources"], dict)
        or not {
            "analysis/host_decision.py",
            "analysis/starlink/templates.py",
            "analysis/native_presence/host_decision_coefficients.inc",
        }.issubset(value["sources"])
    ):
        raise ValueError("host detector release inventory is invalid")
    for relative, digest in value["files"].items():
        _verified_file(manifest.parent, relative, digest)
    source_root = Path(__file__).resolve().parents[1]
    for relative, digest in value["sources"].items():
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise ValueError("host detector source inventory is invalid")
        _verified_file(source_root, relative, digest)
    templates = np.ascontiguousarray(
        [
            qin_edge_pilot_frame(2_500_000, edge, symbol_roll=roll)
            for edge in ("lower", "upper")
            for roll in (0, 17)
        ],
        dtype="<c16",
    )
    if _sha(templates.tobytes()) != value["templates_sha256"]:
        raise ValueError("host detector generated templates differ from release")
    return HostDecisionRelease(
        HostDecisionConfigurationV1(detector_manifest_sha256=expected_sha256),
        manifest.parent / "decision.so",
    )
