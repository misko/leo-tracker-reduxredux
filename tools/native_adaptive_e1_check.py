#!/usr/bin/env python3
"""Recorded IQ -> native fractional GLRT -> native physical observations.

This development harness uses only timing/RF authority from the projection
fixture. It never supplies saved candidates or reference locations to inference.
The four-visit selection is not a complete scan or a server-parity assertion.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--detector", type=Path, required=True)
    p.add_argument("--projector", type=Path, required=True)
    p.add_argument("--replay-manifest", type=Path, required=True)
    p.add_argument("--selection-manifest", type=Path, required=True)
    p.add_argument("--source-authority", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    selection = json.loads(a.selection_manifest.read_text())
    inventory = {row["raw_sha256"]: row for row in selection["rows"]}
    bindings = []
    for line in a.replay_manifest.read_text().splitlines():
        fields = line.split("\t")
        if len(fields) != 8:
            raise ValueError("invalid detector schedule")
        metadata = json.loads(fields[7])
        digest = sha(fields[6])
        if digest != metadata["raw_sha256"] or digest not in inventory:
            raise ValueError("IQ authority mismatch")
        bindings.append(
            dict(raw_sha256=digest, exact_sha256=sha(fields[4]), control_sha256=sha(fields[5]))
        )
    sources = {}
    for line in a.source_authority.read_text().splitlines():
        source = json.loads(line)["source"]
        key = (source["visit"], source["receiver"], source["probe_index"])
        if key in sources and sources[key] != source:
            raise ValueError("conflicting timing authority")
        sources[key] = source
    algorithm = dict(
        detector_sha256=sha(a.detector),
        mode="ordinary-with-fractional-epoch",
        template_bindings=bindings,
    )
    analysis_digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(algorithm, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    native = subprocess.run(
        [str(a.detector), "--manifest", str(a.replay_manifest), "--fractional-epoch"],
        text=True,
        capture_output=True,
        check=True,
        timeout=120,
    )
    calls = [
        x["result"]
        for line in native.stdout.splitlines()
        if (x := json.loads(line)).get("result", {}).get("kind") == "call"
    ]
    records, checks = [], []
    for call in calls:
        meta = json.loads(call["metadata"])
        original = inventory[meta["raw_sha256"]]
        for row in call["rows"]:
            source = sources[(meta["visit_index"], row["receiver_id"], row["probe_index"])].copy()
            source["analysis_digest"] = analysis_digest
            if source["rate"] != call["rate_hz"] or source["rate"] != original["rate_hz"]:
                raise ValueError("source sample-rate authority mismatch")
            if source["input_digest"] != selection["manifest_sha256"]:
                raise ValueError("source recording authority mismatch")
            if (
                source["window_counter"]
                != original["sample_start_counter"]
                + row["probe_start_ms"] * call["rate_hz"] // 1000
            ):
                raise ValueError("source window counter mismatch")
            for rank, candidate in enumerate(row["candidates"]):
                fractional = candidate["fractional_epoch"]
                complete = fractional["status"] == "complete"
                # Incomplete values are placeholders only in a record explicitly
                # marked incomplete; the projector must emit no observation.
                values = [
                    source[k]
                    for k in (
                        "rate",
                        "anchor_counter",
                        "anchor_utc_ns",
                        "generation",
                        "visit",
                        "window_counter",
                        "probe_index",
                        "receiver",
                        "channel",
                        "upper_edge",
                        "actual_rf_hz",
                        "utc_bracket_width_ns",
                        "input_digest",
                        "analysis_digest",
                        "continuity_qualified",
                    )
                ]
                values += [rank, candidate["epoch"]]
                values += [
                    fractional[k] if complete else 0
                    for k in (
                        "offset_samples",
                        "tracking_cfo_hz",
                        "exact_score",
                        "control_score",
                        "margin",
                    )
                ]
                values += [complete]
                records.append(
                    "\t".join(str(int(v)) if isinstance(v, bool) else str(v) for v in values)
                )
                checks.append((source, rank, fractional))
    projected = subprocess.run(
        [str(a.projector)],
        input=("\n".join(records) + "\n") if records else "",
        text=True,
        capture_output=True,
        check=True,
        timeout=120,
    )
    output = projected.stdout.splitlines()
    if len(output) != len(checks):
        raise ValueError("projection lost candidate accounting")
    retained = 0
    for line, (source, rank, fractional) in zip(output, checks, strict=True):
        expected = fractional["status"] == "complete" and fractional["margin"] >= 0.025
        if (line != "unavailable") != expected:
            raise ValueError("projection availability changed")
        if not expected:
            continue
        fields = line.split("\t")
        group_payload = dict(
            capture=source["input_digest"],
            visit=source["visit"],
            probe=source["probe_index"],
            rx=source["receiver"],
        )
        group = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(group_payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        )
        identifier = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    dict(analysis=analysis_digest, group=group, rank=rank),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
        )
        if fields[:2] != [identifier, group] or float(fields[5]) != fractional["tracking_cfo_hz"]:
            raise ValueError("observation identity/CFO changed")
        anchor = source["anchor_utc_ns"]
        start = anchor + round(
            (source["window_counter"] - source["anchor_counter"]) * 1e9 / source["rate"]
        )
        end = anchor + round(
            (source["window_counter"] - source["anchor_counter"] + source["rate"] // 50)
            * 1e9
            / source["rate"]
        )
        left, center, right = map(int, fields[2:5])
        if not start <= left <= center < right <= end:
            raise ValueError("UTC support escaped the actual IQ window")
        retained += 1
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.with_suffix(".native.jsonl").write_text(native.stdout)
    a.output.with_suffix(".observations.tsv").write_text(projected.stdout)
    report = dict(
        status="pass",
        scope="E1 four saved DS9 visits, native IQ-to-observation bridge",
        complete_scan=False,
        server_parity_qualified=False,
        visits=len(calls),
        candidates=len(records),
        observations=retained,
        analysis_digest=analysis_digest,
        algorithm=algorithm,
        source_authority_sha256=sha(a.source_authority),
        projector_sha256=sha(a.projector),
        native_candidates_from_saved_answers=False,
    )
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "algorithm"}))


if __name__ == "__main__":
    main()
