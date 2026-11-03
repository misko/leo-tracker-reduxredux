"""Post-run integrity audit, separate from the frozen model implementation."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()

def audit():
    frozen_path = HERE / "execution-freeze.json"
    frozen = json.loads(frozen_path.read_text())
    freeze_hash = digest(frozen_path)
    if digest(HERE / "preparation-audit.json") != frozen["preparation_audit_sha256"]:
        raise ValueError("preparation audit changed")
    journal_path = HERE / "tle-publications.jsonl"
    journal_hash = digest(journal_path)
    publications = set()
    for line in journal_path.read_text().splitlines():
        try:
            event = json.loads(line)
            message = json.loads(event["MESSAGE"])
            published_ns = int(event["__REALTIME_TIMESTAMP"])*1000
        except (KeyError, ValueError, TypeError):
            continue
        if message.get("event") == "tle_collection":
            publications.update((p.get("provider"),p.get("digest"),published_ns)
                                for p in message.get("providers",[]) if p.get("status") == "published")
    verified_snapshots = {}
    for category in ("sources", "evidence"):
        for path, expected in frozen[category].items():
            if digest(path) != expected:
                raise ValueError(f"{category} hash mismatch: {path}")
    selected = {r["unit_id"]:r for rows in json.loads((HERE / "selection.json").read_text())["selected"].values() for r in rows}
    if len(frozen["units"]) != 32 or len(set(frozen["units"])) != 32 or len(set(frozen["arms"])) != 15:
        raise ValueError("panel dimensions differ")
    seals, launches = {}, {}
    for unit in frozen["units"]:
        evidence = json.loads((HERE / "evidence" / f"{unit}.json").read_text())
        orbit = json.loads((HERE / "evidence" / f"{unit}-orbits.json").read_text())
        if evidence["session_id"] != selected[unit]["session_id"] or evidence["manifest_sha256"] != selected[unit]["manifest_sha256"]:
            raise ValueError("selected evidence identity mismatch")
        if digest(evidence["source"]["path"]) != evidence["source"]["sha256"]:
            raise ValueError("raw observation export digest mismatch")
        if orbit["session_id"] != evidence["session_id"] or orbit["observation_sha256"] != evidence["source"]["sha256"]:
            raise ValueError("orbit observation binding mismatch")
        source_observations = json.loads(Path(evidence["source"]["path"]).read_text())
        cutoff = min(source_observations["start_utc_ns"], selected[unit].get("capture_start_earliest_utc_ns",selected[unit]["capture_start_utc_ns"]))
        if digest(orbit["state_file"]) != orbit["state_sha256"] or not orbit["tle"]["causal"]:
            raise ValueError("orbit states or causality mismatch")
        if orbit["tle"]["publication_log_sha256"] != journal_hash:
            raise ValueError("publication log digest mismatch")
        for source in orbit["tle"]["sources"]:
            if not max(source["collected_utc_ns"],source["mtime_ns"]) <= source["published_utc_ns"] < source["cutoff_utc_ns"]:
                raise ValueError("causal publication proof mismatch")
            if source["cutoff_utc_ns"] != cutoff:
                raise ValueError("publication cutoff differs from capture")
            if (source["provider"],source["sha256"],source["published_utc_ns"]) not in publications:
                raise ValueError("exact publication receipt absent from journal")
            snapshot_path = Path(source["path"])
            if source["path"] not in verified_snapshots:
                verified_snapshots[source["path"]] = digest(snapshot_path)
            if verified_snapshots[source["path"]] != source["sha256"] or snapshot_path.stat().st_mtime_ns != source["mtime_ns"]:
                raise ValueError("causal snapshot bytes or modification time differ")
        for arm in frozen["arms"]:
            prediction_path = HERE / "runs" / f"{unit}-{arm}.json"
            launch_path = prediction_path.with_suffix(".launch.json")
            launch = json.loads(launch_path.read_text())
            if (launch["unit"],launch["arm"],launch["execution_freeze_sha256"]) != (unit,arm,freeze_hash):
                raise ValueError("launch identity/freeze mismatch")
            command = launch["command"]
            for option, expected in (("--unit",unit),("--arm",arm),("--output",str(prediction_path)),("--evidence-root",str(HERE / "evidence"))):
                if command.count(option) != 1 or command[command.index(option)+1] != expected:
                    raise ValueError("launch command cell arguments differ")
            if frozen["python"] not in command or str(HERE / "run_arm.py") not in command:
                raise ValueError("launch interpreter or runner differs")
            if digest(prediction_path.with_suffix(".log")) != launch["log_sha256"]:
                raise ValueError("launch log mismatch")
            if prediction_path.exists():
                if launch["prediction"] != str(prediction_path):
                    raise ValueError("launch prediction path mismatch")
                seal_path = prediction_path.with_suffix(".seal.json")
                if json.loads(seal_path.read_text())["prediction_sha256"] != digest(prediction_path):
                    raise ValueError("prediction seal mismatch")
                prediction = json.loads(prediction_path.read_text())
                if (prediction["unit_id"],prediction["arm"]) != (unit,arm):
                    raise ValueError("prediction identity mismatch")
                if prediction.get("session_id",evidence["session_id"]) != evidence["session_id"]:
                    raise ValueError("prediction session mismatch")
                for path, expected in prediction.get("inputs",{}).items():
                    if digest(path) != expected:
                        raise ValueError("prediction input digest mismatch")
                if prediction["status"] != launch["status"] or prediction["reference_coordinate_accessed"] is not False:
                    raise ValueError("status or truth isolation mismatch")
                seals[str(seal_path)] = digest(seal_path)
            elif launch["prediction"] is not None or launch["returncode"] == 0:
                raise ValueError("successful launch without sealed prediction")
            elif launch["status"] not in ("timeout","error"):
                raise ValueError("unsealed attempt has invalid terminal status")
            launches[str(launch_path)] = digest(launch_path)
    result = {"passed": True, "planned_cells": 480, "launch_receipts": len(launches),
              "sealed_predictions": len(seals), "execution_freeze_sha256": freeze_hash,
              "audit_source_sha256": digest(__file__), "launch_sha256": launches, "seal_sha256": seals,
              "geographic_errors_accessed": False}
    with (HERE / "final-integrity-audit.json").open("x") as stream:
        json.dump(result,stream,indent=2)
    print(json.dumps({k:result[k] for k in ("passed","planned_cells","launch_receipts","sealed_predictions")}))

if __name__ == "__main__": audit()
