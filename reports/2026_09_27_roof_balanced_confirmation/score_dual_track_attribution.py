"""Validate both fixed-point diagnostics, then attribute saved winner changes."""
import json
from pathlib import Path

import dual_track_attribution as attribution
import run_dual_track_diagnostic as runner

HERE = Path(__file__).resolve().parent


def analyze(payload, source):
    if set(payload["branches"]) != set(runner.base.PRIORS):
        raise ValueError("incomplete diagnostic priors")
    results = []
    for prior, branch in payload["branches"].items():
        expected = runner.fixed_inventory(source["branches"][prior])
        actual = branch["positions"]
        if len(expected) != len(actual):
            raise ValueError("fixed point inventory differs")
        by_label = {}
        for wanted, found in zip(expected, actual):
            if any(wanted[key] != found[key] for key in ("labels", "coordinate", "source")):
                raise ValueError("fixed point/source differs")
            parity = runner.aggregate_parity(wanted["source"], found["diagnostic"])
            if parity != found["aggregate_parity"]:
                raise ValueError("aggregate parity receipt differs")
            for label in found["labels"]:
                if label in by_label: raise ValueError("duplicate point label")
                by_label[label] = found
        if set(by_label) != {"D", "old", "detection", "dual"}:
            raise ValueError("missing point labels")
        for left, right in (("D", "dual"), ("detection", "dual"), ("D", "old")):
            for variant in runner.VARIANTS:
                result = attribution.compare(by_label[left]["diagnostic"],
                                             by_label[right]["diagnostic"], variant)
                results.append({"session_id": payload["session_id"], "prior": prior,
                    "from": left, "to": right,
                    "from_coordinate": by_label[left]["coordinate"],
                    "to_coordinate": by_label[right]["coordinate"], **result})
    return results


def main():
    target = HERE / "dual-track-attribution.json"
    if target.exists(): raise FileExistsError(target)
    entries, _ = runner.balanced.inputs()
    rows = []; inputs = {}
    report_bytes = (HERE / "dual-shared-geometry-distances.json").read_bytes()
    report = json.loads(report_bytes)
    if not report.get("complete"): raise ValueError("geographic report incomplete")
    for index in runner.ALLOWED_INDICES:
        sid = entries[index]["session_id"]
        path = HERE / f"dual-track-diagnostic-{sid}.json"
        body = path.read_bytes(); payload = json.loads(body)
        source_bytes = (HERE / f"dual-shared-geometry-replay-{sid}.json").read_bytes()
        source = json.loads(source_bytes)
        if (not payload.get("finished") or payload.get("session_id") != sid or
                payload.get("source_replay_sha256") != runner.base.digest(source_bytes) or
                report["replay_sha256"][sid] != runner.base.digest(source_bytes) or
                payload.get("source_report_sha256") != runner.base.digest(report_bytes) or
                payload.get("dual_track_diagnostic_protocol_sha256") != runner.base.digest(
                    (HERE / "DUAL_TRACK_DIAGNOSTIC_PROTOCOL.md").read_bytes())):
            raise ValueError("diagnostic source/protocol binding differs")
        for name, digest in payload["code_sha256"].items():
            if runner.base.digest((HERE / name).read_bytes()) != digest:
                raise ValueError("diagnostic code changed: " + name)
        for key in ("ratio_effect_binding", "detection_effect_binding", "calibration_sha256",
                    "calibration_source_hashes", "calibration_artifact_sha256", "contract_sha256",
                    "cache_sha256", "input_manifest_sha256", "analysis_manifest_sha256",
                    "evidence_sha256", "snapshot_digest", "topology_audit_sha256",
                    "model_hashes", "parameters", "topology_receipt"):
            if payload.get(key) != source.get(key):
                raise ValueError("diagnostic binding changed: " + key)
        inputs[path.name] = runner.base.digest(body)
        rows.extend(analyze(payload, source))
    output = {"complete": True, "input_sha256": inputs, "comparisons": rows,
        "code_sha256": {name: runner.base.digest((HERE / name).read_bytes()) for name in (
            "score_dual_track_attribution.py", "dual_track_attribution.py")},
        "scope": "Posthoc descriptive attribution at saved independent-prior winners; no new estimator or truth use."}
    runner.base.atomic(target, output)
    for row in rows:
        if row["variant"] == "dual" and row["to"] == "dual":
            print(row["session_id"], row["prior"], row["from"], row["to"],
                  row["changes"], row["totals"])


if __name__ == "__main__": main()
