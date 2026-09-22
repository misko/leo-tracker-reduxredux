#!/usr/bin/env python3
"""Replay regional Doppler scoring with deterministic full-span shape CV.

This exploratory adapter leaves the published replay implementation untouched.
Within every RF source trajectory, five chronological index blocks are formed;
blocks 0/2/4 train and blocks 1/3 evaluate.  Evaluation therefore measures
interpolation across the captured shape, not forecasting beyond the fit span.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

from leo.analysis.research.regional_doppler import ObservationArc

PARTITION = "five-chronological-blocks-train-0-2-4-heldout-1-3-v1"


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _selected(indices: np.ndarray, maximum: int) -> np.ndarray:
    if maximum and len(indices) > maximum:
        positions = np.unique(np.rint(np.linspace(0, len(indices) - 1, maximum)).astype(int))
        return indices[positions]
    return indices


class FiveBlockLoader:
    """Drop-in replay loader that records the exact response-free partition."""

    def __init__(self) -> None:
        self.documents: list[dict[str, object]] = []

    def __call__(self, document, max_per_partition=8, individual=False):
        sources = {row["tracklet_id"]: row for row in document["series"]}
        episodes = (
            [
                {"episode_id": key, "members": [key], "channel": row["channel"]}
                for key, row in sources.items()
            ]
            if individual
            else document["episodes"]
        )
        used: set[str] = set()
        output = []
        source_receipts = []
        for episode in episodes:
            times, values, segments, training = [], [], [], []
            episode_sources = []
            for number, key in enumerate(episode["members"]):
                row = sources[key]
                ids = list(row["candidate_ids"])
                if len(ids) != len(set(ids)) or used.intersection(ids):
                    raise ValueError("duplicate RF observations across episodes")
                used.update(ids)
                t = np.asarray(row["t_s"], dtype=float)
                y = np.asarray(row["y_hz"], dtype=float)
                if (
                    len(t) != len(y)
                    or len(t) != len(ids)
                    or row["actual_rf_hz"] <= 0
                    or not np.all(np.isfinite(t))
                    or not np.all(np.isfinite(y))
                ):
                    raise ValueError("invalid source observation arrays / RF metadata")
                order = np.argsort(t, kind="stable")
                blocks = np.array_split(order, 5)
                fit_members = np.concatenate([blocks[index] for index in (0, 2, 4)])
                test_members = np.concatenate([blocks[index] for index in (1, 3)])
                fit_full = fit_members[np.argsort(t[fit_members], kind="stable")]
                test_full = test_members[np.argsort(t[test_members], kind="stable")]
                if min(len(fit_full), len(test_full)) < 2:
                    raise ValueError("source too short for five-block partition")
                fit, test = (
                    _selected(fit_full, max_per_partition),
                    _selected(test_full, max_per_partition),
                )
                for part, is_training in ((fit, True), (test, False)):
                    times.extend(t[part])
                    values.extend(y[part])
                    segments.extend([number] * len(part))
                    training.extend([is_training] * len(part))
                labels = ["heldout"] * len(ids)
                for index in fit_full:
                    labels[int(index)] = "training"
                episode_sources.append(
                    {
                        "tracklet_id": key,
                        "observations": len(ids),
                        "full_training": len(fit_full),
                        "full_heldout": len(test_full),
                        "selected_training": len(fit),
                        "selected_heldout": len(test),
                        "partition_digest": _digest(
                            [
                                {"observation_id": identity, "partition": labels[index]}
                                for index, identity in enumerate(ids)
                            ]
                        ),
                    }
                )
            output.append(
                (
                    str(episode["episode_id"]),
                    ObservationArc(
                        np.asarray(times),
                        np.asarray(values),
                        np.asarray(segments),
                        np.asarray(training, dtype=bool),
                        # ObservationArc currently distinguishes only causal
                        # chronological versus noncausal full-span masks. The
                        # exact five-block policy is bound by our receipt.
                        partition="randomized",
                    ),
                )
            )
            source_receipts.append(
                {"episode_id": str(episode["episode_id"]), "sources": episode_sources}
            )
        receipt = {
            "source_document_digest": _digest(document),
            "partition": PARTITION,
            "max_per_partition": max_per_partition,
            "episodes": source_receipts,
            "episode_count": len(output),
            "full_observation_count": sum(
                source["observations"]
                for episode in source_receipts
                for source in episode["sources"]
            ),
            "selected_observation_count": sum(len(arc.time_s) for _, arc in output),
        }
        receipt["content_digest"] = _digest(receipt)
        self.documents.append(receipt)
        return output


def _load_replay(path: Path):
    spec = importlib.util.spec_from_file_location("five_block_base_replay", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("regional replay has no loader")
    spec.loader.exec_module(module)
    return module


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def run(args) -> None:
    replay_path = Path(__file__).parents[1] / "replay_regional_doppler.py"
    replay = _load_replay(replay_path)
    loader = FiveBlockLoader()
    replay.load_observations = loader
    replay.run(args)
    receipt = {
        "schema": "regional-five-block-partition-receipt/v1",
        "partition": PARTITION,
        "interpretation": "full-span interpolation/shape CV; not future forecasting",
        "position_truth_used": False,
        "base_replay_digest": "sha256:" + hashlib.sha256(replay_path.read_bytes()).hexdigest(),
        "adapter_digest": "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "documents": loader.documents,
        "document_count": len(loader.documents),
        "episode_count": sum(int(row["episode_count"]) for row in loader.documents),
        "full_observation_count": sum(
            int(row["full_observation_count"]) for row in loader.documents
        ),
        "selected_observation_count": sum(
            int(row["selected_observation_count"]) for row in loader.documents
        ),
    }
    receipt["content_digest"] = _digest(receipt)
    _write(args.output / "partition-receipt.json", receipt)
    for name in ("configuration.json", "result.json"):
        path = args.output / name
        document = json.loads(path.read_text())
        document.update(
            {
                "partition": PARTITION,
                "partition_receipt_digest": receipt["content_digest"],
                "partition_interpretation": receipt["interpretation"],
            }
        )
        _write(path, document)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--center-lat", type=float, required=True)
    parser.add_argument("--center-lon", type=float, required=True)
    parser.add_argument("--region-size-km", type=float, default=5000.0)
    parser.add_argument("--spacing-km", type=float, default=50.0)
    parser.add_argument("--altitude-m", type=float, default=0.0)
    parser.add_argument("--sigma-hz", type=float, default=250.0)
    parser.add_argument("--effective-count", type=float, default=6.0)
    parser.add_argument("--clock-s", type=float, default=0.0)
    parser.add_argument("--max-per-partition", type=int, default=6)
    parser.add_argument("--scan-limit", type=int)
    parser.add_argument("--shifted-grid", action="store_true")
    parser.add_argument("--individual-sources", action="store_true")
    parser.add_argument("--points", type=Path)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
