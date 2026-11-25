"""Read a physically fixed carrier disagreement indicator from sealed small metadata."""

import argparse
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path


DATA = Path(__file__).resolve().parent/"measurements"
PINS = {
    "anchor-cfo-innovation-held-plan.json": "a16f7fb0d7be0cd97c7ebd0eedaf03791fd0b39ae8c7c9b5f717019d25974160",
    "anchor-cfo-innovation-development-plan.json": "d413a0392769249dc6a2977a43290b586dbe91ec927fd38a07a1cf9bddfef134",
    "held-short-cfo-shrink-prediction.json.gz": "3e8881c463ff66d0f936e4ac4cfbe9f2589f5543a6e4a776081cffa2473ae99d",
    "ds30-routing-first64.json.gz": "6958f0a428eeb70ca147aa19c595a834298f1e613ae0776a07e448f230406b10",
}
HERTZ = 250.
ARMS = ("c0", "fitted_c")


def load(name):
    raw = (DATA/name).read_bytes()
    if sha256(raw).hexdigest() != PINS[name]:
        raise ValueError("The saved metadata changed")
    return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)


def anchor_disagreement(ledger):
    sizes = ledger["counts"]
    innovations = list(ledger["anchor_innovations_hz"].values())
    outside = sum(abs(value) > HERTZ for value in innovations)
    tested = sizes["rank_zero_with_forecast"]
    if (tested != len(innovations) or not all(map(isfinite, innovations))
            or tested-outside != sizes["eligible_full_anchors"]
            or not 0 <= tested <= sizes["rank_zero_full_positives"] <= sizes["full_positives"] <= sizes["full_lanes"]):
        raise ValueError("The anchor ledger does not bind the unfiltered forecast denominator")
    return dict(candidate_attempt_sha256=ledger["candidate_result_sha256"],
                candidate_native_sha256=ledger["candidate_native_sha256"], full_lanes=sizes["full_lanes"],
                full_positives=sizes["full_positives"], short_positives=sizes["short_positives"],
                with_forecast=tested, beyond_250_hz=outside, rate=outside/tested if tested else None)


def two_full_forecast(ledger):
    rows = ledger["forecasts"]
    full = [key for key, row in rows.items() if row["donor_full"] == [True, True]]
    if any(row["left_wait_samples"]+row["right_wait_samples"] > 12_500_000 for row in rows.values()):
        raise ValueError("This ledger differs from the registered spacing gates")
    return dict(original_native_sha256=ledger["native_sha256"], held_lanes=ledger["held_lanes"],
                held_candidate_positives=ledger["held_candidate_positives"], forecasts=len(rows),
                both_full_donors=len(full),
                both_full_donors_eligible_to_edit=sum(key in ledger["eligible"] for key in full))


def candidate_only():
    return dict(
        gate_hz=HERTZ,
        source_pins={name: pin for name, pin in PINS.items() if name != "ds30-routing-first64.json.gz"},
        retrospective_primary={
            source: {case: anchor_disagreement(row) for case, row in
                     load(f"anchor-cfo-innovation-{source}-plan.json")["cases"].items()}
            for source in ("development", "held")
        },
        two_full_coverage={case: two_full_forecast(row) for case, row in
                           load("held-short-cfo-shrink-prediction.json.gz")["cases"].items()},
    )


def gate(installed, candidate, arm):
    key, fix = arm+"_error_km", arm+"_fix"
    baseline_error, candidate_error = installed[key], candidate[key]
    if baseline_error is None:
        return "installed_unscored" if installed[fix] else "installed_withheld"
    if baseline_error > 1.:
        return "installed_outside"
    if candidate_error is None:
        return "candidate_unscored" if candidate[fix] else "lost_withheld"
    return "kept" if candidate_error <= 1. else "lost"


def concordance(rows):
    kept = [value for status, value in rows if status == "kept" and value is not None]
    lost = [value for status, value in rows if status in {"lost", "lost_withheld"} and value is not None]
    comparisons = [(a, b) for a in lost for b in kept]
    return dict(kept=len(kept), lost=len(lost), comparisons=len(comparisons),
                ranks_loss_higher=sum(a > b for a, b in comparisons),
                ties=sum(a == b for a, b in comparisons))


def compare(prediction, field):
    archived = {row["case"]: row for row in field["measurements"]}
    result, ranking = {}, {arm: [] for arm in ARMS}
    for source, cases in prediction["retrospective_primary"].items():
        result[source] = {}
        for case, observed in cases.items():
            installed, candidate = (archived[case][name] for name in ("installed", "successor"))
            if candidate["attempt_result_sha256"] != observed["candidate_attempt_sha256"]:
                raise ValueError("The candidate-only statistic and scored position have different attempts")
            rate = (Fraction(observed["beyond_250_hz"], observed["with_forecast"])
                    if observed["with_forecast"] else None)
            result[source][case] = {}
            for arm in ARMS:
                state = gate(installed, candidate, arm)
                result[source][case][arm] = dict(gate=state, installed_km=installed[arm+"_error_km"],
                                                    candidate_km=candidate[arm+"_error_km"])
                if source == "held":
                    ranking[arm].append((state, rate))
    return dict(outcomes=result, held_concordance={arm: concordance(rows) for arm, rows in ranking.items()},
                score_source_sha256=PINS["ds30-routing-first64.json.gz"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score", type=Path, help="Use only the already sealed candidate-only readout")
    args = parser.parse_args()
    prediction = candidate_only()
    if args.score:
        raw = args.score.read_bytes()
        if json.loads(raw) != prediction:
            raise ValueError("The input differs from the frozen candidate-only readout")
        result = compare(prediction, load("ds30-routing-first64.json.gz"))
        result["prediction_sha256"] = sha256(raw).hexdigest()
    else:
        result = prediction
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
