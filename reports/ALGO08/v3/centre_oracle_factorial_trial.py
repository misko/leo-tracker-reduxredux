"""Capture the original provider, then seal four proxy branches per arm."""

import argparse
import gzip
import json
from pathlib import Path
from unittest.mock import patch

import centre_oracle_step
import centre_oracle_step_trial as capture
from aperture_trial import write
from centre_oracle_factorial import factor_arm


HERE = capture.HERE
PRIOR = HERE / "measurements/centre-oracle-iterative.json.gz"
PRIOR_SHA = "7fe59af88cc9c21d6bc4897ea6821338a4b7fdbb70243df7f5f20e7823e3c4d3"


class FactorialOracle(capture.OwnerOracle):
    def repair(self, prepared, signed, measured):
        def proxy(scan, node, keep, entries, means, model, arm):
            return factor_arm(scan, node, keep, entries, means, model, arm,
                              record=signed["arms"][arm], original_powers=signed["powers"])

        with patch.object(centre_oracle_step, "arm_step", proxy):
            return super().repair(prepared, signed, measured)


def trace(row):
    return {key: row[key] for key in ("history", "stopped", "accepted_steps")}


def run(case, output):
    if capture.file_sha(PRIOR) != PRIOR_SHA:
        raise ValueError("The nominal control archive changed")
    intermediate = output.with_name(f"{case}-verified-capture.json")
    with patch.object(capture, "OwnerOracle", FactorialOracle):
        capture.run(case, intermediate)
    document = json.loads(intermediate.read_bytes())
    original = json.loads(gzip.decompress(PRIOR.read_bytes()))["complete"][case]
    if (any(document[key] != original[key] for key in original["verified_same_oracle"])
            or any(trace(result["cells"]["causal_unit"]) != trace(original["trials"][arm])
                   for arm, result in document["trials"].items())):
        raise ValueError("Original exact rows/priors or the causal nominal profile changed")
    document["exact_nominal_trace"] = True
    document["sources"].update({name: capture.file_sha(HERE / name) for name in (
        "centre-oracle-factorial-protocol.md", "centre_oracle_factorial.py",
        "centre_oracle_factorial_trial.py", "measurements/centre-oracle-iterative.json.gz")})
    write(output, document)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=capture.CASES)
    parser.add_argument("output", type=Path)
    run(**vars(parser.parse_args()))
