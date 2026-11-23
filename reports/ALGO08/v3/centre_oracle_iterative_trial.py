"""Reuse the exact signed capture and compare the owner inputs before sealing."""

import argparse
import gzip
import json
from pathlib import Path
from unittest.mock import patch

import centre_oracle_step
from aperture_trial import write
from centre_oracle_iterative import arm_iterative
from centre_oracle_step_trial import CASES, HERE, file_sha, run


PRIOR = HERE / "measurements/centre-oracle-step.json.gz"
PRIOR_SHA = "1e28c18d4d6fa16102abee15252500289bd2223caf39f97c1b581d740f29a305"


def trial(case, output):
    if file_sha(PRIOR) != PRIOR_SHA:
        raise ValueError("Expected the sealed single-step archive")
    capture = output.with_name(f"{case}-checked-capture.json")
    with patch.object(centre_oracle_step, "arm_step", arm_iterative):
        run(case, capture)
    row = json.loads(capture.read_bytes())
    original = json.loads(gzip.decompress(PRIOR.read_bytes()))["complete"][case]
    fields = ("binding", "oracle_rows", "oracle_aliases", "oracle_arms",
              "prior_model", "causal_means_s", "request_sha256")
    if any(row[key] != original[key] for key in fields):
        raise ValueError("The repeated diagnostic must use identical owners, aliases and priors")
    row["sources"].update({name: file_sha(HERE / name) for name in (
        "centre-oracle-iterative-protocol.md", "centre_oracle_iterative.py",
        "centre_oracle_iterative_trial.py", "measurements/centre-oracle-step.json.gz")})
    row["verified_same_oracle"] = list(fields)
    write(output, row)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output", type=Path)
    trial(**vars(parser.parse_args()))
