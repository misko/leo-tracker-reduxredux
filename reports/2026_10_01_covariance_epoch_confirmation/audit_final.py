"""Final 128-cell integrity and causal-input audit, without geographic truth."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED_ARMS = ("C1", "M2", "M4", "M24")
EXPECTED_CELLS = 128


def digest(path: Path | str) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit() -> dict:
    frozen_path = HERE / "execution-freeze.json"
    frozen = json.loads(frozen_path.read_text())
    freeze_hash = digest(frozen_path)
    if frozen["arms"] != list(EXPECTED_ARMS) or len(frozen["units"]) != 32:
        raise ValueError("frozen matrix is not 32 scans x four declared arms")
    if frozen.get("expected_cells") != EXPECTED_CELLS:
        raise ValueError("frozen expected-cell count differs")
    if digest(HERE / "preparation-audit.json") != frozen["preparation_audit_sha256"]:
        raise ValueError("preparation audit changed")
    for category in ("sources", "evidence"):
        for path, expected in frozen[category].items():
            if digest(path) != expected:
                raise ValueError(f"{category} hash mismatch: {path}")
    selected = {
        row["unit_id"]: row
        for group in json.loads((HERE / "selection.json").read_text())["selected"].values()
        for row in group
    }
    journal_path = HERE / "tle-publications.jsonl"
    journal_hash = digest(journal_path)
    publications = set()
    for line in journal_path.read_text().splitlines():
        try:
            event = json.loads(line)
            message = json.loads(event["MESSAGE"])
            published_ns = int(event["__REALTIME_TIMESTAMP"]) * 1000
        except (KeyError, ValueError, TypeError):
            continue
        if message.get("event") == "tle_collection":
            publications.update(
                (provider.get("provider"), provider.get("digest"), published_ns)
                for provider in message.get("providers", [])
                if provider.get("status") == "published"
            )
    launches: dict[str, str] = {}
    seals: dict[str, str] = {}
    snapshots: dict[str, str] = {}
    for unit in frozen["units"]:
        evidence_path = HERE / "evidence" / f"{unit}.json"
        orbit_path = HERE / "evidence" / f"{unit}-orbits.json"
        evidence = json.loads(evidence_path.read_text())
        orbit = json.loads(orbit_path.read_text())
        if evidence["session_id"] != selected[unit]["session_id"] or evidence["manifest_sha256"] != selected[unit]["manifest_sha256"]:
            raise ValueError("selected evidence identity mismatch")
        if digest(evidence["source"]["path"]) != evidence["source"]["sha256"]:
            raise ValueError("observation export digest mismatch")
        if orbit["session_id"] != evidence["session_id"] or orbit["observation_sha256"] != evidence["source"]["sha256"]:
            raise ValueError("orbit observation binding mismatch")
        source = json.loads(Path(evidence["source"]["path"]).read_text())
        cutoff = min(source["start_utc_ns"], selected[unit].get("capture_start_earliest_utc_ns", selected[unit]["capture_start_utc_ns"]))
        if digest(orbit["state_file"]) != orbit["state_sha256"] or orbit["tle"]["causal"] is not True:
            raise ValueError("orbit state digest or causal declaration mismatch")
        if orbit["tle"]["publication_log_sha256"] != journal_hash:
            raise ValueError("publication journal binding mismatch")
        for tle_source in orbit["tle"]["sources"]:
            if not max(tle_source["collected_utc_ns"], tle_source["mtime_ns"]) <= tle_source["published_utc_ns"] < tle_source["cutoff_utc_ns"]:
                raise ValueError("causal TLE publication ordering mismatch")
            if tle_source["cutoff_utc_ns"] != cutoff:
                raise ValueError("TLE cutoff differs from capture cutoff")
            proof = (tle_source["provider"], tle_source["sha256"], tle_source["published_utc_ns"])
            if proof not in publications:
                raise ValueError("exact TLE publication receipt absent")
            snapshot_path = Path(tle_source["path"])
            snapshots.setdefault(tle_source["path"], digest(snapshot_path))
            if snapshots[tle_source["path"]] != tle_source["sha256"] or snapshot_path.stat().st_mtime_ns != tle_source["mtime_ns"]:
                raise ValueError("causal snapshot bytes or mtime differ")
        for arm in EXPECTED_ARMS:
            prediction_path = HERE / "runs" / f"{unit}-{arm}.json"
            launch_path = prediction_path.with_suffix(".launch.json")
            launch = json.loads(launch_path.read_text())
            if (launch["unit"], launch["arm"], launch["execution_freeze_sha256"]) != (unit, arm, freeze_hash):
                raise ValueError("launch identity or freeze binding mismatch")
            command = launch["command"]
            for option, expected in (("--unit", unit), ("--arm", arm), ("--output", str(prediction_path)), ("--evidence-root", str(HERE / "evidence"))):
                if command.count(option) != 1 or command[command.index(option) + 1] != expected:
                    raise ValueError("launch command cell arguments differ")
            if frozen["python"] not in command or str(HERE / "run_arm.py") not in command:
                raise ValueError("launch interpreter or runner differs")
            log_path = prediction_path.with_suffix(".log")
            if digest(log_path) != launch["log_sha256"]:
                raise ValueError("launch log mismatch")
            if prediction_path.exists():
                if launch["prediction"] != str(prediction_path):
                    raise ValueError("launch prediction path mismatch")
                seal_path = prediction_path.with_suffix(".seal.json")
                if json.loads(seal_path.read_text())["prediction_sha256"] != digest(prediction_path):
                    raise ValueError("prediction seal mismatch")
                prediction = json.loads(prediction_path.read_text())
                if (prediction["unit_id"], prediction["arm"]) != (unit, arm):
                    raise ValueError("prediction identity mismatch")
                if prediction.get("session_id", evidence["session_id"]) != evidence["session_id"]:
                    raise ValueError("prediction session mismatch")
                for path, expected in prediction.get("inputs", {}).items():
                    if digest(path) != expected:
                        raise ValueError("prediction input digest mismatch")
                if prediction["status"] != launch["status"] or prediction.get("reference_coordinate_accessed") is not False:
                    raise ValueError("prediction status or truth isolation mismatch")
                seals[str(seal_path)] = digest(seal_path)
            elif launch["prediction"] is not None or launch["returncode"] == 0:
                raise ValueError("successful launch lacks a sealed prediction")
            elif launch["status"] not in ("timeout", "error"):
                raise ValueError("unsealed attempt has invalid status")
            launches[str(launch_path)] = digest(launch_path)
    if len(launches) != EXPECTED_CELLS:
        raise ValueError("launch matrix is incomplete")
    result = {
        "schema": "covariance-epoch-final-integrity/v1",
        "passed": True,
        "planned_cells": EXPECTED_CELLS,
        "launch_receipts": len(launches),
        "sealed_predictions": len(seals),
        "execution_freeze_sha256": freeze_hash,
        "audit_source_sha256": digest(__file__),
        "launch_sha256": launches,
        "seal_sha256": seals,
        "geographic_errors_accessed": False,
    }
    output = HERE / "final-integrity-audit.json"
    with output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ("passed", "planned_cells", "launch_receipts", "sealed_predictions")}))
    return result


if __name__ == "__main__":
    audit()
