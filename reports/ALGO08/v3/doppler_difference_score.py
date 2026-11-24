"""Score sealed contrast results against pre-existing controls after both exit."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def compare(output, receipt):
    from centre_oracle_step_score import PINS, controls
    from tools.pipeline_eval.scoring import distance_km

    originals, provenance = {}, {}
    for case in ("physical", "north"):
        body = (output/f"{case}.json").read_bytes()
        data = json.loads(body)
        if (case != data["case"] or data["raw_reads"] or any(
                sha256((HERE/name).read_bytes()).hexdigest() != pin for name, pin in data["sources"].items())):
            raise ValueError("Use only the complete frozen matched-owner pilot")
        originals[case] = data
        provenance[case] = dict(blind_sha256=sha256(body).hexdigest(),
                                process_telemetry=(output/f"{case}.time").read_text().strip().splitlines())

    matches = controls()
    cases = {}
    for name, data in originals.items():
        ref, stock = matches[name]
        arms = {}
        for arm, results in data["fit"].items():
            error_named = distance_km(ref, stock[arm]["latlon"])
            entries = {}
            for model, trial in results["results"].items():
                error = distance_km(ref, trial.get("latlon"))
                passes = bool(error is not None and not trial["face"] and trial["profiled"]["numerical_rank"] == 2
                              and error <= error_named + .250
                              and trial["endpoint_rf_check"]["robust_loss"] < results["centre_rf_check"]["robust_loss"]
                              and (arm == "c0" or trial["fitted_c_hz_per_ghz"] is not None))
                entries[model] = dict(error_km=error, named_error_km=error_named, passes=passes,
                                      fitted_c_identifiable=bool(trial.get("fitted_c_hz_per_ghz") is not None),
                                      **trial)
            arms[arm] = dict(results, results=entries)
        cases[name] = dict(arms=arms, oracle_rows=len(data["oracle_rows"]), oracle_cpu_ns=data["owner_provider_cpu_ns"],
                           paired_candidate_cpu_ns=data["paired_diagnostic_cpu_ns"], request_sha256=data["request_sha256"],
                           archive=data["archive"], native_sha256=data["original_native_sha256"],
                           named_provider=data["owner_provider_signed"], sources=data["sources"], **provenance[name])

    qualifies = {method: all(arm["results"][method]["passes"] for case in cases.values() for arm in case["arms"].values())
                 for method in ("shape", "shape_and_mean")}
    result = dict(cases=cases, reference_pins=PINS, qualifies=qualifies, raw_reads=0, fresh_publications=0)
    body = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    with receipt.open("xb") as stream:
        stream.write(gzip.compress(body, mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("receipt", type=Path)
    compare(**vars(parser.parse_args()))
