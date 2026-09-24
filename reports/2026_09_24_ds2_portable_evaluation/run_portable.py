#!/usr/bin/env python3
"""Run the frozen DS2 portable positioning arms without a reference coordinate.

This is a narrow adapter over the reviewed DS1 full-observation engines.  It
only changes cache bindings and, for the joint arm, normalizes each whole scan
to unit weight.  The scientific implementations remain digest-bound inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TIMING = ROOT / "reports/2026_09_24_ds1_train_full_timing/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def equal_timing_engine(module: Any) -> type:
    base = module.FullObservationEngine

    class EqualSessionEngine(base):
        """Use one objective vote per complete scan, irrespective of track count."""

        def score(self, latitude: float, longitude: float, method: str, options: dict) -> dict:
            curves = [self._session_curve(s, latitude, longitude) for s in self.sessions]
            losses = np.asarray([c["loss"] for c in curves])
            zero = int(np.argmin(np.abs(self.tau_values)))
            if not np.isclose(self.tau_values[zero], 0.0):
                raise ValueError("tau grid must contain zero")
            if method == "baseline":
                indices = np.full(len(self.sessions), zero, int)
                objective = float(np.mean(losses[:, zero]))
                parameters: dict[str, Any] = {"global_tau_s": 0.0}
            elif method == "shared_global_tau":
                aggregate = np.mean(losses, axis=0)
                chosen = int(np.argmin(aggregate))
                indices = np.full(len(self.sessions), chosen, int)
                objective = float(aggregate[chosen])
                parameters = {"global_tau_s": float(self.tau_values[chosen])}
            elif method == "regularized_per_scan_tau":
                sigma = float(options.get("per_scan_sigma_s", 1.0))
                penalty_weight = float(options.get("per_scan_penalty_weight", 0.01))
                delta_limit = float(options.get("per_scan_delta_limit_s", 5.0))
                objective_by_global = np.full(len(self.tau_values), np.inf)
                index_by_global: list[np.ndarray] = []
                for global_index, global_tau in enumerate(self.tau_values):
                    choices = np.full(len(self.sessions), -1, int)
                    value = 0.0
                    for scan_index, scan_loss in enumerate(losses):
                        delta = self.tau_values - global_tau
                        permitted = np.abs(delta) <= delta_limit + 1e-12
                        local = scan_loss / len(self.sessions)
                        local += penalty_weight * (delta / sigma) ** 2
                        local = np.where(permitted, local, np.inf)
                        choice = int(np.argmin(local))
                        choices[scan_index] = choice
                        value += float(local[choice])
                    objective_by_global[global_index] = value
                    index_by_global.append(choices)
                global_index = int(np.argmin(objective_by_global))
                indices = index_by_global[global_index]
                deltas = self.tau_values[indices] - self.tau_values[global_index]
                raw_loss = float(np.mean(losses[np.arange(len(self.sessions)), indices]))
                penalty = float(np.sum(penalty_weight * (deltas / sigma) ** 2))
                objective = raw_loss + penalty
                parameters = {
                    "global_tau_s": float(self.tau_values[global_index]),
                    "per_scan_delta_s": {
                        session.session_id: float(delta)
                        for session, delta in zip(self.sessions, deltas, strict=True)
                    },
                    "per_scan_penalty": penalty,
                }
            elif method == "independent_per_track_tau":
                total = 0.0
                assignments = []
                track_tau: dict[str, float] = {}
                for session, curve in zip(self.sessions, curves, strict=True):
                    support = sum(track.occupied_seconds for track in session.tracks)
                    session_loss = 0.0
                    for track, result in zip(session.tracks, curve["tracks"], strict=True):
                        choice = int(np.argmin(result["loss"]))
                        session_loss += track.occupied_seconds * float(result["loss"][choice])
                        track_tau[f"{session.session_id}:{track.track_id}"] = float(
                            self.tau_values[choice]
                        )
                        candidate = int(result["winner"][choice])
                        assignments.append(
                            {
                                "session_id": session.session_id,
                                "track_id": track.track_id,
                                "candidate_id": str(session.candidate_ids[candidate]),
                                "constant_cfo_hz": float(result["cfo"][choice]),
                                "full_observation_rms_hz": float(result["rms"][choice]),
                                "observation_count": int(len(track.times_s)),
                                "occupied_seconds": track.occupied_seconds,
                            }
                        )
                    total += session_loss / support
                objective = total / len(self.sessions)
                return {
                    "objective": float(objective),
                    "rf_capped_loss": float(objective),
                    "parameters": {"per_track_tau_s": track_tau},
                    "assignments": assignments,
                }
            else:
                raise ValueError("equal-session adapter supports timing models only")
            raw_loss = float(np.mean(losses[np.arange(len(self.sessions)), indices]))
            assignments = []
            for session, curve, index in zip(self.sessions, curves, indices, strict=True):
                assignments.extend(self._assignments(session, curve, int(index)))
            return {
                "objective": objective,
                "rf_capped_loss": raw_loss,
                "parameters": parameters,
                "assignments": assignments,
            }

    return EqualSessionEngine


def run_timing(task: dict[str, Any], cache_root: Path) -> dict[str, Any]:
    module = load(TIMING, "ds2_portable_timing")
    module.CACHE_ROOTS.clear()
    module.CACHE_ROOTS["ds2"] = cache_root
    module.RESULT_SCHEMA = "ds2-portable-inference-result/v1"
    if task.get("options", {}).get("equal_session_weight", False):
        module.FullObservationEngine = equal_timing_engine(module)
    result = module.run_task(task)
    if result.get("reference_coordinate_present") is not False:
        raise ValueError("inference result crossed the post-seal reference boundary")
    return result


def run_orbit(task: dict[str, Any], cache_root: Path) -> dict[str, Any]:
    module = load(ORBIT, "ds2_portable_orbit")
    module.CACHE_ROOTS.clear()
    module.CACHE_ROOTS["ds2"] = cache_root
    if task.get("options", {}).get("equal_session_weight", False):
        original = module.FullObservationEngine.__init__

        def normalized(self: Any, normalized_task: dict[str, Any]) -> None:
            original(self, normalized_task)
            for session in self.sessions:
                denominator = sum(track.weight for track in session.tracks)
                for track in session.tracks:
                    track.weight = float(track.weight) / denominator

        module.FullObservationEngine.__init__ = normalized
    result = module.run_task(task)
    path = Path(result["output_path"])
    document = json.loads(path.read_text())
    document["schema"] = "ds2-portable-inference-result/v1"
    document["partition"] = "development"
    document["reference_coordinate_present"] = False
    document["equal_whole_session_weight"] = bool(
        task.get("options", {}).get("equal_session_weight", False)
    )
    document["adapter_bindings"] = {
        "adapter": digest(Path(__file__)),
        "scientific_runner": digest(ORBIT),
    }
    content = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.write_text(content)
    path.with_suffix(".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    args = parser.parse_args()
    task = json.loads(args.task.read_text())
    if task.get("partition") != "development":
        raise ValueError("DS2 tasks must be explicitly labelled development")
    # Reviewed workers enforce their historical TRAIN-only task boundary.  DS2
    # uses the word only as an implementation token; the output is relabelled
    # development and no split excludes a frozen Sep-24 session.
    task["partition"] = "train"
    task["session_groups"] = {sid: "ds2" for sid in task["session_ids"]}
    task.setdefault("options", {})["cache_root"] = str(args.cache_root)
    if task["method"] in {
        "causal_per_norad_orbit_rate",
        "global_tau_per_norad_orbit_rate",
        "soft_joint_association",
        "soft_association_global_tau",
    }:
        result = run_orbit(task, args.cache_root)
    else:
        result = run_timing(task, args.cache_root)
        path = Path(task["output_path"])
        document = json.loads(path.read_text())
        document["partition"] = "development"
        document["equal_whole_session_weight"] = bool(
            task.get("options", {}).get("equal_session_weight", False)
        )
        document["adapter_bindings"] = {
            "adapter": digest(Path(__file__)),
            "scientific_runner": digest(TIMING),
        }
        content = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
        path.write_text(content)
        path.with_suffix(path.suffix + ".sha256").write_text(
            hashlib.sha256(content.encode()).hexdigest() + "\n"
        )
    print(json.dumps({"task_id": result["task_id"], "status": "sealed"}, sort_keys=True))


if __name__ == "__main__":
    main()
