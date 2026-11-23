"""Score the frozen relinearization only after the two diagnostics seal."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from centre_oracle_iterative_trial import CASES, HERE, PRIOR, PRIOR_SHA
from centre_oracle_step_score import controls, distance_km


def score(directory, output, full):
    blob = PRIOR.read_bytes()
    if sha256(blob).hexdigest() != PRIOR_SHA:
        raise ValueError("The sealed one-step comparison changed")
    prior = json.loads(gzip.decompress(blob))
    complete, blind = {}, {}
    for case in CASES:
        data = (directory / f"{case}.json").read_bytes()
        doc = json.loads(data)
        if doc["case"] != case or any(sha256((HERE / name).read_bytes()).hexdigest() != pin
                                      for name, pin in doc["sources"].items()):
            raise ValueError("Expected the sealed iterative study")
        if any(doc[name] != prior["complete"][case][name] for name in doc["verified_same_oracle"]):
            raise ValueError("Oracle inputs changed after the matching check")
        complete[case], blind[case] = doc, sha256(data).hexdigest()

    matched = controls()
    cases = {}
    for case, doc in complete.items():
        truth, _ = matched[case]
        arms = {}
        for arm, result in doc["trials"].items():
            old = prior["summary"]["cases"][case]["arms"][arm]
            if old["trial"]["centre"] != result["centre"]["authoritative"]:
                raise ValueError("The exact robust readouts should match at the same centre")
            first, final = (distance_km(truth, result[stage]["latlon"])
                            for stage in ("first", "final"))
            first_fit = result["history"][min(1, result["accepted_steps"])]
            last_fit = result["history"][-1]
            arms[arm] = dict(
                v3_error_km=old["v3_error_km"],
                original_short_error_km=old["archived_unfiltered_error_km"],
                one_step_error_km=old["candidate_error_km"],
                first_damped_error_km=first,
                iterated_error_km=final,
                iterative_minus_one_step_km=distance_km(old["trial"]["latlon"],
                                                       result["final"]["latlon"]),
                passes=final <= old["v3_error_km"] + .250,
                stopped=result["stopped"],
                last_tested_full_step_km=result["last_tested_full_step_km"],
                accepted_steps=result["accepted_steps"],
                rejected_trials=sum(e.get("accepted") is False for e in result["evaluations"]),
                profile_calculations=len(result["evaluations"]),
                gaussian_profile=[result["history"][0]["objective"], first_fit["objective"],
                                  last_fit["objective"]],
                robust_check=[result[k]["authoritative"]["robust_loss"]
                              for k in ("centre", "first", "final")],
                robust_one_step=old["trial"]["endpoint"]["robust_loss"],
                last_c_hz_per_ghz=last_fit["c_hz_per_ghz"],
                phase_range_s=[min(last_fit["phase_s"].values()), max(last_fit["phase_s"].values())],
                clocks_ns=result["clocks_ns"],
            )
        cases[case] = dict(arms=arms, oracle_cpu_ns=doc["oracle_cpu_ns"],
                           paired_candidate_cpu_ns=doc["paired_candidate_cpu_ns"],
                           one_step_cpu_ns=prior["summary"]["cases"][case]["paired_candidate_cpu_ns"])
    summary = dict(cases=cases, blind_sha256=blind, single_step_archive_sha256=PRIOR_SHA,
                   passed=all(a["passes"] for c in cases.values() for a in c["arms"].values()),
                   scorer_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                   waveform_reads=0, new_product_publications=0)
    json_bytes = (json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    archive = (json.dumps(dict(complete=complete, summary=summary), sort_keys=True,
                          separators=(",", ":"), allow_nan=False) + "\n").encode()
    with output.open("xb") as out:
        out.write(json_bytes)
    with full.open("xb") as out:
        out.write(gzip.compress(archive, mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ("directory", "output", "full"):
        parser.add_argument(label, type=Path)
    score(**vars(parser.parse_args()))
