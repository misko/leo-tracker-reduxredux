"""Join the sealed proposals to the two saved installed publication formats."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from unittest.mock import patch

from . import odd_short_interpolation as frozen
from directed_donor import arrival_phase


def installed_owners(case, installed):
    if case == "DS30-0049":
        return original_owners(case, installed)
    path = frozen.OWNER_0086
    witness = frozen.signed.document(path, frozen.OWNER_0086_PIN)
    receipt = witness["receipt"]
    terminal = frozen.signed.document(
        path.parent/"fast-scan-automatic-work"/receipt["run_id"]/"terminal.json", receipt["terminal_sha256"])
    if (terminal["native_sha256"] != installed["native_sha256"] or witness["verified_handoffs"] != 1
            or witness["waveform_reads"]):
        raise ValueError("The saved 0086 ownership view is unbound")
    rows = witness["ordered_owners"]
    digests = installed["evidence"]["owners"]
    if any(frozen.signed.canonical({oid: norad for oid, norad, _ in rows[arm]}) != digest
           for arm, digest in digests.items()):
        return None
    return frozen.signed.owners(rows, digests)


original_owners = frozen.installed_owners


def strict_provenance(predictions, mixed, installed):
    counts = Counter(dict(original_candidate_empty=0, original_candidate_strict_match=0,
                          original_candidate_positive_strict_mismatch=0))
    hz, samples = frozen.WINDOWS[0]
    for oid, forecast in predictions.items():
        reference = installed[oid]["factor"]
        if reference is None:
            continue
        counter = mixed[oid]["counter"]
        error = frozen.errors_for(forecast, counter, reference)
        if error["hz"] > hz or error["samples"] > samples:
            continue
        candidate = mixed[oid]["factor"]
        if candidate is None:
            counts["original_candidate_empty"] += 1
            continue
        original = dict(cfo_hz=candidate[frozen.HERTZ], arrival=arrival_phase(counter, candidate))
        error = frozen.errors_for(original, counter, reference)
        name = ("original_candidate_strict_match" if error["hz"] <= hz and error["samples"] <= samples
                else "original_candidate_positive_strict_mismatch")
        counts[name] += 1
    return dict(counts)


def audit_fallback(scores, plan):
    for case, scored in scores["cases"].items():
        predictions = plan["cases"][case]["proposals"]
        _, result, candidate, _, clock = frozen.candidate(case)
        _, installed, pub = frozen.original(case, "installed")
        if (result["native_sha256"] != plan["cases"][case]["native_sha256"]
                or installed["native_sha256"] != scored["installed_native_sha256"]):
            raise ValueError("Reference-only provenance must bind both scored packet identities")
        reference = frozen.signed.read_native(pub, installed["native_sha256"])
        mixed, stock = map(frozen.signed.opportunities, (candidate, reference))
        provenance = strict_provenance(predictions, mixed, stock)
        if sum(provenance.values()) != scored["windows"]["250Hz/2samples"]["both"]:
            raise ValueError("Strict hit provenance does not partition the sealed matches")
        scored["strict_hit_provenance"] = provenance
        short = scored["callbacks"]["original"]["short_primary"]
        stereo = Counter(mixed[oid]["row"]["visit_index"] for oid in predictions)
        scored["fallback_callback_ceiling"] = dict(
            proposed_short_lanes=len(predictions), original_short_lanes=short,
            short_fraction=len(predictions)/short, complete_two_radio_visits=sum(n==2 for n in stereo.values()),
            gross_mean_short_callback_s={metric: len(predictions)*clock[f"native_{metric}_ns"]["short_primary"]
                                         /short/1e9 for metric in ("wall", "cpu")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prediction", type=Path)
    parser.add_argument("sha256")
    args = parser.parse_args()
    sys.addaudithook(frozen.deny_backing)
    with patch.object(frozen, "installed_owners", installed_owners):
        result = frozen.score(args.prediction, args.sha256)
    audit_fallback(result, frozen.signed.document(args.prediction, args.sha256))
    print(json.dumps(result, sort_keys=True, allow_nan=False, indent=2))
