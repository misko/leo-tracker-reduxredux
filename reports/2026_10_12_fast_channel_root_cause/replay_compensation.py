"""Counterfactual replay: retain all GLRT evidence, compensate a frozen band step."""

import argparse
import json
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from diagnose import load_source

from leo.application.regional_position_inputs import prepare_position_windows
from leo.cli import regional_position
from leo.contracts.digests import canonical_digest
from leo.storage.regional_position_v3 import B7Store


def compensate(source, steps):
    probes = []
    for p in source.probes:
        step = steps[p.receiver_id] if p.channel >= 5 else 0
        probes.append(
            replace(
                p,
                candidates=tuple(
                    replace(c, fractional_tracking_cfo_hz=c.fractional_tracking_cfo_hz - step)
                    for c in p.candidates
                ),
            )
        )
    return replace(source, probes=tuple(probes))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--diagnostics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    original = load_source(args.parent)
    diagnostics = json.loads(args.diagnostics.read_text())
    steps = {r["receiver"]: r["high_minus_low_hz"] for r in diagnostics["offset_contrast"]}
    corrected = compensate(original, steps)
    before = prepare_position_windows(original).observations
    after = prepare_position_windows(corrected).observations
    assert before.window_ids == after.window_ids
    assert (before.times_s == after.times_s).all()
    assert (before.margin == after.margin).all()
    assert (before.rf_hz == after.rf_hz).all()
    binding = canonical_digest(
        {
            "capture": original.input_manifest_sha256,
            "analysis": original.analysis_manifest_sha256,
            "steps_hz": {str(k): v for k, v in steps.items()},
            "policy": "frozen-rx-band-offset-counterfactual-v1",
        }
    )
    corrected = replace(corrected, input_manifest_sha256=binding)
    receipt = dict(
        steps_hz=steps,
        scope=(
            "All-data half-model calibration offsets, frozen before full-channel replay; "
            "diagnostic counterfactual, not an independent validation."
        ),
        original_input_sha256=original.input_manifest_sha256,
        binding=binding,
        windows=len(before.window_ids),
        probe_counts=dict(Counter(p.channel for p in corrected.probes)),
        evidence_checks=(
            "Identical selected observation rows, times, margins, RF, receivers and "
            "candidates; only high-group measured CFO translated."
        ),
        engine=regional_position.__file__,
        slice_seconds=500,
        maximum_slices=3,
    )

    class InputPort:
        def __init__(self, _root):
            pass

        def load(self, sid):
            assert sid == corrected.session_id
            return corrected

        def close(self):
            pass

    started = time.monotonic()
    with patch.object(regional_position, "ScannerTrackingInputStore", InputPort):
        for index in range(3):
            result = regional_position.run_regional_position_analysis(
                args.output, Path("/var/lib/leo/tle"), corrected.session_id, maximum_seconds=500
            )
            print(
                json.dumps(dict(slice=index + 1, elapsed_s=time.monotonic() - started, **result)),
                flush=True,
            )
            if result["state"] == "complete":
                break
    receipt.update(result=result, elapsed_s=time.monotonic() - started)
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if result["state"] != "complete":
        raise RuntimeError("Bounded replay incomplete")
    doc = B7Store(args.output).status(corrected.session_id).manifest.document
    (args.output / "regional.json").write_text(doc.model_dump_json(indent=2) + "\n")


if __name__ == "__main__":
    main()
