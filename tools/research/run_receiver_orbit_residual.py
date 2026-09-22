#!/usr/bin/env python3
"""Run the frozen-position receiver-versus-satellite residual diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import asdict, replace
from pathlib import Path

for _variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_variable] = "1"

import numpy as np  # noqa: E402

from leo.analysis.research.receiver_orbit_residual import (  # noqa: E402
    ResidualCandidate,
    ResidualDiagnosticConfig,
    ResidualEpisode,
    diagnose_receiver_orbit_residuals,
)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: object) -> str:
    # JSON object keys are strings. Normalize through JSON before sorting so a
    # document containing integer NORAD keys hashes identically after reload.
    normalized = json.loads(json.dumps(value, allow_nan=False))
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def verify_content_digest(value: dict[str, object]) -> None:
    expected = value.get("content_digest")
    body = dict(value)
    body.pop("content_digest", None)
    if expected != canonical_digest(body):
        raise ValueError("document content digest mismatch")


def safe_child(directory: Path, name: str) -> Path:
    if not name or Path(name).name != name:
        raise ValueError("session file must be a safe basename")
    return directory / name


def load_episode(session_id: str, value: dict[str, object]) -> ResidualEpisode:
    support = value["candidate_support"]
    candidates_json = support["candidates"]
    if not candidates_json:
        raise ValueError("episode has no frozen candidates")
    reference = candidates_json[0]["rows"]
    keys = [
        (row["observation_id"], row["utc_ns"], row["training"], row["receiver_id"])
        for row in reference
    ]
    candidates = []
    for candidate in candidates_json:
        rows = candidate["rows"]
        candidate_keys = [
            (row["observation_id"], row["utc_ns"], row["training"], row["receiver_id"])
            for row in rows
        ]
        if candidate_keys != keys:
            raise ValueError("candidate rows are not aligned within episode")
        candidates.append(
            ResidualCandidate(
                catalog_number=int(candidate["catalog_number"]),
                soft_weight=float(candidate["soft_weight"]),
                residual_hz=np.asarray([row["residual_hz"] for row in rows]),
                satellite_design_hz_per_unit=np.asarray(
                    [row["satellite_design_hz_per_s_h"] for row in rows]
                ),
            )
        )
    receiver_ids = {int(row["receiver_id"]) for row in reference}
    if len(receiver_ids) != 1:
        raise ValueError("episode spans multiple physical receiver paths")
    # CFO and residuals were normalized by the exporter to the canonical 11.2 GHz
    # RF. A shared coefficient therefore describes normalized frequency drift.
    receiver_group = f"receiver-{receiver_ids.pop()}"
    return ResidualEpisode(
        episode_id=f"{session_id}:{value['episode_id']}",
        receiver_drift_group=receiver_group,
        time_s=np.asarray([row["time_s"] for row in reference]),
        training=np.asarray([row["training"] for row in reference], dtype=bool),
        candidates=tuple(candidates),
        null_probability=float(support["null_probability"]),
        omitted_probability_mass=float(support["omitted_probability_mass"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    manifest_path = args.input / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    verify_content_digest(manifest)
    required = {
        "diagnostic_only": True,
        "truth_accessed": False,
        "known_position_used": False,
        "site_conditioned_candidates_used": False,
    }
    if any(manifest.get(key) is not value for key, value in required.items()):
        raise ValueError("input manifest does not assert the truth-free diagnostic contract")
    episodes = []
    inputs = {"manifest.json": digest(manifest_path)}
    for item in manifest["sessions"]:
        path = safe_child(args.input, item["file"])
        if digest(path) != item["digest"]:
            raise ValueError(f"session digest mismatch: {item['file']}")
        inputs[item["file"]] = item["digest"]
        session = json.loads(path.read_text())
        verify_content_digest(session)
        episodes.extend(load_episode(session["session_id"], value) for value in session["episodes"])
    config = ResidualDiagnosticConfig()
    started = time.monotonic()
    result = diagnose_receiver_orbit_residuals(tuple(episodes), config)
    sensitivity = diagnose_receiver_orbit_residuals(
        tuple(
            replace(
                episode,
                receiver_drift_group=(
                    f"{episode.episode_id.split(':', 1)[0]}:{episode.receiver_drift_group}"
                ),
            )
            for episode in episodes
        ),
        config,
    )
    weak_receiver_prior = diagnose_receiver_orbit_residuals(
        tuple(episodes), replace(config, receiver_slope_sigma_hz_h=50_000.0)
    )
    runtime_s = time.monotonic() - started
    source_paths = [
        Path(__file__),
        Path(__file__).parents[2]
        / "src/leo/analysis/research/receiver_orbit_residual.py",
    ]
    document = {
        "schema": "receiver-orbit-residual-diagnostic/v1",
        "diagnostic_only": True,
        "truth_accessed": False,
        "position_and_identity_weights_frozen": True,
        "receiver_grouping": "physical receiver_id; canonical-11.2GHz normalized residuals",
        "inputs": inputs,
        "input_content_digest": manifest["content_digest"],
        "configuration": asdict(config),
        "result": asdict(result),
        "sensitivity_per_session_receiver": asdict(sensitivity),
        "sensitivity_weak_receiver_prior": asdict(weak_receiver_prior),
        "runtime": {"elapsed_s": runtime_s, "thread_limit": 1},
        "sources": {
            str(path.relative_to(Path(__file__).parents[2])): digest(path)
            for path in source_paths
        },
        "limitations": [
            "satellite coefficients are descriptive phase-rate proxies, not orbit corrections",
            "receiver coefficients are normalized frequency slopes, not UTC clock offsets",
            "top-eight frozen support omits catalogue alternatives and cannot refresh identity",
            "within-episode heldout scoring is retrospective and not whole-scan transfer",
            "500 and 50000 normalized-Hz/hour receiver priors are sensitivity arms, not calibrated",
        ],
    }
    document["content_digest"] = canonical_digest(document)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
