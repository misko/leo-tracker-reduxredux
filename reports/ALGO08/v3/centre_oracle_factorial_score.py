"""Score the blind factorial phases and weights against the published references."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from centre_oracle_factorial import CELLS
from centre_oracle_factorial_trial import HERE, PRIOR, PRIOR_SHA, capture
from centre_oracle_step_score import controls, distance_km


def score(directory, output, full):
    complete, blind = {}, {}
    for case in capture.CASES:
        blob = (directory / f"{case}.json").read_bytes()
        row = json.loads(blob)
        if row["case"] != case or not row["exact_nominal_trace"] or any(
                capture.file_sha(HERE / name) != pin for name, pin in row["sources"].items()):
            raise ValueError("The blind factorial receipt or control trace changed")
        complete[case], blind[case] = row, sha256(blob).hexdigest()
    if capture.file_sha(PRIOR) != PRIOR_SHA:
        raise ValueError("The original nominal comparison changed")
    prior = json.loads(gzip.decompress(PRIOR.read_bytes()))["summary"]["cases"]
    matched = controls()
    cases = {}
    for case, row in complete.items():
        truth, _ = matched[case]
        arms = {}
        for arm, result in row["trials"].items():
            control = prior[case]["arms"][arm]
            outcomes = {}
            for name in CELLS:
                cell = result["cells"][name]
                error = distance_km(truth, cell["final"]["latlon"])
                outcomes[name] = dict(
                    error_km=error,
                    delta_v3_error_km=error-control["v3_error_km"],
                    passes=error <= control["v3_error_km"] + .250,
                    stopped=cell["stopped"], accepted=cell["accepted_steps"],
                    rejected=sum(e.get("accepted") is False for e in cell["evaluations"]),
                    evaluations=len(cell["evaluations"]),
                    settled_gaussian=cell["history"][-1]["objective"],
                    robust_centre=cell["centre_authoritative"]["robust_loss"],
                    robust_endpoint=cell["final"]["authoritative"]["robust_loss"],
                    curved_rms_hz=cell["final"]["authoritative"]["curved_rms_hz"],
                    predictive_rms_hz=cell["final"]["authoritative"]["predictive_rms_hz"],
                    profile_cpu_ns=cell["profile_cpu_ns"], audit_cpu_ns=cell["audit_cpu_ns"],
                )
            arms[arm] = dict(cells=outcomes, provider_cpu_ns=result["provider_cpu_ns"],
                             original_short_error_km=control["original_short_error_km"],
                             v3_error_km=control["v3_error_km"])
        cases[case] = dict(arms=arms, origin_replay_cpu_ns=row["oracle_cpu_ns"],
                           all_cells_cpu_ns=row["paired_candidate_cpu_ns"])
    qualifying = [name for name in CELLS if all(
        arm["cells"][name]["passes"] for case in cases.values() for arm in case["arms"].values())]
    summary = dict(cases=cases, blind_sha256=blind, qualifying_cells=qualifying, waveform_reads=0,
                   scorer_sha256=capture.file_sha(Path(__file__)), new_publications=0)
    json_bytes = (json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    archive = (json.dumps(dict(complete=complete, summary=summary), sort_keys=True,
                          separators=(",", ":"), allow_nan=False) + "\n").encode()
    with output.open("xb") as stream:
        stream.write(json_bytes)
    with full.open("xb") as stream:
        stream.write(gzip.compress(archive, mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ("directory", "output", "full"):
        parser.add_argument(label, type=Path)
    score(**vars(parser.parse_args()))
